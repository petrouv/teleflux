"""
Telegram API client module using Pyrogram

This module implements a mixed approach using both high-level and low-level Pyrogram APIs
for optimal performance and functionality:

HIGH-LEVEL API USAGE (pyrogram.Client methods):
- get_dialogs(): Used for general dialog enumeration when we need to process all dialogs
- send_message(): Used for sending notifications - simpler and more reliable
- get_users(): Used for getting user information - handles user/bot detection automatically

LOW-LEVEL API USAGE (pyrogram.raw functions):
- GetDialogFilters(): Used to get folder information - NOT available in high-level API
- GetPeerDialogs(): Used to get channels from specific folders with batching - much faster
  than iterating through all dialogs for large accounts (1000+ channels)

PERFORMANCE CONSIDERATIONS:
- GetPeerDialogs with batching (100 peers per request) is 10-50x faster than get_dialogs()
  for accounts with many channels
- Raw API allows direct access to folder structure and peer relationships
- High-level API provides better error handling and type safety for simple operations

RATIONALE FOR MIXED APPROACH:
1. Some functionality (folders, peer dialogs) is only available via Raw API
2. Simple operations (send message, get users) are more reliable via high-level API
3. Performance-critical operations benefit from Raw API optimizations
4. Fallback mechanisms ensure robustness when Raw API changes

This approach maximizes both performance and maintainability while providing
access to all required Telegram features.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import platform
import time
from dataclasses import dataclass
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Chat, Dialog

from . import __version__
from .config import TelegramConfig

logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    """Base exception for Telegram API errors"""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        method_name: str = "",
    ):
        """Initialize Telegram API error.

        Args:
            message: Human-readable error message
            original_error: The underlying exception that caused this error
            method_name: Name of the API method that failed
        """
        self.message = message
        self.original_error = original_error
        self.method_name = method_name
        super().__init__(self.message)


class TelegramAPIHandler:
    """Unified handler for both high-level and low-level Telegram API calls"""

    @staticmethod
    async def handle_api_call(
        func, *args, method_name: str = "", max_retries: int = 3, **kwargs
    ):
        """
        Handle API calls with unified error handling and retry logic

        Args:
            func: Function to call (high-level or low-level)
            *args: Positional arguments for the function
            method_name: Name of the method for logging
            max_retries: Maximum number of retries for FloodWait
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            TelegramAPIError: Unified error for all API failures
        """
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)

            except FloodWait as e:
                wait_time = e.value

                if attempt < max_retries - 1:
                    logger.warning(
                        f"FloodWait in {method_name}: {wait_time}s. Waiting as required by Telegram... (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"FloodWait on final attempt in {method_name}: {wait_time}s. Giving up."
                    logger.error(error_msg)
                    raise TelegramAPIError(error_msg, e, method_name)

            except RPCError as e:
                error_msg = f"RPC error in {method_name}: {e.MESSAGE} (code: {e.CODE})"
                logger.error(error_msg)
                raise TelegramAPIError(error_msg, e, method_name)

            except Exception as e:
                error_msg = (
                    f"Unexpected error in {method_name}: {type(e).__name__}: {e}"
                )
                logger.error(error_msg)
                raise TelegramAPIError(error_msg, e, method_name)

        raise TelegramAPIError(
            f"Max retries ({max_retries}) reached in {method_name}",
            method_name=method_name,
        )


def _get_system_info() -> str:
    """
    Get system information for User-Agent

    Returns:
        str: System information string
    """
    try:
        system = platform.system()
        release = platform.release()
        machine = platform.machine()

        # Format system info
        if system == "Darwin":
            # macOS
            mac_version = platform.mac_ver()[0]
            return f"macOS {mac_version} ({machine})"
        elif system == "Linux":
            # Linux
            return f"Linux {release} ({machine})"
        elif system == "Windows":
            # Windows
            return f"Windows {release} ({machine})"
        else:
            # Other systems
            return f"{system} {release} ({machine})"
    except Exception:
        # Fallback if platform detection fails
        return "Unknown System"


@dataclass
class TelegramChannel:
    """Telegram channel information container.

    Attributes:
        id: Unique channel identifier (Telegram channel ID)
        username: Public channel username (None for private channels)
        title: Human-readable channel title
        is_private: Whether the channel is private (requires invitation)
        folder_name: Name of the Telegram folder containing this channel
        channel_hash: Secret hash for private channel access (if available)
    """

    id: int
    username: str | None
    title: str
    is_private: bool
    folder_name: str | None
    channel_hash: str | None = None


@dataclass
class TelegramFolder:
    """Telegram folder information container.

    Attributes:
        id: Unique folder identifier (None for Main folder)
        name: Human-readable folder name
        channel_count: Number of channels in this folder
    """

    id: int | None
    name: str
    channel_count: int


class TelegramClient:
    """Telegram API client"""

    def __init__(self, config: TelegramConfig):
        """Initialize Telegram API client.

        Args:
            config: Telegram configuration containing API credentials and settings
        """
        self.config = config
        self.client: Client | None = None

    async def __aenter__(self):
        """Async context manager - enter"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager - exit"""
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to Telegram API"""
        session_path = Path(self.config.session_file)

        # Get system information
        system_info = _get_system_info()
        app_version = f"Teleflux {__version__}"

        self.client = Client(
            name=str(session_path.stem),
            api_id=int(self.config.api_id),
            api_hash=self.config.api_hash,
            workdir=str(session_path.parent),
            app_version=app_version,
            system_version=system_info,
        )

        logger.info(
            f"Connecting to Telegram API with {app_version} on {system_info}..."
        )
        await self.client.start()
        logger.info("Successfully connected to Telegram API")

    async def disconnect(self) -> None:
        """Disconnect from Telegram API"""
        if self.client:
            logger.info("Disconnecting from Telegram API...")
            await self.client.stop()
            logger.info("Disconnected from Telegram API")

    async def get_all_folders(self) -> list[TelegramFolder]:
        """
        Get list of all folders with channel counts

        MIXED API APPROACH:
        - Uses Raw API (GetDialogFilters) to get folder structure - NOT available in high-level API
        - Uses high-level API (get_dialogs) to enumerate and count channels - more reliable for iteration
        - Combines both approaches for optimal performance and functionality

        PERFORMANCE RATIONALE:
        - Raw API provides direct access to folder metadata and peer relationships
        - High-level API handles dialog iteration with proper error handling and type conversion
        - This combination is faster than pure high-level enumeration for large accounts

        Returns:
            List[TelegramFolder]: List of folders with channel counts
        """
        if not self.client:
            raise RuntimeError("Client not connected")

        # Get folder information with channel mappings
        folder_info = await self._get_dialog_filters_with_peers()

        # Count channels by folder
        folder_stats: dict[str, int] = {}
        folder_ids: dict[str, int | None] = {}

        # Create a mapping from channel_id to folder info
        channel_to_folder: dict[int, dict] = {}
        for folder_name, folder_data in folder_info.items():
            # Extract channel IDs from include_peers
            for peer in folder_data["include_peers"]:
                channel_id = (
                    peer.user_id
                    if hasattr(peer, "user_id")
                    else (
                        peer.channel_id if hasattr(peer, "channel_id") else peer.chat_id
                    )
                )
                channel_to_folder[channel_id] = {
                    "id": folder_data["id"],
                    "name": folder_data["title"],
                }

        logger.info(
            f"Found {len(folder_info)} dialog filters with {len(channel_to_folder)} channel mappings"
        )

        # Get all dialogs and count channels by folder
        dialog_count = 0
        channels_found = 0
        supergroups_skipped = 0

        async for dialog in self.client.get_dialogs():
            dialog: Dialog
            chat: Chat = dialog.chat
            dialog_count += 1

            # Check if it's a channel or supergroup
            if chat.type.value not in ["channel", "supergroup"]:
                continue

            # Use raw object attributes to distinguish channels from supergroups
            try:
                # Access the raw object to get broadcast/megagroup flags
                if hasattr(chat, "_raw") and chat._raw:
                    raw_chat = chat._raw

                    # Check if it's a supergroup (megagroup=True) - skip these
                    if hasattr(raw_chat, "megagroup") and raw_chat.megagroup:
                        supergroups_skipped += 1
                        logger.info(
                            f"Skipping supergroup: {chat.title} (ID: {chat.id})"
                        )
                        continue

                    # Check if it's a broadcast channel (broadcast=True) - keep these
                    if hasattr(raw_chat, "broadcast") and raw_chat.broadcast:
                        # This is a real channel, proceed
                        pass
                    else:
                        # If neither broadcast nor megagroup flags are clear, skip to be safe
                        logger.info(
                            f"Skipping chat with unclear type: {chat.title} (ID: {chat.id})"
                        )
                        continue
                else:
                    # If we can't access raw object, fall back to type check
                    # Only proceed if type is explicitly "channel"
                    if chat.type.value != "channel":
                        logger.info(
                            f"Skipping non-channel: {chat.title} (ID: {chat.id}, type: {chat.type.value})"
                        )
                        continue

            except Exception as e:
                logger.warning(
                    f"Failed to check chat type for {chat.title} (ID: {chat.id}): {e}"
                )
                # If we can't determine the type, skip this chat to be safe
                continue

            channels_found += 1

            # Determine folder using channel mapping
            channel_id = chat.id

            # Convert negative channel IDs to positive (Telegram API quirk)
            if channel_id < 0:
                # Remove the -100 prefix for supergroups/channels
                if str(channel_id).startswith("-100"):
                    channel_id = int(str(channel_id)[4:])
                else:
                    channel_id = abs(channel_id)

            if channel_id in channel_to_folder:
                # Found in a specific folder
                folder_info_item = channel_to_folder[channel_id]
                folder_name = folder_info_item["name"]
                folder_id = folder_info_item["id"]

                if channels_found <= 5:
                    logger.debug(
                        f"Channel {chat.title} is in folder '{folder_name}' (folder_id: {folder_id})"
                    )
            else:
                # Not in any specific folder, goes to Main
                folder_name = "Main"
                folder_id = None

                if channels_found <= 5:
                    logger.debug(
                        f"Channel {chat.title} is in Main folder (not in any filter)"
                    )

            # Count channels in folder
            if folder_name in folder_stats:
                folder_stats[folder_name] += 1
            else:
                # First channel in this folder
                folder_stats[folder_name] = 1
                folder_ids[folder_name] = folder_id

        logger.info(
            f"Analyzed {dialog_count} total dialogs, found {channels_found} channels (skipped {supergroups_skipped} supergroups)"
        )

        if supergroups_skipped > 0:
            logger.info(
                f"Filtered out {supergroups_skipped} supergroups (megagroups) - only broadcast channels are synchronized"
            )

        # Create folder objects only for folders that have channels
        folders = []
        for folder_name, count in folder_stats.items():
            folder = TelegramFolder(
                id=folder_ids[folder_name], name=folder_name, channel_count=count
            )
            folders.append(folder)

        # Sort folders: Main first, then by name
        folders.sort(key=lambda f: (f.name != "Main", str(f.name)))

        logger.debug(
            f"Found {len(folders)} folders with {sum(f.channel_count for f in folders)} total channels"
        )
        return folders

    async def _get_dialog_filters(self) -> dict[int, str]:
        """
        Get dialog filters (folders) using raw API

        Returns:
            Dict[int, str]: Mapping of folder_id to folder_name
        """
        folder_info = {}

        try:
            from pyrogram.raw import functions

            logger.info("Getting dialog filters using raw API...")

            # Get dialog filters
            result = await self.client.invoke(functions.messages.GetDialogFilters())

            logger.info(f"GetDialogFilters result type: {type(result)}")

            # The result is a List object, not an object with 'filters' attribute
            # We need to iterate directly over the result
            if result and len(result) > 0:
                logger.info(f"Found {len(result)} dialog filters")

                for i, filter_obj in enumerate(result):
                    logger.debug(f"Filter {i}: {type(filter_obj)}")

                    # Check if it's a regular dialog filter or chatlist (skip default)
                    class_name = filter_obj.__class__.__name__

                    # Skip default filters (All Chats, Unread, etc.)
                    if class_name in ["DialogFilterDefault", "DialogFilterChatlist"]:
                        logger.debug(f"[SKIP] Skipping default filter: {class_name}")
                        continue

                    if hasattr(filter_obj, "id") and hasattr(filter_obj, "title"):
                        folder_id = filter_obj.id
                        folder_title = filter_obj.title

                        if class_name in ["DialogFilter", "DialogFilterChatlist"]:
                            folder_info[folder_id] = folder_title
                            logger.info(
                                f"[OK] Added folder: ID={folder_id}, Title='{folder_title}', Type={class_name}"
                            )
                        else:
                            logger.debug(
                                f"[SKIP] Skipping filter with unknown class: {class_name}"
                            )
                    else:
                        logger.debug(
                            f"[SKIP] Skipping filter without id/title: {class_name}"
                        )
            else:
                logger.info("[WARNING] No dialog filters found in result")

        except Exception as e:
            logger.error(f"[ERROR] Failed to get dialog filters: {e}")

        logger.info(f"Final folder_info: {folder_info}")
        return folder_info

    async def _get_dialog_filters_with_peers(self) -> dict[str, dict]:
        """
        Get dialog filters with their include_peers information

        Uses Raw API (GetDialogFilters) for optimal performance and access to folder structure.
        Includes fallback to high-level API if Raw API fails.

        Returns:
            Dict[str, Dict]: Mapping of folder_name to folder info with peers
        """
        folder_info = {}

        try:
            from pyrogram.raw import functions

            logger.debug("Getting dialog filters with peers using Raw API...")

            # Use unified error handling for Raw API call
            result = await TelegramAPIHandler.handle_api_call(
                self.client.invoke,
                functions.messages.GetDialogFilters(),
                method_name="GetDialogFilters",
                max_retries=3,
            )

            if result and len(result) > 0:
                logger.debug(f"Raw API returned {len(result)} dialog filters")

                for filter_obj in result:
                    class_name = filter_obj.__class__.__name__

                    # Skip default filters (All Chats, Unread, etc.)
                    if class_name in ["DialogFilterDefault", "DialogFilterChatlist"]:
                        logger.debug(f"[SKIP] Skipping default filter: {class_name}")
                        continue

                    if hasattr(filter_obj, "id") and hasattr(filter_obj, "title"):
                        folder_id = filter_obj.id
                        folder_title = filter_obj.title

                        if class_name in ["DialogFilter", "DialogFilterChatlist"]:
                            # Store include_peers directly
                            include_peers = []
                            if hasattr(filter_obj, "include_peers"):
                                include_peers = filter_obj.include_peers

                            # Store exclude_peers as well for debugging
                            exclude_peers = []
                            if hasattr(filter_obj, "exclude_peers"):
                                exclude_peers = filter_obj.exclude_peers

                            folder_info[folder_title] = {
                                "id": folder_id,
                                "title": folder_title,
                                "type": class_name,
                                "include_peers": include_peers,
                                "exclude_peers": exclude_peers,
                            }

                            logger.debug(
                                f"Folder '{folder_title}' (ID: {folder_id}) has {len(include_peers)} include_peers and {len(exclude_peers)} exclude_peers"
                            )
            else:
                logger.warning("No dialog filters found in Raw API result")

        except TelegramAPIError as e:
            logger.error(f"Raw API failed for GetDialogFilters: {e.message}")

            # Fallback: Try to extract folder information from high-level API
            logger.info("Attempting fallback to high-level API for folder detection...")
            try:
                folder_info = await self._fallback_get_folders_from_dialogs()
                if folder_info:
                    logger.info(
                        f"Fallback successful: found {len(folder_info)} folders via high-level API"
                    )
                else:
                    logger.warning(
                        "Fallback failed: no folders detected via high-level API"
                    )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                # Return empty dict - caller will handle gracefully

        except Exception as e:
            logger.error(f"Unexpected error in _get_dialog_filters_with_peers: {e}")
            # Try fallback as last resort
            try:
                folder_info = await self._fallback_get_folders_from_dialogs()
            except Exception:
                pass  # Return empty dict

        logger.debug(f"Final folder_info: {len(folder_info)} folders found")
        return folder_info

    async def _fallback_get_folders_from_dialogs(self) -> dict[str, dict]:
        """
        Fallback method to detect folders using high-level API

        This method attempts to infer folder structure by analyzing dialog patterns
        when Raw API is unavailable. Limited functionality compared to Raw API.

        Returns:
            Dict[str, Dict]: Basic folder info with empty include_peers (fallback mode)
        """
        logger.info("Using fallback folder detection via high-level API...")

        # In fallback mode, we can't get actual folder structure
        # We'll create a single "Main" folder containing all channels
        fallback_folder_info = {
            "Main": {
                "id": None,
                "title": "Main",
                "type": "Fallback",
                "include_peers": [],  # Will be populated by caller using get_dialogs()
                "exclude_peers": [],
            }
        }

        logger.warning(
            "Fallback mode: Only 'Main' folder available. Folder-specific synchronization disabled."
        )
        logger.warning(
            "To restore full folder functionality, check your Telegram API credentials and connection."
        )

        return fallback_folder_info

    async def get_channels_by_folders(
        self, folder_names: list[str]
    ) -> list[TelegramChannel]:
        """
        Get list of channels from specified folders using optimized GetPeerDialogs with pagination

        Uses Raw API (GetPeerDialogs) for optimal performance with batching.
        Includes fallback to high-level API if Raw API fails.

        Args:
            folder_names: List of folder names to search for channels

        Returns:
            List[TelegramChannel]: List of channels
        """
        if not self.client:
            raise RuntimeError("Client not connected")

        channels = []

        logger.info(f"Getting channels from folders: {folder_names}")

        # Get folder information with channel mappings
        folder_info = await self._get_dialog_filters_with_peers()

        # Check if we're in fallback mode (no Raw API access)
        is_fallback_mode = any(
            folder_data.get("type") == "Fallback"
            for folder_data in folder_info.values()
        )

        if is_fallback_mode:
            logger.info(
                "Operating in fallback mode - using high-level API for all folders"
            )
            return await self._fallback_get_channels_from_all_dialogs(folder_names)

        # Process each folder separately with pagination (Raw API mode)
        for folder_name in folder_names:
            if folder_name not in folder_info:
                logger.warning(f"Folder '{folder_name}' not found")
                continue

            peers = folder_info[folder_name]["include_peers"]
            logger.info(f"Processing folder: '{folder_name}' with {len(peers)} peers")

            if not peers:
                logger.info(f"No peers found in folder '{folder_name}'")
                continue

            # Split peers into batches of 100 (GetPeerDialogs limit)
            batch_size = 100
            total_batches = (len(peers) + batch_size - 1) // batch_size

            if total_batches > 1:
                logger.info(
                    f"Splitting {len(peers)} peers into {total_batches} batches of max {batch_size} peers each"
                )

            folder_channels = []

            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(peers))
                batch_peers = peers[start_idx:end_idx]

                if total_batches > 1:
                    logger.info(
                        f"Processing batch {batch_num + 1}/{total_batches}: peers {start_idx}-{end_idx - 1} ({len(batch_peers)} peers)"
                    )

                try:
                    from pyrogram.raw import functions

                    start_time = time.time()

                    # Use unified error handling for Raw API call
                    peer_dialogs_result = await TelegramAPIHandler.handle_api_call(
                        self.client.invoke,
                        functions.messages.GetPeerDialogs(peers=batch_peers),
                        method_name=f"GetPeerDialogs_batch_{batch_num + 1}",
                        max_retries=3,
                    )

                    api_time = time.time() - start_time

                    if total_batches > 1:
                        logger.info(
                            f"Batch {batch_num + 1} returned {len(peer_dialogs_result.dialogs)} dialogs ({api_time:.2f}s)"
                        )

                    # Process results for this batch
                    batch_channels = await self._process_peer_dialogs_result(
                        peer_dialogs_result, folder_name
                    )
                    folder_channels.extend(batch_channels)

                    # Add small delay between batches to avoid rate limiting
                    if batch_num < total_batches - 1:  # Don't wait after the last batch
                        await asyncio.sleep(0.5)

                except TelegramAPIError as e:
                    logger.error(
                        f"Raw API failed for batch {batch_num + 1} in folder '{folder_name}': {e.message}"
                    )

                    # Try fallback for this specific batch
                    logger.info(f"Attempting fallback for batch {batch_num + 1}...")
                    try:
                        fallback_channels = (
                            await self._fallback_get_channels_from_peers(
                                batch_peers, folder_name
                            )
                        )
                        folder_channels.extend(fallback_channels)
                        logger.info(
                            f"Fallback successful for batch {batch_num + 1}: found {len(fallback_channels)} channels"
                        )
                    except Exception as fallback_error:
                        logger.error(
                            f"Fallback also failed for batch {batch_num + 1}: {fallback_error}"
                        )
                        # Continue with next batch
                        continue

                except Exception as e:
                    logger.error(
                        f"Unexpected error in batch {batch_num + 1} for folder '{folder_name}': {e}"
                    )
                    # Continue with next batch instead of failing completely
                    continue

            if total_batches > 1:
                logger.info(
                    f"Folder '{folder_name}' total: {len(folder_channels)} channels from {total_batches} batches"
                )
            else:
                logger.info(
                    f"Found {len(folder_channels)} channels in folder '{folder_name}'"
                )

            channels.extend(folder_channels)

        logger.info(
            f"Found {len(channels)} total channels across all specified folders"
        )
        return channels

    async def _process_peer_dialogs_result(
        self, peer_dialogs_result, folder_name: str
    ) -> list[TelegramChannel]:
        """
        Process the result from GetPeerDialogs API call

        Args:
            peer_dialogs_result: Result from GetPeerDialogs
            folder_name: Name of the folder being processed

        Returns:
            List[TelegramChannel]: List of channels found in the result
        """
        channels = []

        # Process results for this folder
        missing_chats = 0
        processed_count = 0
        users_skipped = 0
        bots_skipped = 0
        supergroups_skipped = 0
        groups_skipped = 0
        channels_added = 0
        other_skipped = 0

        for dialog in peer_dialogs_result.dialogs:
            # Count every dialog that enters the loop
            processed_count += 1

            # Find corresponding chat
            chat = None
            peer_id = None
            peer_type = None

            if hasattr(dialog.peer, "channel_id"):
                peer_id = dialog.peer.channel_id
                peer_type = "channel"
            elif hasattr(dialog.peer, "chat_id"):
                peer_id = dialog.peer.chat_id
                peer_type = "chat"
            elif hasattr(dialog.peer, "user_id"):
                peer_id = dialog.peer.user_id
                peer_type = "user"

            # Skip users - we only process channels and groups
            if peer_type == "user":
                # Try to get user info to determine if it's a bot
                try:
                    user = await self.client.get_users(peer_id)
                    if user.is_bot:
                        bots_skipped += 1
                        user_identifier = (
                            f"@{user.username}"
                            if user.username
                            else f"'{user.first_name or 'Unknown'}'"
                        )
                        logger.debug(
                            f"Skipping bot: {user_identifier} from folder '{folder_name}' - bots are not synchronized"
                        )
                    else:
                        users_skipped += 1
                        user_identifier = (
                            f"@{user.username}"
                            if user.username
                            else f"'{user.first_name or 'Unknown'}'"
                        )
                        logger.debug(
                            f"Skipping private chat: {user_identifier} from folder '{folder_name}' - private chats are not synchronized"
                        )
                except Exception:
                    # If we can't get user info, count as user
                    users_skipped += 1
                    logger.debug(
                        f"Skipping private chat: ID {peer_id} from folder '{folder_name}' - private chats are not synchronized"
                    )
                continue

            # Find the chat object
            for c in peer_dialogs_result.chats:
                if c.id == peer_id:
                    chat = c
                    break

            if not chat:
                # Try to find chat with ID conversion
                converted_ids = []
                if peer_id:
                    # Try different ID conversions
                    converted_ids = [
                        peer_id,
                        -peer_id,
                        int(f"-100{peer_id}"),
                        (
                            int(str(peer_id)[4:])
                            if str(peer_id).startswith("-100")
                            else None
                        ),
                    ]
                    converted_ids = [cid for cid in converted_ids if cid is not None]

                    for converted_id in converted_ids:
                        for c in peer_dialogs_result.chats:
                            if c.id == converted_id:
                                chat = c
                                logger.debug(
                                    f"Found chat using ID conversion: {peer_id} -> {converted_id}"
                                )
                                break
                        if chat:
                            break

                if not chat:
                    missing_chats += 1
                    logger.debug(
                        f"Chat not found for peer_id {peer_id} (type: {peer_type})"
                    )
                    continue

            # Check object type using isinstance on raw objects
            from pyrogram.raw.types import Channel, Chat, User

            if isinstance(chat, User):
                # This is a private chat with a user
                if getattr(chat, "bot", False):
                    bots_skipped += 1
                    user_identifier = (
                        f"@{chat.username}"
                        if chat.username
                        else f"'{chat.first_name or 'Unknown'}'"
                    )
                    logger.debug(
                        f"Skipping bot: {user_identifier} from folder '{folder_name}' - bots are not synchronized"
                    )
                else:
                    users_skipped += 1
                    user_identifier = (
                        f"@{chat.username}"
                        if chat.username
                        else f"'{chat.first_name or 'Unknown'}'"
                    )
                    logger.debug(
                        f"Skipping private chat: {user_identifier} from folder '{folder_name}' - private chats are not synchronized"
                    )
                continue

            elif isinstance(chat, Chat):
                # This is a basic group
                groups_skipped += 1
                logger.debug(
                    f"Skipping group: '{chat.title}' (@{getattr(chat, 'username', None) or 'no_username'}) from folder '{folder_name}' - groups are not synchronized"
                )
                continue

            elif isinstance(chat, Channel):
                # This is a channel or supergroup
                if getattr(chat, "megagroup", False):
                    # This is a supergroup
                    supergroups_skipped += 1
                    username = getattr(chat, "username", None)
                    logger.debug(
                        f"Skipping supergroup: '{chat.title}' (@{username or 'no_username'}) from folder '{folder_name}' - supergroups are not synchronized"
                    )
                    continue
                elif getattr(chat, "broadcast", False):
                    # This is a broadcast channel - process it
                    is_private = not hasattr(chat, "username") or chat.username is None

                    # Generate hash for private channel
                    channel_hash = None
                    if is_private:
                        channel_hash = self._generate_channel_hash(chat.id)

                    channel = TelegramChannel(
                        id=chat.id,
                        title=chat.title,
                        username=chat.username,
                        is_private=is_private,
                        folder_name=folder_name,
                        channel_hash=channel_hash,
                    )
                    channels.append(channel)
                    channels_added += 1
                    logger.debug(
                        f"Found channel for sync: {chat.title} from folder '{folder_name}'"
                    )
                else:
                    # Unknown channel type
                    other_skipped += 1
                    username = getattr(chat, "username", None)
                    logger.debug(
                        f"Skipping unknown channel type: '{chat.title}' (@{username or 'no_username'}) from folder '{folder_name}' - unknown type"
                    )
                    continue
            else:
                # Unknown object type
                other_skipped += 1
                chat_class = type(chat).__name__
                logger.debug(
                    f"Skipping unknown object type: '{getattr(chat, 'title', 'Unknown')}' (class: {chat_class}) from folder '{folder_name}' - unknown type"
                )
                continue

        if missing_chats > 0:
            logger.info(
                f"Note: {missing_chats} chats were not accessible in folder '{folder_name}' (likely deleted or restricted)"
            )

        # Summary for this folder
        filtered_summary = []
        if users_skipped > 0:
            filtered_summary.append(f"{users_skipped} private chats")
        if bots_skipped > 0:
            filtered_summary.append(f"{bots_skipped} bots")
        if supergroups_skipped > 0:
            filtered_summary.append(f"{supergroups_skipped} supergroups")
        if groups_skipped > 0:
            filtered_summary.append(f"{groups_skipped} groups")
        if other_skipped > 0:
            filtered_summary.append(f"{other_skipped} other")

        if filtered_summary:
            logger.info(
                f"Folder '{folder_name}' filtered out: {', '.join(filtered_summary)}"
            )

        return channels

    async def send_notification(self, message: str) -> None:
        """
        Send notification to specified chat, splitting long messages if necessary

        Uses high-level API (send_message) for reliability and simplicity.
        Includes unified error handling, automatic message splitting, and automatic
        peer discovery for new sessions.

        Args:
            message: Message text
        """
        if not self.client:
            raise RuntimeError("Client not connected")

        # Telegram's message length limit
        MAX_MESSAGE_LENGTH = 4096

        try:
            # Ensure the target peer is available before attempting to send
            validated_chat_id = await self._ensure_peer_available(self.config.notify_chat_id)
            logger.debug(f"Using validated chat_id: {validated_chat_id}")

            if len(message) <= MAX_MESSAGE_LENGTH:
                # Message fits in one message - use unified error handling
                await TelegramAPIHandler.handle_api_call(
                    self.client.send_message,
                    chat_id=validated_chat_id,
                    text=message,
                    method_name="send_notification",
                    max_retries=3,
                )
                logger.info("Notification sent successfully")
            else:
                # Message is too long, need to split it
                logger.info(
                    f"Message is {len(message)} characters, splitting into multiple messages"
                )

                # Split the message intelligently
                parts = self._split_message(message, MAX_MESSAGE_LENGTH)

                for i, part in enumerate(parts):
                    try:
                        if i == 0:
                            # First message
                            await TelegramAPIHandler.handle_api_call(
                                self.client.send_message,
                                chat_id=validated_chat_id,
                                text=part,
                                method_name=f"send_notification_part_{i + 1}",
                                max_retries=3,
                            )
                        else:
                            # Subsequent messages with a small delay to avoid rate limiting
                            await asyncio.sleep(0.1)
                            await TelegramAPIHandler.handle_api_call(
                                self.client.send_message,
                                chat_id=validated_chat_id,
                                text=f"(continued {i + 1}/{len(parts)})\n\n{part}",
                                method_name=f"send_notification_part_{i + 1}",
                                max_retries=3,
                            )
                    except TelegramAPIError as e:
                        logger.error(
                            f"Failed to send notification part {i + 1}/{len(parts)}: {e.message}"
                        )
                        # Continue with remaining parts - partial notification is better than none
                        continue

                logger.info(f"Notification sent in {len(parts)} parts")

        except TelegramAPIError as e:
            logger.error(f"Failed to send notification: {e.message}")
            raise TelegramAPIError(
                f"Notification sending failed: {e.message}",
                e.original_error,
                "send_notification",
            )
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {e}")
            raise TelegramAPIError(
                f"Unexpected notification error: {e}", e, "send_notification"
            )

    def _split_message(self, message: str, max_length: int) -> list[str]:
        """
        Split a long message into multiple parts while preserving structure

        Args:
            message: The message to split
            max_length: Maximum length per part

        Returns:
            List[str]: List of message parts
        """
        if len(message) <= max_length:
            return [message]

        parts = []
        remaining = message

        while remaining:
            if len(remaining) <= max_length:
                # Remaining text fits in one part
                parts.append(remaining)
                break

            # Find the best split point
            split_point = max_length

            # Try to split at a newline first
            chunk = remaining[:split_point]
            last_newline = chunk.rfind("\n")

            if last_newline > max_length // 2:  # Only use newline if it's not too early
                split_point = last_newline
                parts.append(remaining[:split_point])
                remaining = remaining[split_point + 1 :]  # +1 to skip the newline
            else:
                # Try to split at a space
                last_space = chunk.rfind(" ")

                if last_space > max_length // 2:  # Only use space if it's not too early
                    split_point = last_space
                    parts.append(remaining[:split_point])
                    remaining = remaining[split_point + 1 :]  # +1 to skip the space
                else:
                    # Force split at max_length
                    parts.append(remaining[:max_length])
                    remaining = remaining[max_length:]

        return parts

    def _generate_channel_hash(self, channel_id: int) -> str:
        """Generate hash for private channel access.

        Creates a deterministic hash based on channel ID and API credentials
        for accessing private channels via RSSHub secret parameter.

        Args:
            channel_id: Unique channel identifier

        Returns:
            Generated hash string for private channel access
        """
        # Simple hash generation based on channel ID
        # In real application, you can use more complex logic
        hash_input = f"{channel_id}_{self.config.api_hash}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

    async def get_unfoldered_channels(self) -> list[TelegramChannel]:
        """
        Get list of channels that are not in any folder (only in Main folder)

        Uses high-level API (get_dialogs) with unified error handling.
        Includes fallback mechanisms for folder detection.

        Returns:
            List[TelegramChannel]: List of channels not in any custom folder
        """
        if not self.client:
            raise RuntimeError("Client not connected")

        # Get folder information with channel mappings
        folder_info = await self._get_dialog_filters_with_peers()

        # Create a mapping from channel_id to folder info
        channel_to_folder: dict[int, dict] = {}
        for _folder_name, folder_data in folder_info.items():
            # Extract channel IDs from include_peers
            for peer in folder_data["include_peers"]:
                channel_id = (
                    peer.user_id
                    if hasattr(peer, "user_id")
                    else (
                        peer.channel_id if hasattr(peer, "channel_id") else peer.chat_id
                    )
                )
                channel_to_folder[channel_id] = {
                    "id": folder_data["id"],
                    "name": folder_data["title"],
                }

        logger.info(
            f"Found {len(folder_info)} dialog filters with {len(channel_to_folder)} channel mappings"
        )

        # Get all dialogs and find channels not in any folder
        unfoldered_channels = []
        dialog_count = 0
        channels_found = 0
        supergroups_skipped = 0
        channels_in_folders = 0

        try:
            # Use unified error handling for high-level API call
            async def get_all_dialogs():
                dialogs = []
                async for dialog in self.client.get_dialogs():
                    dialogs.append(dialog)
                return dialogs

            all_dialogs = await TelegramAPIHandler.handle_api_call(
                get_all_dialogs, method_name="get_unfoldered_channels", max_retries=3
            )

            for dialog in all_dialogs:
                dialog: Dialog
                chat: Chat = dialog.chat
                dialog_count += 1

                # Check if it's a channel or supergroup
                if chat.type.value not in ["channel", "supergroup"]:
                    continue

                # Use raw object attributes to distinguish channels from supergroups
                try:
                    # Access the raw object to get broadcast/megagroup flags
                    if hasattr(chat, "_raw") and chat._raw:
                        raw_chat = chat._raw

                        # Check if it's a supergroup (megagroup=True) - skip these
                        if hasattr(raw_chat, "megagroup") and raw_chat.megagroup:
                            supergroups_skipped += 1
                            logger.debug(
                                f"Skipping supergroup: {chat.title} (ID: {chat.id})"
                            )
                            continue

                        # Check if it's a broadcast channel (broadcast=True) - keep these
                        if hasattr(raw_chat, "broadcast") and raw_chat.broadcast:
                            # This is a real channel, proceed
                            pass
                        else:
                            # If neither broadcast nor megagroup flags are clear, skip to be safe
                            logger.debug(
                                f"Skipping chat with unclear type: {chat.title} (ID: {chat.id})"
                            )
                            continue
                    else:
                        # If we can't access raw object, fall back to type check
                        # Only proceed if type is explicitly "channel"
                        if chat.type.value != "channel":
                            logger.debug(
                                f"Skipping non-channel: {chat.title} (ID: {chat.id}, type: {chat.type.value})"
                            )
                            continue

                except Exception as e:
                    logger.warning(
                        f"Failed to check chat type for {chat.title} (ID: {chat.id}): {e}"
                    )
                    # If we can't determine the type, skip this chat to be safe
                    continue

                channels_found += 1

                # Determine folder using channel mapping
                channel_id = chat.id

                # Convert negative channel IDs to positive (Telegram API quirk)
                if channel_id < 0:
                    # Remove the -100 prefix for supergroups/channels
                    if str(channel_id).startswith("-100"):
                        channel_id = int(str(channel_id)[4:])
                    else:
                        channel_id = abs(channel_id)

                if channel_id in channel_to_folder:
                    # Found in a specific folder - skip this channel
                    channels_in_folders += 1
                    logger.debug(
                        f"Channel {chat.title} is in folder '{channel_to_folder[channel_id]['name']}' - skipping"
                    )
                else:
                    # Not in any specific folder - this is what we want
                    is_private = not hasattr(chat, "username") or chat.username is None

                    # Generate hash for private channel
                    channel_hash = None
                    if is_private:
                        channel_hash = self._generate_channel_hash(chat.id)

                    channel = TelegramChannel(
                        id=chat.id,
                        title=chat.title,
                        username=chat.username,
                        is_private=is_private,
                        folder_name=None,  # Not in any folder
                        channel_hash=channel_hash,
                    )
                    unfoldered_channels.append(channel)
                    logger.debug(f"Found unfoldered channel: {chat.title}")

            logger.info(f"Analyzed {dialog_count} total dialogs")
            logger.info(
                f"Found {channels_found} total channels (skipped {supergroups_skipped} supergroups)"
            )
            logger.info(f"Channels in folders: {channels_in_folders}")
            logger.info(f"Found {len(unfoldered_channels)} channels not in any folder")

        except TelegramAPIError as e:
            logger.error(f"Failed to get unfoldered channels: {e.message}")
            raise TelegramAPIError(
                f"Could not retrieve unfoldered channels: {e.message}",
                e.original_error,
                "get_unfoldered_channels",
            )

        return unfoldered_channels

    async def _fallback_get_channels_from_all_dialogs(
        self, folder_names: list[str]
    ) -> list[TelegramChannel]:
        """
        Fallback method to get channels using high-level API when Raw API is unavailable

        This method uses get_dialogs() to enumerate all channels and assigns them to "Main" folder
        since we can't determine actual folder assignments without Raw API.

        Args:
            folder_names: List of requested folder names (will be mapped to "Main" in fallback)

        Returns:
            List[TelegramChannel]: List of channels found via high-level API
        """
        logger.info("Using fallback method: getting channels via high-level API")
        logger.warning(
            "Folder-specific filtering unavailable in fallback mode - all channels assigned to 'Main'"
        )

        channels = []
        dialog_count = 0
        channels_found = 0
        supergroups_skipped = 0

        try:
            # Use unified error handling for high-level API call
            async def get_all_dialogs():
                dialogs = []
                async for dialog in self.client.get_dialogs():
                    dialogs.append(dialog)
                return dialogs

            all_dialogs = await TelegramAPIHandler.handle_api_call(
                get_all_dialogs, method_name="get_dialogs_fallback", max_retries=3
            )

            for dialog in all_dialogs:
                dialog: Dialog
                chat: Chat = dialog.chat
                dialog_count += 1

                # Check if it's a channel or supergroup
                if chat.type.value not in ["channel", "supergroup"]:
                    continue

                # Use raw object attributes to distinguish channels from supergroups
                try:
                    # Access the raw object to get broadcast/megagroup flags
                    if hasattr(chat, "_raw") and chat._raw:
                        raw_chat = chat._raw

                        # Check if it's a supergroup (megagroup=True) - skip these
                        if hasattr(raw_chat, "megagroup") and raw_chat.megagroup:
                            supergroups_skipped += 1
                            logger.debug(
                                f"Skipping supergroup: {chat.title} (ID: {chat.id})"
                            )
                            continue

                        # Check if it's a broadcast channel (broadcast=True) - keep these
                        if hasattr(raw_chat, "broadcast") and raw_chat.broadcast:
                            # This is a real channel, proceed
                            pass
                        else:
                            # If neither broadcast nor megagroup flags are clear, skip to be safe
                            logger.debug(
                                f"Skipping chat with unclear type: {chat.title} (ID: {chat.id})"
                            )
                            continue
                    else:
                        # If we can't access raw object, fall back to type check
                        # Only proceed if type is explicitly "channel"
                        if chat.type.value != "channel":
                            logger.debug(
                                f"Skipping non-channel: {chat.title} (ID: {chat.id}, type: {chat.type.value})"
                            )
                            continue

                except Exception as e:
                    logger.warning(
                        f"Failed to check chat type for {chat.title} (ID: {chat.id}): {e}"
                    )
                    # If we can't determine the type, skip this chat to be safe
                    continue

                channels_found += 1

                # In fallback mode, all channels go to "Main" folder
                is_private = not hasattr(chat, "username") or chat.username is None

                # Generate hash for private channel
                channel_hash = None
                if is_private:
                    channel_hash = self._generate_channel_hash(chat.id)

                channel = TelegramChannel(
                    id=chat.id,
                    title=chat.title,
                    username=chat.username,
                    is_private=is_private,
                    folder_name="Main",  # All channels assigned to Main in fallback mode
                    channel_hash=channel_hash,
                )
                channels.append(channel)

                if channels_found <= 5:
                    logger.debug(
                        f"Found channel: {chat.title} (assigned to Main folder)"
                    )

            logger.info(
                f"Fallback completed: analyzed {dialog_count} dialogs, found {channels_found} channels (skipped {supergroups_skipped} supergroups)"
            )

        except TelegramAPIError as e:
            logger.error(f"Fallback method also failed: {e.message}")
            raise TelegramAPIError(
                f"Both Raw API and fallback methods failed: {e.message}",
                e.original_error,
                "fallback_get_channels",
            )

        return channels

    async def _fallback_get_channels_from_peers(
        self, peers: list, folder_name: str
    ) -> list[TelegramChannel]:
        """
        Fallback method to get channels from specific peers using high-level API

        This method attempts to get channel information for specific peers when
        GetPeerDialogs Raw API call fails.

        Args:
            peers: List of peer objects from Raw API
            folder_name: Name of the folder being processed

        Returns:
            List[TelegramChannel]: List of channels found via high-level API
        """
        logger.info(
            f"Using fallback method for {len(peers)} peers in folder '{folder_name}'"
        )

        channels = []

        for peer in peers:
            try:
                # Extract peer ID
                peer_id = None
                if hasattr(peer, "channel_id"):
                    peer_id = peer.channel_id
                elif hasattr(peer, "chat_id"):
                    peer_id = peer.chat_id
                elif hasattr(peer, "user_id"):
                    # Skip users in fallback mode
                    continue

                if peer_id is None:
                    continue

                # Try to get chat info using high-level API
                try:
                    chat = await TelegramAPIHandler.handle_api_call(
                        self.client.get_chat,
                        peer_id,
                        method_name=f"get_chat_fallback_{peer_id}",
                        max_retries=2,
                    )

                    # Check if it's a broadcast channel
                    if hasattr(chat, "_raw") and chat._raw:
                        raw_chat = chat._raw
                        if hasattr(raw_chat, "broadcast") and raw_chat.broadcast:
                            is_private = (
                                not hasattr(chat, "username") or chat.username is None
                            )

                            # Generate hash for private channel
                            channel_hash = None
                            if is_private:
                                channel_hash = self._generate_channel_hash(chat.id)

                            channel = TelegramChannel(
                                id=chat.id,
                                title=chat.title,
                                username=chat.username,
                                is_private=is_private,
                                folder_name=folder_name,
                                channel_hash=channel_hash,
                            )
                            channels.append(channel)
                            logger.debug(f"Fallback found channel: {chat.title}")
                        else:
                            logger.debug(
                                f"Skipping non-broadcast chat: {getattr(chat, 'title', 'Unknown')}"
                            )

                except TelegramAPIError as e:
                    logger.debug(
                        f"Failed to get chat info for peer {peer_id}: {e.message}"
                    )
                    continue

            except Exception as e:
                logger.debug(f"Error processing peer in fallback: {e}")
                continue

        logger.info(
            f"Fallback method found {len(channels)} channels for folder '{folder_name}'"
        )
        return channels

    async def _ensure_peer_available(self, chat_id: str | int) -> str | int:
        """
        Ensure peer is available for messaging by attempting to discover it if not found.

        This method handles the "peer id being used is invalid or not known yet" error
        by automatically attempting to discover the peer through various methods.

        Args:
            chat_id: The chat ID to validate ("me", integer ID, or @username)

        Returns:
            Validated chat_id that can be used for messaging

        Raises:
            TelegramAPIError: If peer cannot be discovered or validated
        """
        if not self.client:
            raise RuntimeError("Client not connected")

        # "me" is always valid
        if chat_id == "me":
            return chat_id

        try:
            # Try to get chat info to validate the peer
            await TelegramAPIHandler.handle_api_call(
                self.client.get_chat,
                chat_id,
                method_name="validate_peer",
                max_retries=1,
            )
            logger.debug(f"Peer {chat_id} is already available")
            return chat_id

        except TelegramAPIError as e:
            if "PEER_ID_INVALID" in str(e.original_error):
                logger.info(f"🔍 Peer {chat_id} not found in current session, attempting auto-discovery...")

                # If it's a numeric ID, try to find by possible username patterns
                if isinstance(chat_id, int) or (isinstance(chat_id, str) and chat_id.isdigit()):
                    logger.info(f"💡 Searching for bot with ID {chat_id} using smart discovery...")
                    discovered_peer = await self._auto_discover_peer_by_id(int(chat_id))
                    if discovered_peer:
                        logger.info(f"✅ Successfully discovered and connected to peer {chat_id}")
                        return discovered_peer

                # If it's a username, try alternative formats
                elif isinstance(chat_id, str) and chat_id.startswith("@"):
                    logger.info(f"💡 Searching for username {chat_id}...")
                    discovered_peer = await self._auto_discover_peer_by_username(chat_id)
                    if discovered_peer:
                        logger.info(f"✅ Successfully discovered and connected to {chat_id}")
                        return discovered_peer

                # If auto-discovery failed, provide helpful error message
                logger.error(f"❌ Auto-discovery failed for peer {chat_id}")
                raise TelegramAPIError(
                    f"Cannot find peer {chat_id}. For bots, make sure to send /start to the bot first from your Telegram account, "
                    f"or add the bot to a group/channel where your account is also present.",
                    e.original_error,
                    "ensure_peer_available"
                )
            else:
                # Re-raise other types of errors
                raise e

    async def _auto_discover_peer_by_id(self, peer_id: int) -> str | int | None:
        """
        Try to auto-discover a peer by its numeric ID using various strategies.

        Args:
            peer_id: Numeric peer ID to discover

        Returns:
            Discovered peer identifier or None if not found
        """
        logger.debug(f"Attempting auto-discovery for peer ID: {peer_id}")

        # Strategy 1: Search through recent dialogs for matching ID
        try:
            logger.debug("Searching through recent dialogs...")

            # Use a limited search to avoid performance issues
            dialog_count = 0
            max_dialogs_to_search = 100

            async for dialog in self.client.get_dialogs(limit=max_dialogs_to_search):
                dialog_count += 1
                if dialog.chat.id == peer_id:
                    logger.info(f"Found peer {peer_id} in recent dialogs: {dialog.chat.title or dialog.chat.first_name}")
                    return peer_id

            logger.debug(f"Searched {dialog_count} dialogs, peer not found")

        except Exception as e:
            logger.debug(f"Dialog search failed: {e}")

        # Strategy 2: Try known bot username patterns first (faster and more reliable)
        try:
            logger.debug("Attempting known bot pattern discovery...")
            discovered_peer = await self._discover_known_bots(peer_id)
            if discovered_peer:
                return discovered_peer
        except Exception as e:
            logger.debug(f"Known bot discovery failed: {e}")

        # Strategy 3: Search through existing bot dialogs for matching ID
        try:
            logger.debug("Searching through bot dialogs...")

            # Look for bots with "bot" in the name through contacts/dialogs
            async for dialog in self.client.get_dialogs(limit=50):
                if (dialog.chat.type.value == "bot" and
                    dialog.chat.username and
                    "bot" in dialog.chat.username.lower()):

                    # Try to get the chat and see if it matches our target ID
                    try:
                        chat = await self.client.get_chat(f"@{dialog.chat.username}")
                        if chat.id == peer_id:
                            logger.info(f"Discovered peer {peer_id} as @{dialog.chat.username}")
                            return peer_id
                    except Exception:
                        logger.debug(f"Error accessing bot @{dialog.chat.username}")
                        continue

        except Exception as e:
            logger.debug(f"Bot dialog search failed: {e}")

        logger.debug(f"Auto-discovery failed for peer ID: {peer_id}")
        return None

    async def _auto_discover_peer_by_username(self, username: str) -> str | int | None:
        """
        Try to auto-discover a peer by its username.

        Args:
            username: Username to discover (with or without @)

        Returns:
            Discovered peer identifier or None if not found
        """
        username = username.lstrip("@")  # Remove @ if present
        logger.debug(f"Attempting auto-discovery for username: @{username}")

        try:
            # Try to search for the username directly
            chat = await TelegramAPIHandler.handle_api_call(
                self.client.get_chat,
                f"@{username}",
                method_name="discover_by_username",
                max_retries=1,
            )
            logger.info(f"Discovered peer @{username} with ID: {chat.id}")
            return chat.id

        except TelegramAPIError as e:
            logger.debug(f"Username discovery failed for @{username}: {e.message}")
            return None

    async def _discover_known_bots(self, target_id: int) -> str | int | None:
        """
        Try to discover known bots by their common usernames.

        This method attempts to find bots by searching for common bot username patterns
        that might match the target ID. This is useful when the session is new and
        the bot peer is not yet known.

        Args:
            target_id: Target bot ID to discover

        Returns:
            Discovered peer identifier or None if not found
        """
        # List of common bot username patterns to try
        # These can be extended based on common bot naming conventions
        common_bot_patterns = [
            "tlflx_bot",  # Specific for this application
            "teleflux_bot",
            "rss_bot",
            "feed_bot",
            "notify_bot",
            "notification_bot"
        ]

        logger.debug(f"Searching for known bot patterns for ID: {target_id}")

        for bot_username in common_bot_patterns:
            try:
                logger.debug(f"Trying bot username: @{bot_username}")
                chat = await TelegramAPIHandler.handle_api_call(
                    self.client.get_chat,
                    f"@{bot_username}",
                    method_name="discover_known_bot",
                    max_retries=1,
                )

                if chat.id == target_id:
                    logger.info(f"Successfully discovered bot {target_id} as @{bot_username}")
                    return target_id
                else:
                    logger.debug(f"Bot @{bot_username} found but ID mismatch: {chat.id} != {target_id}")

            except TelegramAPIError as e:
                if "USERNAME_NOT_OCCUPIED" in str(e.original_error):
                    logger.debug(f"Bot @{bot_username} does not exist")
                else:
                    logger.debug(f"Error checking @{bot_username}: {e.message}")
                continue

        logger.debug(f"No known bot patterns matched for ID: {target_id}")
        return None
