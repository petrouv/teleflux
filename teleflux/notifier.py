"""Telegram notification module.

This module provides functionality for sending formatted notifications about
synchronization results to Telegram. It handles message formatting, length
limits, and provides detailed summaries of synchronization operations.

The notifier creates structured messages with action summaries, error reporting,
and automatic message splitting for long notifications. It integrates with the
main synchronization process to provide real-time feedback on operations.

Key features:
    - Formatted sync result notifications
    - Automatic message length handling and splitting
    - Detailed action summaries (added, removed, updated, moved feeds)
    - Error reporting with truncation for readability
    - Configurable notification settings (enable/disable, no-changes notifications)
    - Message length optimization for Telegram limits
"""

from __future__ import annotations

import logging

from .config import Config
from .sync import SyncResult
from .telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram notification handler for synchronization results.

    Manages the creation and sending of formatted notifications about
    synchronization operations to Telegram. Handles message formatting,
    length constraints, and provides configurable notification behavior.
    """

    def __init__(self, config: Config):
        """Initialize Telegram notifier.

        Args:
            config: Full application configuration containing Telegram settings
                   and notification preferences
        """
        self.config = config

    def _format_sync_message(self, result: SyncResult) -> str:
        """Format synchronization result into a structured Telegram message.

        Creates a comprehensive, readable message summarizing all synchronization
        actions including feeds added, removed, updated, moved, and any errors.
        Handles message length optimization and item truncation for readability.

        Args:
            result: Synchronization result containing all performed actions and errors

        Returns:
            Formatted message string ready for sending to Telegram
        """
        lines = []

        # Telegram message length considerations - prevent overly long messages
        MAX_ITEMS_TO_SHOW = 20  # Limit detailed items to prevent very long messages
        MAX_ERROR_LENGTH = 200  # Limit individual error message length

        # Status summary first - provides immediate overview
        if (
            not result.added_feeds
            and not result.removed_feeds
            and not result.updated_titles
            and not result.moved_feeds
            and not result.errors
        ):
            if result.dry_run:
                lines.append("Sync Status: No changes would be made")
            else:
                lines.append("Sync Status: No changes required")
        elif not result.errors:
            if result.dry_run:
                lines.append("Sync Status: Dry run completed successfully")
            else:
                lines.append("Sync Status: Synchronization completed successfully")
        else:
            if result.dry_run:
                lines.append("Sync Status: ⚠️ Dry run completed with errors")
            else:
                lines.append("Sync Status: ⚠️ Synchronization completed with errors")

        # Add empty line after status if there's content to follow
        has_content = (
            result.added_feeds
            or result.removed_feeds
            or result.updated_titles
            or result.moved_feeds
            or result.errors
        )
        if has_content:
            lines.append("")

        # Added feeds section
        if result.added_feeds:
            action_text = "Would add feeds" if result.dry_run else "Added feeds"
            lines.append(f"**{action_text}** ({len(result.added_feeds)}):")

            # Show limited number of feeds to prevent message overflow
            feeds_to_show = result.added_feeds[:MAX_ITEMS_TO_SHOW]
            for action in feeds_to_show:
                category_text = (
                    f" → {action.category_name}"
                    if hasattr(action, "category_name") and action.category_name
                    else ""
                )
                lines.append(f"  • {action.channel_title}{category_text}")

            # Show summary if there are more feeds than displayed
            if len(result.added_feeds) > MAX_ITEMS_TO_SHOW:
                remaining = len(result.added_feeds) - MAX_ITEMS_TO_SHOW
                lines.append(f"  • ... and {remaining} more")
            lines.append("")

        # Removed feeds section
        if result.removed_feeds:
            action_text = "Would remove feeds" if result.dry_run else "Removed feeds"
            lines.append(f"**{action_text}** ({len(result.removed_feeds)}):")

            # Show limited number of feeds
            feeds_to_show = result.removed_feeds[:MAX_ITEMS_TO_SHOW]
            for action in feeds_to_show:
                category_text = (
                    f" ← {action.category_name}"
                    if hasattr(action, "category_name") and action.category_name
                    else ""
                )
                lines.append(f"  • {action.channel_title}{category_text}")

            # Show summary if there are more feeds
            if len(result.removed_feeds) > MAX_ITEMS_TO_SHOW:
                remaining = len(result.removed_feeds) - MAX_ITEMS_TO_SHOW
                lines.append(f"  • ... and {remaining} more")
            lines.append("")

        # Updated titles section
        if result.updated_titles:
            action_text = "Would update titles" if result.dry_run else "Updated titles"
            lines.append(f"**{action_text}** ({len(result.updated_titles)}):")

            # Show limited number of feeds with before/after titles
            feeds_to_show = result.updated_titles[:MAX_ITEMS_TO_SHOW]
            for action in feeds_to_show:
                old_title = getattr(action, "old_title", "Unknown")
                lines.append(f"  • {old_title} → {action.channel_title}")

            # Show summary if there are more feeds
            if len(result.updated_titles) > MAX_ITEMS_TO_SHOW:
                remaining = len(result.updated_titles) - MAX_ITEMS_TO_SHOW
                lines.append(f"  • ... and {remaining} more")
            lines.append("")

        # Moved feeds section
        if result.moved_feeds:
            action_text = "Would move feeds" if result.dry_run else "Moved feeds"
            lines.append(f"**{action_text}** ({len(result.moved_feeds)}):")

            # Show limited number of feeds with category movement
            feeds_to_show = result.moved_feeds[:MAX_ITEMS_TO_SHOW]
            for action in feeds_to_show:
                old_category = getattr(action, "old_category", "Unknown")
                lines.append(f"  • {action.channel_title}")
                lines.append(f"    {old_category} → {action.category_name}")

            # Show summary if there are more feeds
            if len(result.moved_feeds) > MAX_ITEMS_TO_SHOW:
                remaining = len(result.moved_feeds) - MAX_ITEMS_TO_SHOW
                lines.append(f"  • ... and {remaining} more")
            lines.append("")

        # Errors section with truncation for readability
        if result.errors:
            lines.append(f"**Errors** ({len(result.errors)}):")

            # Show limited number of errors
            errors_to_show = result.errors[:MAX_ITEMS_TO_SHOW]
            for error in errors_to_show:
                # Truncate individual error messages to prevent overwhelming output
                error_text = (
                    error
                    if len(error) <= MAX_ERROR_LENGTH
                    else f"{error[: MAX_ERROR_LENGTH - 3]}..."
                )
                lines.append(f"  • {error_text}")

            # Show summary if there are more errors
            if len(result.errors) > MAX_ITEMS_TO_SHOW:
                remaining = len(result.errors) - MAX_ITEMS_TO_SHOW
                lines.append(f"  • ... and {remaining} more")
            lines.append("")

        # Summary section with totals (only if there are changes or errors)
        total_changes = (
            len(result.added_feeds)
            + len(result.removed_feeds)
            + len(result.updated_titles)
            + len(result.moved_feeds)
        )
        if total_changes > 0 or result.errors:
            summary_parts = []
            if result.added_feeds:
                summary_parts.append(f"Added: {len(result.added_feeds)}")
            if result.removed_feeds:
                summary_parts.append(f"Removed: {len(result.removed_feeds)}")
            if result.updated_titles:
                summary_parts.append(f"Updated: {len(result.updated_titles)}")
            if result.moved_feeds:
                summary_parts.append(f"Moved: {len(result.moved_feeds)}")
            if result.errors:
                summary_parts.append(f"Errors: {len(result.errors)}")

            mode_text = " (DRY RUN)" if result.dry_run else ""
            lines.append(f"**Summary**: {' | '.join(summary_parts)}{mode_text}")

        return "\n".join(lines)

    async def send_sync_notification(self, result: SyncResult) -> None:
        """Send synchronization results notification to Telegram.

        Formats and sends a notification message about synchronization results.
        Respects configuration settings for notification behavior, including
        whether to send notifications when no changes are made.

        Args:
            result: Synchronization result containing actions performed and any errors

        Note:
            This method will not raise exceptions on notification failures to avoid
            affecting the main synchronization process. Errors are logged instead.
        """
        # Check if we should skip notification for "no changes" case
        total_changes = (
            len(result.added_feeds)
            + len(result.removed_feeds)
            + len(result.updated_titles)
            + len(result.moved_feeds)
        )
        if (
            total_changes == 0
            and not result.errors
            and not self.config.sync.notify_no_changes
        ):
            logger.info(
                "Skipping notification: no changes and notify_no_changes is disabled"
            )
            return

        message = self._format_sync_message(result)

        try:
            async with TelegramClient(self.config.telegram) as tg_client:
                await tg_client.send_notification(message)
            if result.dry_run:
                logger.info("Dry run notification sent")
            else:
                logger.info("Synchronization notification sent")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            # Don't raise exception as this is not critical for main operation
            # Notification failure should not affect synchronization success
