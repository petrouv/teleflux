"""Main synchronization module for Teleflux.

This module contains the core synchronization logic that orchestrates the process
of synchronizing Telegram channels organized in folders with Miniflux RSS categories.
It provides comprehensive two-stage synchronization with conflict resolution,
detailed logging, and extensive error handling.

The synchronization process includes:
    - Stage 1: Planning and conflict resolution across folders
    - Stage 2: Applying changes (add/move feeds, then remove unused feeds)
    - Title updates with emoji handling options
    - Comprehensive comparison displays and progress reporting
    - Dry-run mode for safe testing

Key components:
    - SyncAction: Represents individual synchronization actions
    - SyncResult: Contains results of synchronization operation
    - TelefluxSyncer: Main synchronization orchestrator
    - Utility functions for emoji handling and URL normalization

The module handles complex scenarios like channels appearing in multiple folders,
private channel support with secret URLs, and maintains consistency across
large numbers of channels and categories.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from tabulate import tabulate


def remove_emojis(text: str) -> str:
    """Remove all emojis from text and clean up whitespace.

    This function removes emojis and related Unicode formatting characters that
    are commonly used in Telegram channel titles. It uses comprehensive Unicode
    ranges to catch various emoji types and cleans up the resulting whitespace.

    The function handles:
        - Standard emoticons and symbols
        - Transport, map, and flag symbols
        - Dingbats and enclosed characters
        - Supplemental symbols and pictographs
        - Zero-width joiners and variation selectors
        - Other invisible formatting characters

    Args:
        text: Input text that may contain emojis and Unicode formatting

    Returns:
        Cleaned text with emojis removed and whitespace normalized

    Example:
        >>> remove_emojis("🚀 Tech News 📱 Channel")
        "Tech News Channel"
        >>> remove_emojis("AI & ML 🤖💡 Updates")
        "AI & ML Updates"
    """
    if not text:
        return text

    # Comprehensive Unicode ranges for emojis
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags (iOS)
        "\U00002702-\U000027b0"  # dingbats
        "\U000024c2-\U0001f251"  # enclosed characters
        "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
        "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
        "\U00002600-\U000026ff"  # miscellaneous symbols
        "\U00002700-\U000027bf"  # dingbats
        "\u2640-\u2642"  # gender symbols
        "\u23cf"  # eject symbol
        "\u23e9"  # fast forward
        "\u231a"  # watch
        "\u3030"  # wavy dash
        "]+",
        flags=re.UNICODE,
    )

    # Replace emojis with spaces to maintain word boundaries
    cleaned = emoji_pattern.sub(" ", text)

    # Remove Zero Width Joiner (ZWJ) and other invisible formatting characters
    # that are commonly used in emoji sequences
    invisible_chars_pattern = re.compile(
        "["
        "\u200d"  # Zero Width Joiner (ZWJ)
        "\ufe0f"  # Variation Selector-16 (makes preceding character emoji-style)
        "\u200c"  # Zero Width Non-Joiner (ZWNJ)
        "\u200b"  # Zero Width Space
        "\u2060"  # Word Joiner
        "\ufeff"  # Zero Width No-Break Space (BOM)
        "\u180e"  # Mongolian Vowel Separator
        "]+",
        flags=re.UNICODE,
    )

    # Remove invisible formatting characters
    cleaned = invisible_chars_pattern.sub(" ", cleaned)

    # Normalize whitespace: remove multiple consecutive spaces and trim
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


from .config import Config
from .miniflux_client import MinifluxClient
from .telegram_client import TelegramChannel, TelegramClient

logger = logging.getLogger(__name__)


@dataclass
class SyncAction:
    """Represents a single synchronization action to be performed.

    This class encapsulates information about a specific action during
    synchronization, such as adding a feed, removing a feed, updating
    a title, or moving a feed between categories.

    Attributes:
        action: Type of action ('add', 'remove', 'update_title', 'move_category')
        channel_title: Name of the Telegram channel being processed
        feed_url: RSS feed URL for the channel
        category_name: Target Miniflux category name
        old_title: Previous feed title (for update_title actions)
        old_category: Previous category name (for move_category actions)
    """

    action: str  # 'add', 'remove', 'update_title', or 'move_category'
    channel_title: str
    feed_url: str
    category_name: str
    old_title: str | None = None  # For update_title actions
    old_category: str | None = None  # For move_category actions


@dataclass
class SyncResult:
    """Contains the results of a synchronization operation.

    This class aggregates all actions performed during synchronization
    and any errors encountered, providing a comprehensive summary of
    the synchronization process.

    Attributes:
        added_feeds: List of feed addition actions
        removed_feeds: List of feed removal actions
        updated_titles: List of title update actions
        moved_feeds: List of feed movement actions between categories
        errors: List of error messages encountered during synchronization
        dry_run: Whether this was a dry-run operation (no actual changes made)
    """

    added_feeds: list[SyncAction]
    removed_feeds: list[SyncAction]
    updated_titles: list[SyncAction]
    moved_feeds: list[SyncAction]
    errors: list[str]
    dry_run: bool = False


class TelefluxSyncer:
    """Main synchronization orchestrator for Teleflux operations.

    This class manages the complete synchronization process between Telegram
    folders and Miniflux categories. It handles conflict resolution, feed
    management, error handling, and provides detailed progress reporting.

    The synchronizer implements a two-stage process:
        1. Planning: Analyze folders, resolve conflicts, and plan actions
        2. Execution: Apply planned changes with error handling and rollback
    """

    def __init__(self, config: Config, quiet: bool = False):
        """Initialize synchronization orchestrator.

        Args:
            config: Application configuration containing API credentials and settings
            quiet: If True, suppress non-error output for automated operation
        """
        self.config = config
        self.miniflux_client = MinifluxClient(config.miniflux)
        self.quiet = quiet

    def _build_rss_url(self, channel: TelegramChannel) -> str:
        """Build RSS feed URL for a Telegram channel using RSSHub.

        Constructs the appropriate RSS URL based on channel type (public/private)
        and configuration settings. For private channels, includes secret hash
        if available and private feed mode is set to "secret".

        Args:
            channel: Telegram channel object containing channel information

        Returns:
            RSS feed URL string, or empty string if channel should be skipped
            or URL cannot be constructed
        """
        base_url = self.config.rsshub.base_url

        if channel.is_private:
            if self.config.sync.private_feed_mode == "skip":
                return ""

            # For private channels use ID and add secret
            channel_identifier = str(abs(channel.id))  # Remove minus sign for ID
            url = f"{base_url}/telegram/channel/{channel_identifier}"

            if channel.channel_hash:
                params = {"secret": channel.channel_hash}
                url += "?" + urlencode(params)

            return url
        else:
            # For public channels use username
            if not channel.username:
                logger.warning(f"Public channel {channel.title} has no username")
                return ""

            # Always convert username to lowercase for consistency
            return f"{base_url}/telegram/channel/{channel.username.lower()}"

    def _normalize_url_for_comparison(self, url: str) -> str:
        """Normalize URL for case-insensitive comparison.

        Converts URL to lowercase to enable case-insensitive matching.
        This is necessary because URLs may have different cases in
        different sources but refer to the same resource.

        Args:
            url: URL string to normalize

        Returns:
            Normalized URL in lowercase for consistent comparison
        """
        return url.lower()

    def _create_url_mapping(self, urls: set[str]) -> dict:
        """Create mapping from normalized URLs to original URLs.

        Creates a dictionary that maps case-normalized URLs to their original
        forms, enabling case-insensitive URL lookups while preserving the
        original URL format.

        Args:
            urls: Set of original URL strings

        Returns:
            Dictionary mapping normalized URLs to original URLs
        """
        return {self._normalize_url_for_comparison(url): url for url in urls}

    def _find_matching_url(self, target_url: str, url_mapping: dict) -> str | None:
        """Find matching URL using case-insensitive comparison.

        Looks up a target URL in a normalized URL mapping to find the
        corresponding original URL, enabling case-insensitive URL matching.

        Args:
            target_url: URL to search for
            url_mapping: Dictionary mapping normalized URLs to original URLs

        Returns:
            Original URL if a match is found, None otherwise
        """
        normalized_target = self._normalize_url_for_comparison(target_url)
        return url_mapping.get(normalized_target)

    def _is_telegram_feed(self, feed_url: str) -> bool:
        """Check if feed URL is a Telegram feed created via RSSHub.

        Determines whether a given feed URL was generated by RSSHub for a
        Telegram channel by checking if it matches the expected URL pattern.

        Args:
            feed_url: Feed URL to analyze

        Returns:
            True if the URL is a Telegram feed from RSSHub, False otherwise
        """
        base_url = self.config.rsshub.base_url.rstrip("/")
        telegram_path = "/telegram/channel/"

        # Check if URL starts with our RssHub base URL and contains Telegram path
        return feed_url.startswith(base_url) and telegram_path in feed_url

    def _filter_channels(
        self, channels: list[TelegramChannel]
    ) -> list[TelegramChannel]:
        """Filter channels based on configuration settings.

        Removes channels that should not be synchronized according to the
        current configuration. This includes filtering out private channels
        when private_feed_mode is set to "skip".

        Args:
            channels: List of channels to filter

        Returns:
            Filtered list of channels that should be synchronized
        """
        if self.config.sync.private_feed_mode != "skip":
            return channels

        filtered_channels = []
        skipped_count = 0

        for channel in channels:
            # Skip all private channels when private_feed_mode is "skip"
            if channel.is_private:
                logger.info(
                    f"Skipping private channel: '{channel.title}' from folder '{channel.folder_name}' - private channels are not synchronized"
                )
                skipped_count += 1
                continue

            filtered_channels.append(channel)

        if skipped_count > 0:
            logger.info(f"Filtered out {skipped_count} private channels")

        return filtered_channels

    async def _plan_synchronization(
        self, all_channels: list[TelegramChannel]
    ) -> tuple[dict[str, tuple[str, str, TelegramChannel]], list[dict]]:
        """Plan synchronization and resolve conflicts between channels in multiple folders.

        Analyzes all channels across folders and creates a conflict-free assignment
        plan. When a channel appears in multiple folders, the first folder in the
        configuration takes priority (order-based conflict resolution).

        Args:
            all_channels: List of all channels from all configured folders

        Returns:
            Tuple containing:
                - Dictionary mapping feed_url to (category_name, folder_name, channel)
                - List of conflict dictionaries describing channels found in multiple folders
        """
        channel_assignments = {}  # feed_url -> (category_name, folder_name, channel)
        conflicts = []

        # Process folders in the order they appear in config (priority by order)
        for folder_name, category_name in self.config.sync.folders.items():
            # Get channels for this folder
            folder_channels = [
                ch for ch in all_channels if ch.folder_name == folder_name
            ]

            for channel in folder_channels:
                feed_url = self._build_rss_url(channel)
                if not feed_url:
                    # Skip channels that can't generate RSS URLs
                    if (
                        channel.is_private
                        and self.config.sync.private_feed_mode == "skip"
                    ):
                        logger.debug(
                            f"Skipping private channel: '{channel.title}' from folder '{folder_name}' - private channels are not synchronized"
                        )
                    else:
                        logger.warning(
                            f"Failed to build RSS URL for channel: {channel.title}"
                        )
                    continue

                if feed_url in channel_assignments:
                    # Conflict detected: channel already assigned to another category
                    existing_category, existing_folder, existing_channel = (
                        channel_assignments[feed_url]
                    )
                    conflicts.append(
                        {
                            "channel": channel,
                            "existing_folder": existing_folder,
                            "existing_category": existing_category,
                            "new_folder": folder_name,
                            "new_category": category_name,
                        }
                    )
                    # Keep the first assignment (priority by config order)
                    continue
                else:
                    # First assignment for this channel
                    channel_assignments[feed_url] = (
                        category_name,
                        folder_name,
                        channel,
                    )

        return channel_assignments, conflicts

    def _get_category_name_by_id(self, category_id: int) -> str:
        """Get category name by ID with fallback for unknown categories.

        Retrieves the human-readable name for a category ID. If the category
        cannot be found, returns a fallback string to ensure robustness.

        Args:
            category_id: Miniflux category identifier

        Returns:
            Category name if found, or fallback string like "Category {id}"
        """
        try:
            category = self.miniflux_client.get_category_by_id(category_id)
            return category.title if category else f"Category {category_id}"
        except Exception:
            return f"Category {category_id}"

    def _display_folder_comparison(
        self,
        tg_folder: str,
        miniflux_category: str,
        channels: list[TelegramChannel],
        existing_feeds: list,
        channel_assignments: dict[str, tuple[str, str, TelegramChannel]] = None,
        all_existing_feeds: list = None,
        dry_run: bool = False,
        update_titles: bool = False,
    ) -> None:
        """Display detailed side-by-side comparison of Telegram channels and Miniflux feeds.

        Creates a comprehensive table showing the current state and planned actions
        for synchronization between a Telegram folder and Miniflux category. The
        display includes feed status, planned operations, and summary statistics.

        The table shows various action types:
            - [IN SYNC]: Channel and feed are already synchronized
            - [TO ADD]: New feed will be created for this channel
            - [TO REMOVE]: Feed will be deleted (no corresponding channel)
            - [MOVED IN/OUT]: Feed will be moved between categories
            - [CONFLICT]: Channel assigned to different category due to conflicts
            - [SKIPPED]: Private channel skipped due to configuration
            - [ERROR]: Channel with RSS URL generation problems

        Args:
            tg_folder: Telegram folder name being processed
            miniflux_category: Target Miniflux category name
            channels: List of Telegram channels in this folder
            existing_feeds: List of existing Miniflux feeds in this category
            channel_assignments: Planned assignments mapping feed_url to
                               (category_name, folder_name, channel)
            all_existing_feeds: Complete list of all Miniflux feeds for move detection
            dry_run: Whether this is a dry-run operation (affects display labels)
            update_titles: Whether title updates are enabled (affects count calculations)
        """
        # Skip all display output in quiet mode
        if self.quiet:
            return

        # Build mapping of channels to RSS URLs
        channel_by_url = {}
        telegram_items = []

        for channel in channels:
            rss_url = self._build_rss_url(channel)
            if rss_url:
                channel_by_url[rss_url] = channel
                # Build original Telegram URL
                if channel.username:
                    tg_url = f"https://t.me/{channel.username}"
                else:
                    tg_url = (
                        f"https://t.me/c/{abs(channel.id)}"
                        if channel.is_private
                        else "Private channel"
                    )

                telegram_items.append(
                    {
                        "title": channel.title,
                        "tg_url": tg_url,
                        "rss_url": rss_url,
                        "status": "normal",
                    }
                )
            else:
                if channel.is_private and self.config.sync.private_feed_mode == "skip":
                    telegram_items.append(
                        {
                            "title": channel.title,
                            "tg_url": "Private channel",
                            "rss_url": "SKIPPED",
                            "status": "skipped",
                        }
                    )
                else:
                    telegram_items.append(
                        {
                            "title": channel.title,
                            "tg_url": "Unknown",
                            "rss_url": "ERROR",
                            "status": "error",
                        }
                    )

        # Get Miniflux feeds (only Telegram feeds)
        miniflux_items = []
        other_feeds = []

        for feed in existing_feeds:
            if self._is_telegram_feed(feed.feed_url):
                miniflux_items.append({"title": feed.title, "url": feed.feed_url})
            else:
                other_feeds.append(feed.title)

        # Create sets for comparison
        telegram_rss_urls = {
            item["rss_url"] for item in telegram_items if item["status"] == "normal"
        }
        miniflux_urls = {item["url"] for item in miniflux_items}

        # Create mapping for matched items using case-insensitive comparison
        telegram_url_mapping = self._create_url_mapping(telegram_rss_urls)
        miniflux_url_mapping = self._create_url_mapping(miniflux_urls)

        # Find matches using case-insensitive comparison
        matched_pairs = []
        matched_telegram_urls = set()
        matched_miniflux_urls = set()

        for tg_url in telegram_rss_urls:
            matching_mf_url = self._find_matching_url(tg_url, miniflux_url_mapping)
            if matching_mf_url:
                matched_pairs.append((tg_url, matching_mf_url))
                matched_telegram_urls.add(tg_url)
                matched_miniflux_urls.add(matching_mf_url)

        # Display header
        mode_text = "[DRY RUN] " if dry_run else ""
        logger.info(
            f"\n{mode_text}Folder Comparison: {tg_folder} -> {miniflux_category}"
        )

        # Prepare table data
        table_data = []

        # Add matched items (check if they will be moved)
        for tg_url, mf_url in matched_pairs:
            tg_item = next(item for item in telegram_items if item["rss_url"] == tg_url)
            mf_item = next(item for item in miniflux_items if item["url"] == mf_url)

            # Check if this feed will be moved to a different category
            status_text = "[IN SYNC]"
            if channel_assignments:
                # Find the planned assignment for this feed
                normalized_tg_url = self._normalize_url_for_comparison(tg_url)
                for feed_url, (
                    planned_category,
                    _planned_folder,
                    _planned_channel,
                ) in channel_assignments.items():
                    normalized_feed_url = self._normalize_url_for_comparison(feed_url)
                    if normalized_feed_url == normalized_tg_url:
                        # This feed has a planned assignment
                        if planned_category != miniflux_category:
                            # Feed will be moved to a different category
                            status_text = f"[MOVED OUT → {planned_category}]"
                        break

            # New column order: Action, Channel Name, Channel URL, Feed Name, Feed URL
            table_data.append(
                [
                    status_text,
                    remove_emojis(tg_item["title"]),
                    tg_item["tg_url"],
                    remove_emojis(mf_item["title"]),
                    mf_item["url"],
                ]
            )

        # Add items to add or move in (Telegram only)
        for item in telegram_items:
            if item["rss_url"] not in matched_telegram_urls:
                if item["status"] == "normal":
                    # Check if this feed exists in another category and will be moved here
                    status_text = "[TO ADD]"
                    feed_name = ""  # No feed exists yet
                    feed_url = ""  # No feed URL yet

                    if channel_assignments:
                        normalized_item_url = self._normalize_url_for_comparison(
                            item["rss_url"]
                        )
                        for feed_url_key, (
                            planned_category,
                            _planned_folder,
                            _planned_channel,
                        ) in channel_assignments.items():
                            normalized_feed_url = self._normalize_url_for_comparison(
                                feed_url_key
                            )
                            if normalized_feed_url == normalized_item_url:
                                # Found the planned assignment for this feed
                                if planned_category == miniflux_category:
                                    # This feed will be moved to this category from another category
                                    # We need to check if it exists anywhere in Miniflux
                                    # Use all feeds passed as parameter to avoid API calls
                                    if all_existing_feeds:
                                        for existing_feed in all_existing_feeds:
                                            if self._is_telegram_feed(
                                                existing_feed.feed_url
                                            ):
                                                normalized_existing_url = (
                                                    self._normalize_url_for_comparison(
                                                        existing_feed.feed_url
                                                    )
                                                )
                                                if (
                                                    normalized_existing_url
                                                    == normalized_item_url
                                                ):
                                                    # Feed exists in another category, so it's a move
                                                    old_category_name = (
                                                        self._get_category_name_by_id(
                                                            existing_feed.category_id
                                                        )
                                                    )
                                                    status_text = f"[MOVED IN ← {old_category_name}]"
                                                    feed_name = remove_emojis(
                                                        existing_feed.title
                                                    )
                                                    feed_url = existing_feed.feed_url
                                                    break
                                else:
                                    # This feed is assigned to a different category (conflict resolution)
                                    # Don't show it as TO ADD, show it as conflict
                                    status_text = f"[CONFLICT → {planned_category}]"
                                break

                elif item["status"] == "skipped":
                    status_text = "[SKIPPED]"
                    feed_name = ""
                    feed_url = ""
                else:
                    status_text = "[ERROR]"
                    feed_name = ""
                    feed_url = ""

                # New column order: Action, Channel Name, Channel URL, Feed Name, Feed URL
                table_data.append(
                    [
                        status_text,
                        remove_emojis(item["title"]),
                        item["tg_url"],
                        feed_name,  # Empty for new feeds
                        feed_url,  # Empty for new feeds
                    ]
                )

        # Add items to remove (Miniflux only, but check if they will be moved from this category)
        for item in miniflux_items:
            if item["url"] not in matched_miniflux_urls:
                status_text = "[TO REMOVE]"

                # Check if this feed will be moved to another category instead of being removed
                if channel_assignments:
                    normalized_item_url = self._normalize_url_for_comparison(
                        item["url"]
                    )
                    for feed_url, (
                        planned_category,
                        _planned_folder,
                        _planned_channel,
                    ) in channel_assignments.items():
                        normalized_feed_url = self._normalize_url_for_comparison(
                            feed_url
                        )
                        if normalized_feed_url == normalized_item_url:
                            # This feed will be moved to another category
                            status_text = f"[MOVED OUT → {planned_category}]"
                            break

                # New column order: Action, Channel Name, Channel URL, Feed Name, Feed URL
                table_data.append(
                    [
                        status_text,
                        "",  # No channel name for feeds to be removed
                        "",  # No channel URL for feeds to be removed
                        remove_emojis(item["title"]),
                        item["url"],
                    ]
                )

        # Display table with tabulate (WIDE_CHARS_MODE enabled)
        headers = ["Action", "Channel Name", "Channel URL", "Feed Name", "Feed URL"]

        if table_data:
            # Sort table data by status priority and then by channel name
            def get_status_priority(status):
                """Get priority for status sorting"""
                if "[IN SYNC]" in status:
                    return 1
                elif "[MOVED IN" in status:
                    return 2
                elif "[MOVED OUT" in status:
                    return 3
                elif "[TO ADD]" in status:
                    return 4
                elif "[TO REMOVE]" in status:
                    return 5
                elif "[CONFLICT" in status:
                    return 6
                elif "[SKIPPED]" in status:
                    return 7
                elif "[ERROR]" in status:
                    return 8
                else:
                    return 9  # Unknown status

            def sort_key(row):
                """Sort key function: first by status priority, then by channel name"""
                status = row[0]  # Action column
                channel_name = row[1]  # Channel Name column
                # Remove emojis and normalize for sorting
                normalized_name = remove_emojis(channel_name).strip().lower()
                return (get_status_priority(status), normalized_name)

            # Sort the table data
            table_data.sort(key=sort_key)

            print(tabulate(table_data, headers=headers, tablefmt="simple_grid"))
        else:
            # Display empty table with headers only
            print(tabulate([], headers=headers, tablefmt="simple_grid"))

        # Count items by status (updated to account for moves)
        to_add = 0
        to_remove = 0
        to_move_out = 0  # Feeds moving out of this category
        to_move_in = 0  # Feeds moving into this category
        in_sync = 0

        # Count Telegram items
        for item in telegram_items:
            if (
                item["status"] == "normal"
                and item["rss_url"] not in matched_telegram_urls
            ):
                # Check if this is a real add or a move in
                is_move_in = False
                is_conflict = False
                if channel_assignments:
                    normalized_item_url = self._normalize_url_for_comparison(
                        item["rss_url"]
                    )
                    for feed_url, (
                        planned_category,
                        _planned_folder,
                        _planned_channel,
                    ) in channel_assignments.items():
                        normalized_feed_url = self._normalize_url_for_comparison(
                            feed_url
                        )
                        if normalized_feed_url == normalized_item_url:
                            if planned_category == miniflux_category:
                                # Check if it exists anywhere in Miniflux
                                all_feeds = (
                                    all_existing_feeds
                                    if all_existing_feeds
                                    else self.miniflux_client.get_feeds()
                                )
                                for existing_feed in all_feeds:
                                    if self._is_telegram_feed(existing_feed.feed_url):
                                        normalized_existing_url = (
                                            self._normalize_url_for_comparison(
                                                existing_feed.feed_url
                                            )
                                        )
                                        if (
                                            normalized_existing_url
                                            == normalized_item_url
                                        ):
                                            to_move_in += 1
                                            is_move_in = True
                                            break
                            else:
                                # This is a conflict - feed assigned to different category
                                is_conflict = True
                            break

                if not is_move_in and not is_conflict:
                    to_add += 1

        # Count matched items (check for moves)
        for tg_url, mf_url in matched_pairs:
            is_moving = False
            if channel_assignments:
                normalized_tg_url = self._normalize_url_for_comparison(tg_url)
                for feed_url, (
                    planned_category,
                    _planned_folder,
                    _planned_channel,
                ) in channel_assignments.items():
                    normalized_feed_url = self._normalize_url_for_comparison(feed_url)
                    if normalized_feed_url == normalized_tg_url:
                        if planned_category != miniflux_category:
                            to_move_out += 1
                            is_moving = True
                        break

            if not is_moving:
                in_sync += 1

        # Count Miniflux items (check for removes vs moves)
        for item in miniflux_items:
            if item["url"] not in matched_miniflux_urls:
                is_moving = False
                if channel_assignments:
                    normalized_item_url = self._normalize_url_for_comparison(
                        item["url"]
                    )
                    for feed_url, (
                        planned_category,
                        _planned_folder,
                        _planned_channel,
                    ) in channel_assignments.items():
                        normalized_feed_url = self._normalize_url_for_comparison(
                            feed_url
                        )
                        if normalized_feed_url == normalized_item_url:
                            # This is already counted in to_move_in for the target category
                            is_moving = True
                            break

                if not is_moving:
                    to_remove += 1

        skipped = len([item for item in telegram_items if item["status"] == "skipped"])
        errors = len([item for item in telegram_items if item["status"] == "error"])

        # Count planned title updates (if update_titles is enabled)
        to_update_titles = 0
        if update_titles:
            for feed in existing_feeds:
                if self._is_telegram_feed(feed.feed_url):
                    # Find matching required URL using case-insensitive comparison
                    matching_required_url = self._find_matching_url(
                        feed.feed_url, telegram_url_mapping
                    )
                    if matching_required_url:
                        channel = channel_by_url.get(matching_required_url)
                        if channel:
                            # Determine the title to use for the feed based on configuration
                            if self.config.sync.keep_emojis_in_titles:
                                # Keep emojis: use full channel title
                                new_feed_title = channel.title
                            else:
                                # Remove emojis: use cleaned channel title
                                new_feed_title = remove_emojis(channel.title)

                            # Compare with current feed title to see if update is needed
                            if new_feed_title != feed.title:
                                to_update_titles += 1

        # Display summary without emojis
        summary_parts = []
        if in_sync > 0:
            summary_parts.append(f"In sync: {in_sync}")
        if to_add > 0:
            summary_parts.append(f"To add: {to_add}")
        if to_remove > 0:
            summary_parts.append(f"To remove: {to_remove}")
        if to_move_out > 0:
            summary_parts.append(f"Moving out: {to_move_out}")
        if to_move_in > 0:
            summary_parts.append(f"Moving in: {to_move_in}")
        if to_update_titles > 0:
            summary_parts.append(f"To update titles: {to_update_titles}")
        if skipped > 0:
            summary_parts.append(f"Skipped: {skipped}")
        if errors > 0:
            summary_parts.append(f"Errors: {errors}")

        print(f"\nSummary: {' | '.join(summary_parts)}")

        # Show other (non-Telegram) feeds if any
        if other_feeds:
            print(f"\nOther feeds in category: {len(other_feeds)}")
            for feed_title in other_feeds[:5]:  # Show first 5
                print(f"   - {feed_title}")
            if len(other_feeds) > 5:
                print(f"   - ... and {len(other_feeds) - 5} more")

        print()

    def _display_overall_summary(self, result: SyncResult) -> None:
        """Display comprehensive summary of synchronization results across all folders.

        Creates a formatted summary showing the complete synchronization results
        including category-wise breakdowns, action counts, error reporting, and
        detailed information about moved feeds. Uses tabular formatting for
        clear presentation of results.

        The summary includes:
            - Category-wise action counts (added, removed, moved, updated)
            - Total action counts across all categories
            - Detailed list of moved feeds with source/target categories
            - Error summary with truncated error messages
            - Visual formatting with borders and highlighting

        Args:
            result: Overall synchronization result containing all actions and errors
        """
        # Skip all display output in quiet mode
        if self.quiet:
            return

        mode_text = "[DRY RUN] " if result.dry_run else ""

        print("\n" + "=" * 80)
        print(f"\033[1m{mode_text}OVERALL SUMMARY\033[0m")  # Bold header
        print("=" * 80)

        # Count actions by type
        total_added = len(result.added_feeds)
        total_removed = len(result.removed_feeds)
        total_updated = len(result.updated_titles)
        total_moved = len(result.moved_feeds)
        total_errors = len(result.errors)

        # Check if there are any actions to display
        if (
            total_added == 0
            and total_removed == 0
            and total_updated == 0
            and total_moved == 0
        ):
            print("✅ No actions performed - all folders are in sync")
        else:
            # Collect all categories
            all_categories = set()
            for action in (
                result.added_feeds
                + result.removed_feeds
                + result.updated_titles
                + result.moved_feeds
            ):
                all_categories.add(action.category_name)
                # Also add old categories for moved feeds
                if hasattr(action, "old_category") and action.old_category:
                    all_categories.add(action.old_category)

            # Prepare category breakdown table with totals row
            category_data = []

            # Add category rows
            for category in sorted(all_categories):
                category_added = len(
                    [a for a in result.added_feeds if a.category_name == category]
                )
                category_removed = len(
                    [a for a in result.removed_feeds if a.category_name == category]
                )
                category_updated = len(
                    [a for a in result.updated_titles if a.category_name == category]
                )
                category_moved_to = len(
                    [a for a in result.moved_feeds if a.category_name == category]
                )
                category_moved_from = len(
                    [
                        a
                        for a in result.moved_feeds
                        if getattr(a, "old_category", None) == category
                    ]
                )

                # Calculate net moved (moved to - moved from)
                category_moved_net = category_moved_to - category_moved_from

                # Only show categories that have actions
                if (
                    category_added > 0
                    or category_removed > 0
                    or category_updated > 0
                    or category_moved_net != 0
                ):
                    moved_display = ""
                    if category_moved_net > 0:
                        moved_display = f"+{category_moved_net}"
                    elif category_moved_net < 0:
                        moved_display = str(category_moved_net)
                    else:
                        moved_display = "-"

                    category_data.append(
                        [
                            category,
                            category_added if category_added > 0 else "-",
                            category_removed if category_removed > 0 else "-",
                            moved_display,
                            category_updated if category_updated > 0 else "-",
                        ]
                    )

            # Add separator line and totals row
            if category_data:
                # Add separator (empty row with dashes)
                category_data.append(["─" * 12, "─" * 5, "─" * 7, "─" * 6, "─" * 7])

                # Add totals row
                category_data.append(
                    [
                        "\033[1mTOTAL\033[0m",  # Bold "TOTAL"
                        f"\033[1m{total_added}\033[0m" if total_added > 0 else "-",
                        f"\033[1m{total_removed}\033[0m" if total_removed > 0 else "-",
                        f"\033[1m{total_moved}\033[0m" if total_moved > 0 else "-",
                        f"\033[1m{total_updated}\033[0m" if total_updated > 0 else "-",
                    ]
                )

                headers = [
                    "\033[1mCategory\033[0m",
                    "\033[1mAdded\033[0m",
                    "\033[1mRemoved\033[0m",
                    "\033[1mMoved\033[0m",
                    "\033[1mUpdated\033[0m",
                ]
                print(tabulate(category_data, headers=headers, tablefmt="simple_grid"))

        # Display detailed actions if there are any
        if total_moved > 0:
            print(f"\n📁 Moved feeds ({total_moved}):")
            for action in result.moved_feeds[:10]:  # Show first 10
                print(
                    f"   • {action.channel_title}: {action.old_category} → {action.category_name}"
                )
            if total_moved > 10:
                print(f"   ... and {total_moved - 10} more")

        # Display errors if any
        if total_errors > 0:
            print(f"\n⚠️  Errors encountered: {total_errors}")
            error_data = []
            for i, error in enumerate(result.errors[:5], 1):  # Show first 5 errors
                error_data.append(
                    [f"{i}.", error[:70] + "..." if len(error) > 70 else error]
                )

            print(
                tabulate(
                    error_data,
                    headers=["\033[1m#\033[0m", "\033[1mError Description\033[0m"],
                    tablefmt="simple_grid",
                )
            )

            if total_errors > 5:
                print(
                    f"\n... and {total_errors - 5} more errors (check logs for details)"
                )

        print("=" * 80)

    async def sync_folders(self, dry_run: bool = False) -> SyncResult:
        """Perform comprehensive two-stage folder synchronization with conflict resolution.

        This is the main synchronization method that orchestrates the complete process:

        Stage 1: Planning and Analysis
            - Retrieve channels from Telegram folders
            - Resolve conflicts when channels appear in multiple folders
            - Plan all necessary actions and validate configurations

        Stage 2: Execution
            - Create or update categories as needed
            - Add new feeds and update existing feed titles
            - Move feeds between categories when required
            - Remove feeds that are no longer needed (if configured)

        The method includes comprehensive error handling, detailed progress reporting,
        and supports both normal and dry-run modes for safe testing.

        Args:
            dry_run: If True, only show planned actions without making actual changes

        Returns:
            SyncResult object containing all performed actions, errors encountered,
            and operation metadata
        """
        # Determine if title updates should be performed based on configuration
        should_update_titles = not self.config.sync.disable_title_updates

        if dry_run:
            logger.info("Starting two-stage synchronization in DRY RUN mode")
        else:
            logger.info("Starting two-stage synchronization")

        if should_update_titles:
            logger.info("Title updates are enabled")
        else:
            logger.info("Title updates are disabled")

        added_feeds = []
        removed_feeds = []
        updated_titles = []
        moved_feeds = []
        errors = []

        try:
            # Get channels from Telegram
            try:
                async with TelegramClient(self.config.telegram) as tg_client:
                    folder_names = list(self.config.sync.folders.keys())
                    all_channels = await tg_client.get_channels_by_folders(folder_names)
            except Exception as e:
                error_msg = f"Failed to get channels from Telegram: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Return early with error, but not as critical failure
                result = SyncResult(
                    added_feeds=[],
                    removed_feeds=[],
                    updated_titles=[],
                    moved_feeds=[],
                    errors=errors,
                    dry_run=dry_run,
                )
                self._display_overall_summary(result)
                return result

            # Filter channels based on configuration
            all_channels = self._filter_channels(all_channels)

            # Stage 1: Plan synchronization and resolve conflicts
            logger.info("Stage 1: Planning synchronization and resolving conflicts...")
            channel_assignments, conflicts = await self._plan_synchronization(
                all_channels
            )

            # Report conflicts
            if conflicts:
                logger.info(f"Found {len(conflicts)} channels in multiple folders:")
                for conflict in conflicts:
                    logger.info(
                        f"  📁 '{conflict['channel'].title}' in folders: "
                        f"'{conflict['existing_folder']}' and '{conflict['new_folder']}' "
                        f"→ assigned to '{conflict['existing_category']}' (higher priority)"
                    )

            # Display detailed folder comparisons
            logger.debug("Displaying detailed folder comparisons...")

            # Get all existing feeds and categories once for comparisons
            try:
                all_existing_feeds = self.miniflux_client.get_feeds()
                all_categories = self.miniflux_client.get_categories()
            except Exception as e:
                error_msg = f"Failed to get initial data from Miniflux: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Return early with error, but not as critical failure
                result = SyncResult(
                    added_feeds=[],
                    removed_feeds=[],
                    updated_titles=[],
                    moved_feeds=[],
                    errors=errors,
                    dry_run=dry_run,
                )
                self._display_overall_summary(result)
                return result

            # Create category ID to name mapping for fast lookup
            category_id_to_name = {cat.id: cat.title for cat in all_categories}

            # Display comparison for each configured folder
            for folder_name, category_name in self.config.sync.folders.items():
                # Get channels for this folder
                folder_channels = [
                    ch for ch in all_channels if ch.folder_name == folder_name
                ]

                # Get existing feeds for this category using fast lookup
                category_feeds = []
                for feed in all_existing_feeds:
                    feed_category_name = category_id_to_name.get(feed.category_id)
                    if feed_category_name == category_name:
                        category_feeds.append(feed)

                # Display comparison table
                self._display_folder_comparison(
                    tg_folder=folder_name,
                    miniflux_category=category_name,
                    channels=folder_channels,
                    existing_feeds=category_feeds,
                    channel_assignments=channel_assignments,
                    all_existing_feeds=all_existing_feeds,
                    dry_run=dry_run,
                    update_titles=should_update_titles,
                )

            # Early optimization: check if any changes are needed
            telegram_feeds = [
                feed
                for feed in all_existing_feeds
                if self._is_telegram_feed(feed.feed_url)
            ]
            existing_feed_by_url = {
                self._normalize_url_for_comparison(feed.feed_url): feed
                for feed in telegram_feeds
            }
            category_name_to_id = {cat.title: cat.id for cat in all_categories}

            # Quick check for changes needed
            changes_needed = False
            new_categories_needed = set()

            for feed_url, (
                category_name,
                folder_name,
                channel,
            ) in channel_assignments.items():
                target_category_id = category_name_to_id.get(category_name)
                if target_category_id is None:
                    new_categories_needed.add(category_name)
                    changes_needed = True
                    continue

                normalized_url = self._normalize_url_for_comparison(feed_url)
                existing_feed = existing_feed_by_url.get(normalized_url)

                if existing_feed is None:
                    # New feed needed
                    changes_needed = True
                    break
                else:
                    # Check if move or title update needed
                    if existing_feed.category_id != target_category_id:
                        changes_needed = True
                        break

                    if should_update_titles:
                        new_feed_title = (
                            channel.title
                            if self.config.sync.keep_emojis_in_titles
                            else remove_emojis(channel.title)
                        )
                        if new_feed_title != existing_feed.title:
                            changes_needed = True
                            break

            # Check for feeds to remove
            if not changes_needed and self.config.sync.remove_absent_feeds:
                planned_urls = {
                    self._normalize_url_for_comparison(url)
                    for url in channel_assignments.keys()
                }
                configured_categories = set(self.config.sync.folders.values())
                configured_category_ids = {
                    cat.id
                    for cat in all_categories
                    if cat.title in configured_categories
                }

                for feed in telegram_feeds:
                    if feed.category_id in configured_category_ids:
                        normalized_feed_url = self._normalize_url_for_comparison(
                            feed.feed_url
                        )
                        if normalized_feed_url not in planned_urls:
                            changes_needed = True
                            break

            if not changes_needed:
                logger.info(
                    "Stage 2: No changes needed - skipping synchronization changes"
                )
            else:
                # Stage 2: Apply changes
                logger.info("Stage 2: Applying synchronization changes...")

                # Filter telegram feeds from already obtained feeds
                telegram_feeds = [
                    feed
                    for feed in all_existing_feeds
                    if self._is_telegram_feed(feed.feed_url)
                ]

                # Create URL mapping for case-insensitive comparison
                existing_feed_by_url = {}
                for feed in telegram_feeds:
                    normalized_url = self._normalize_url_for_comparison(feed.feed_url)
                    existing_feed_by_url[normalized_url] = feed

                # Create category name to ID mapping for fast lookup
                category_name_to_id = {cat.title: cat.id for cat in all_categories}

                # Process each planned assignment
                for feed_url, (
                    category_name,
                    folder_name,
                    channel,
                ) in channel_assignments.items():
                    try:
                        # Get or create target category using cached data
                        target_category_id = category_name_to_id.get(category_name)
                        if target_category_id is None:
                            # Category doesn't exist, create it
                            if dry_run:
                                logger.info(
                                    f"[DRY RUN] Would create category: {category_name}"
                                )
                                target_category_id = -1  # Dummy ID for dry run
                            else:
                                target_category = (
                                    self.miniflux_client.get_or_create_category(
                                        category_name
                                    )
                                )
                                target_category_id = target_category.id
                                # Update cache for future iterations
                                category_name_to_id[category_name] = target_category_id

                        # Check if feed already exists
                        normalized_url = self._normalize_url_for_comparison(feed_url)
                        existing_feed = existing_feed_by_url.get(normalized_url)

                        if existing_feed:
                            # Feed exists - check if it needs to be moved or title updated
                            needs_move = existing_feed.category_id != target_category_id

                            # Determine the title to use for the feed based on configuration
                            if self.config.sync.keep_emojis_in_titles:
                                new_feed_title = channel.title
                            else:
                                new_feed_title = remove_emojis(channel.title)

                            needs_title_update = (
                                should_update_titles
                                and new_feed_title != existing_feed.title
                            )

                            if needs_move:
                                # Move feed to correct category
                                if dry_run:
                                    logger.info(
                                        f"[DRY RUN] Would move feed '{existing_feed.title}' from category {existing_feed.category_id} to '{category_name}'"
                                    )
                                else:
                                    self.miniflux_client.update_feed_category(
                                        existing_feed.id, target_category_id
                                    )

                                action = SyncAction(
                                    action="move_category",
                                    channel_title=channel.title,
                                    feed_url=feed_url,
                                    category_name=category_name,
                                    old_category=self._get_category_name_by_id(
                                        existing_feed.category_id
                                    ),
                                )
                                moved_feeds.append(action)

                            if needs_title_update:
                                # Update feed title
                                if dry_run:
                                    logger.info(
                                        f"[DRY RUN] Would update feed title: '{existing_feed.title}' -> '{new_feed_title}'"
                                    )
                                else:
                                    self.miniflux_client.update_feed(
                                        existing_feed.id, new_feed_title
                                    )

                                action = SyncAction(
                                    action="update_title",
                                    channel_title=channel.title,
                                    feed_url=feed_url,
                                    category_name=category_name,
                                    old_title=existing_feed.title,
                                )
                                updated_titles.append(action)

                        else:
                            # Feed doesn't exist - create new one
                            if self.config.sync.keep_emojis_in_titles:
                                feed_title = channel.title
                            else:
                                feed_title = remove_emojis(channel.title)

                            if dry_run:
                                logger.info(
                                    f"[DRY RUN] Would add feed: {channel.title} -> {feed_url}"
                                )
                            else:
                                self.miniflux_client.create_feed(
                                    feed_url,
                                    target_category_id,
                                    validate=self.config.sync.validate_feeds,
                                    title=feed_title,
                                )

                            action = SyncAction(
                                action="add",
                                channel_title=channel.title,
                                feed_url=feed_url,
                                category_name=category_name,
                            )
                            added_feeds.append(action)

                    except ValueError as e:
                        # Feed URL validation failed or other ValueError
                        error_str = str(e)
                        if "Feed URL is not accessible" in error_str:
                            error_msg = (
                                f"Feed URL validation failed for {channel.title}: {e}"
                            )
                        elif "already exists but could not be found" in error_str:
                            error_msg = f"Feed exists but could not be located for {channel.title}: {e}"
                        elif "Bad request when creating feed" in error_str:
                            error_msg = (
                                f"Miniflux rejected feed for {channel.title}: {e}"
                            )
                        else:
                            error_msg = f"Feed validation/creation error for {channel.title}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                    except Exception as e:
                        # Other errors (Miniflux API, network, etc.)
                        if "503" in str(e) or "Service Unavailable" in str(e):
                            error_msg = f"RSS service unavailable for {channel.title} ({feed_url}): The RSS feed service is currently down"
                        elif "500" in str(e) or "Internal Server Error" in str(e):
                            error_msg = f"Miniflux server error for {channel.title} ({feed_url}): {e}"
                        else:
                            error_msg = f"Error processing feed {channel.title} ({feed_url}): {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                # Remove feeds that are no longer needed (if enabled)
                if self.config.sync.remove_absent_feeds:
                    planned_urls = {
                        self._normalize_url_for_comparison(url)
                        for url in channel_assignments.keys()
                    }

                    # Get list of category names that are configured for synchronization
                    configured_categories = set(self.config.sync.folders.values())

                    # Get category IDs for configured categories using already obtained data
                    configured_category_ids = set()
                    for category in all_categories:
                        if category.title in configured_categories:
                            configured_category_ids.add(category.id)

                    for feed in telegram_feeds:
                        # Only consider feeds that are in categories configured for synchronization
                        if feed.category_id not in configured_category_ids:
                            continue

                        normalized_feed_url = self._normalize_url_for_comparison(
                            feed.feed_url
                        )
                        if normalized_feed_url not in planned_urls:
                            try:
                                if dry_run:
                                    logger.info(
                                        f"[DRY RUN] Would remove feed: {feed.title} -> {feed.feed_url}"
                                    )
                                else:
                                    self.miniflux_client.delete_feed(feed.id)

                                action = SyncAction(
                                    action="remove",
                                    channel_title=feed.title,
                                    feed_url=feed.feed_url,
                                    category_name=self._get_category_name_by_id(
                                        feed.category_id
                                    ),
                                )
                                removed_feeds.append(action)

                            except Exception as e:
                                error_msg = f"Error removing feed {feed.feed_url}: {e}"
                                logger.error(error_msg)
                                errors.append(error_msg)

        except Exception as e:
            error_msg = f"Critical synchronization error: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        if dry_run:
            logger.info(
                f"Dry run completed. Would add: {len(added_feeds)}, would move: {len(moved_feeds)}, would remove: {len(removed_feeds)}, would update titles: {len(updated_titles)}, errors: {len(errors)}"
            )
        else:
            logger.info(
                f"Synchronization completed. Added: {len(added_feeds)}, moved: {len(moved_feeds)}, removed: {len(removed_feeds)}, updated titles: {len(updated_titles)}, errors: {len(errors)}"
            )

        result = SyncResult(
            added_feeds=added_feeds,
            removed_feeds=removed_feeds,
            updated_titles=updated_titles,
            moved_feeds=moved_feeds,
            errors=errors,
            dry_run=dry_run,
        )

        self._display_overall_summary(result)

        return result
