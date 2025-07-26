"""
Tests for Telegram client module
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from teleflux.config import TelegramConfig
from teleflux.telegram_client import TelegramClient


@pytest.fixture
def test_telegram_config():
    """Test configuration fixture"""
    return TelegramConfig(
        api_id="12345",
        api_hash="test_hash",
        session_file="test.session",
        notify_chat_id="me",
    )


@pytest.fixture
def mock_dialog_filters():
    """Mock dialog filters fixture"""
    return {1: "AI & Tech", 2: "News & Media", 3: "Entertainment"}


@pytest.fixture
def mock_dialogs():
    """Mock dialogs fixture"""
    dialogs = []

    # Main folder channels (folder_id should be None or not present)
    for i in range(3):
        dialog = MagicMock()
        dialog.chat = MagicMock()
        dialog.chat.id = 100 + i
        dialog.chat.username = f"main_channel_{i}"
        dialog.chat.title = f"Main Channel {i}"
        dialog.chat.type.value = "channel"
        # Add raw object with broadcast=True for real channels
        dialog.chat._raw = MagicMock()
        dialog.chat._raw.broadcast = True
        dialog.chat._raw.megagroup = False
        # For Main folder, folder_id should be None or not present
        dialog.folder_id = None
        dialogs.append(dialog)

    # AI & Tech folder channels (folder_id = 1)
    for i in range(2):
        dialog = MagicMock()
        dialog.chat = MagicMock()
        dialog.chat.id = 200 + i
        dialog.chat.username = f"ai_channel_{i}"
        dialog.chat.title = f"AI Channel {i}"
        dialog.chat.type.value = "channel"
        # Add raw object with broadcast=True for real channels
        dialog.chat._raw = MagicMock()
        dialog.chat._raw.broadcast = True
        dialog.chat._raw.megagroup = False
        dialog.folder_id = 1
        dialogs.append(dialog)

    # News & Media folder channels (folder_id = 2, private)
    for i in range(1):
        dialog = MagicMock()
        dialog.chat = MagicMock()
        dialog.chat.id = -(300 + i)  # Negative for private
        dialog.chat.username = None
        dialog.chat.title = f"Private News Channel {i}"
        dialog.chat.type.value = "channel"
        # Add raw object with broadcast=True for real channels
        dialog.chat._raw = MagicMock()
        dialog.chat._raw.broadcast = True
        dialog.chat._raw.megagroup = False
        dialog.folder_id = 2
        dialogs.append(dialog)

    # Entertainment folder channels (folder_id = 3)
    for i in range(1):
        dialog = MagicMock()
        dialog.chat = MagicMock()
        dialog.chat.id = 400 + i
        dialog.chat.username = f"entertainment_channel_{i}"
        dialog.chat.title = f"Entertainment Channel {i}"
        dialog.chat.type.value = "channel"
        # Add raw object with broadcast=True for real channels
        dialog.chat._raw = MagicMock()
        dialog.chat._raw.broadcast = True
        dialog.chat._raw.megagroup = False
        dialog.folder_id = 3
        dialogs.append(dialog)

    # Non-channel dialogs (should be ignored)
    dialog = MagicMock()
    dialog.chat = MagicMock()
    dialog.chat.id = 500
    dialog.chat.username = "user_chat"
    dialog.chat.title = "User Chat"
    dialog.chat.type.value = "private"
    dialog.chat._raw = MagicMock()
    dialog.chat._raw.broadcast = False
    dialog.chat._raw.megagroup = False
    dialog.folder_id = None
    dialogs.append(dialog)

    return dialogs


class AsyncIterator:
    """Helper class for async iteration in tests"""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.mark.asyncio
async def test_get_all_folders(test_telegram_config, mock_dialogs, mock_dialog_filters):
    """Test getting all folders with channel counts"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Create async iterator directly
        async_iter = AsyncIterator(mock_dialogs)
        mock_client.get_dialogs = MagicMock(return_value=async_iter)

        client.client = mock_client

        # Mock the handle_flood_wait method to just call the function directly
        async def mock_handle_flood_wait(func, *args, **kwargs):
            return await func(*args, **kwargs)

        client.handle_flood_wait = mock_handle_flood_wait

        # Mock the _get_dialog_filters_with_peers method with proper structure
        with patch.object(client, "_get_dialog_filters_with_peers") as mock_get_filters:
            # Create mock folder info with include_peers
            mock_peer1 = MagicMock()
            mock_peer1.channel_id = 200
            del mock_peer1.user_id
            del mock_peer1.chat_id

            mock_peer2 = MagicMock()
            mock_peer2.channel_id = 201
            del mock_peer2.user_id
            del mock_peer2.chat_id

            mock_peer3 = MagicMock()
            mock_peer3.channel_id = 300
            del mock_peer3.user_id
            del mock_peer3.chat_id

            mock_peer4 = MagicMock()
            mock_peer4.channel_id = 400
            del mock_peer4.user_id
            del mock_peer4.chat_id

            mock_folder_info = {
                "AI & Tech": {
                    "id": 1,
                    "title": "AI & Tech",
                    "type": "DialogFilter",
                    "include_peers": [mock_peer1, mock_peer2],  # AI channels
                },
                "News & Media": {
                    "id": 2,
                    "title": "News & Media",
                    "type": "DialogFilter",
                    "include_peers": [mock_peer3],  # Private news channel
                },
                "Entertainment": {
                    "id": 3,
                    "title": "Entertainment",
                    "type": "DialogFilter",
                    "include_peers": [mock_peer4],  # Entertainment channel
                },
            }
            mock_get_filters.return_value = mock_folder_info

            folders = await client.get_all_folders()

            # Check results - folders are correctly detected with proper channel distribution
            assert len(folders) == 4  # Main + 3 custom folders

            # Check that we have all expected folders
            folder_names = [f.name for f in folders]
            assert "Main" in folder_names
            assert "AI & Tech" in folder_names
            assert "News & Media" in folder_names
            assert "Entertainment" in folder_names

            # Check Main folder
            main_folder = next(f for f in folders if f.name == "Main")
            assert main_folder.id is None
            assert main_folder.channel_count == 3  # 3 channels in Main

            # Check other folders have correct counts
            ai_folder = next(f for f in folders if f.name == "AI & Tech")
            news_folder = next(f for f in folders if f.name == "News & Media")
            entertainment_folder = next(f for f in folders if f.name == "Entertainment")

            assert ai_folder.channel_count == 2
            assert news_folder.channel_count == 1
            assert entertainment_folder.channel_count == 1


@pytest.mark.asyncio
async def test_get_channels_by_folders(
    test_telegram_config, mock_dialogs, mock_dialog_filters
):
    """Test getting channels from specific folders"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock the invoke method for GetPeerDialogs
        async def mock_invoke(request):
            from pyrogram.raw import functions

            if isinstance(request, functions.messages.GetPeerDialogs):
                # Create mock response for GetPeerDialogs
                mock_response = MagicMock()

                # Create mock dialogs and chats based on the requested peers
                mock_dialogs_list = []
                mock_chats_list = []

                for peer in request.peers:
                    if hasattr(peer, "channel_id"):
                        channel_id = peer.channel_id

                        # Find corresponding mock dialog
                        for dialog in mock_dialogs:
                            if dialog.chat.id == channel_id:
                                # Create mock dialog for response
                                mock_dialog = MagicMock()
                                mock_dialog.peer = MagicMock()
                                mock_dialog.peer.channel_id = channel_id
                                mock_dialogs_list.append(mock_dialog)

                                # Create a regular mock chat object
                                chat_copy = MagicMock()
                                chat_copy.id = dialog.chat.id
                                chat_copy.title = dialog.chat.title
                                chat_copy.username = dialog.chat.username
                                # Set broadcast/megagroup attributes directly
                                chat_copy.broadcast = dialog.chat._raw.broadcast
                                chat_copy.megagroup = dialog.chat._raw.megagroup

                                mock_chats_list.append(chat_copy)
                                break

                mock_response.dialogs = mock_dialogs_list
                mock_response.chats = mock_chats_list
                return mock_response

            # For other requests, return empty response
            return MagicMock()

        mock_client.invoke = mock_invoke

        client.client = mock_client

        # Mock isinstance to make our mock objects pass the type checks
        original_isinstance = isinstance

        def custom_isinstance(obj, class_or_tuple):
            result = original_isinstance(obj, class_or_tuple)

            # Make our mock objects pass the appropriate type checks
            from pyrogram.raw.types import Channel, Chat, User

            if hasattr(obj, "broadcast") and hasattr(obj, "megagroup"):
                if class_or_tuple == Channel:
                    return True
            elif hasattr(obj, "title") and not hasattr(obj, "broadcast"):
                if class_or_tuple == Chat:
                    return True
            elif hasattr(obj, "first_name") or hasattr(obj, "username"):
                if class_or_tuple == User:
                    return True

            return result

        with patch(
            "teleflux.telegram_client.isinstance", side_effect=custom_isinstance
        ):
            # Mock the _get_dialog_filters_with_peers method
            with patch.object(
                client, "_get_dialog_filters_with_peers"
            ) as mock_get_filters:
                # Create mock peers for the folder - use IDs from AI & Tech channels in mock_dialogs
                mock_peer1 = MagicMock()
                mock_peer1.channel_id = 200  # AI Channel 0 from mock_dialogs
                # Ensure other attributes don't exist to avoid fallback to user_id/chat_id
                del mock_peer1.user_id
                del mock_peer1.chat_id

                mock_peer2 = MagicMock()
                mock_peer2.channel_id = 201  # AI Channel 1 from mock_dialogs
                # Ensure other attributes don't exist to avoid fallback to user_id/chat_id
                del mock_peer2.user_id
                del mock_peer2.chat_id

                mock_folder_info = {
                    "AI & Tech": {
                        "id": 1,
                        "title": "AI & Tech",
                        "type": "DialogFilter",
                        "include_peers": [mock_peer1, mock_peer2],
                    }
                }
                mock_get_filters.return_value = mock_folder_info

                channels = await client.get_channels_by_folders(["AI & Tech"])

                # Should return 2 channels (both are broadcast channels from mock_dialogs)
                assert len(channels) == 2

                # Check channel details - these are the AI channels from mock_dialogs
                channel_titles = [c.title for c in channels]
                assert "AI Channel 0" in channel_titles
                assert "AI Channel 1" in channel_titles

                # Check folder assignment
                for channel in channels:
                    assert channel.folder_name == "AI & Tech"


@pytest.mark.asyncio
async def test_get_channels_by_folders_private_channels(
    test_telegram_config, mock_dialogs, mock_dialog_filters
):
    """Test getting private channels from folders"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock the invoke method for GetPeerDialogs
        async def mock_invoke(request):
            from pyrogram.raw import functions

            if isinstance(request, functions.messages.GetPeerDialogs):
                # Create mock response for GetPeerDialogs
                mock_response = MagicMock()

                # Create mock dialogs and chats based on the requested peers
                mock_dialogs_list = []
                mock_chats_list = []

                for peer in request.peers:
                    if hasattr(peer, "channel_id"):
                        channel_id = peer.channel_id

                        # Find corresponding mock dialog (private channel has negative ID)
                        for dialog in mock_dialogs:
                            if (
                                dialog.chat.id == -channel_id
                            ):  # Private channel ID is negative
                                # Create mock dialog for response
                                mock_dialog = MagicMock()
                                mock_dialog.peer = MagicMock()
                                # Use the actual chat ID (negative) as peer_id in response
                                mock_dialog.peer.channel_id = abs(
                                    dialog.chat.id
                                )  # Use positive version for peer
                                mock_dialogs_list.append(mock_dialog)

                                # Create a regular mock chat object
                                chat_copy = MagicMock()
                                chat_copy.id = abs(
                                    dialog.chat.id
                                )  # Use positive ID to match peer_id
                                chat_copy.title = dialog.chat.title
                                chat_copy.username = dialog.chat.username
                                # Set broadcast/megagroup attributes directly
                                chat_copy.broadcast = dialog.chat._raw.broadcast
                                chat_copy.megagroup = dialog.chat._raw.megagroup

                                mock_chats_list.append(chat_copy)
                                break

                mock_response.dialogs = mock_dialogs_list
                mock_response.chats = mock_chats_list
                return mock_response

            # For other requests, return empty response
            return MagicMock()

        mock_client.invoke = mock_invoke

        client.client = mock_client

        # Mock isinstance to make our mock objects pass the type checks
        original_isinstance = isinstance

        def custom_isinstance(obj, class_or_tuple):
            result = original_isinstance(obj, class_or_tuple)

            # Make our mock objects pass the appropriate type checks
            from pyrogram.raw.types import Channel, Chat, User

            if hasattr(obj, "broadcast") and hasattr(obj, "megagroup"):
                if class_or_tuple == Channel:
                    return True
            elif hasattr(obj, "title") and not hasattr(obj, "broadcast"):
                if class_or_tuple == Chat:
                    return True
            elif hasattr(obj, "first_name") or hasattr(obj, "username"):
                if class_or_tuple == User:
                    return True

            return result

        with patch(
            "teleflux.telegram_client.isinstance", side_effect=custom_isinstance
        ):
            # Mock the _get_dialog_filters_with_peers method
            with patch.object(
                client, "_get_dialog_filters_with_peers"
            ) as mock_get_filters:
                # Create mock peer for the private news channel (ID: 300, not -300)
                # The negative ID will be created by our conversion logic
                mock_peer = MagicMock()
                mock_peer.channel_id = (
                    300  # Will look for original -300 in mock_dialogs
                )
                # Ensure other attributes don't exist to avoid fallback to user_id/chat_id
                del mock_peer.user_id
                del mock_peer.chat_id

                mock_folder_info = {
                    "News & Media": {
                        "id": 2,
                        "title": "News & Media",
                        "type": "DialogFilter",
                        "include_peers": [mock_peer],
                    }
                }
                mock_get_filters.return_value = mock_folder_info

                channels = await client.get_channels_by_folders(["News & Media"])

                # Should return 1 private channel
                assert len(channels) == 1

                channel = channels[0]
                assert channel.title == "Private News Channel 0"
                assert channel.is_private is True
                assert channel.username is None
                assert channel.folder_name == "News & Media"
                assert channel.channel_hash is not None


@pytest.mark.asyncio
async def test_get_channels_by_folders_nonexistent_folder(
    test_telegram_config, mock_dialogs, mock_dialog_filters
):
    """Test getting channels from non-existent folder"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        client.client = mock_client

        # Mock the handle_flood_wait method to just call the function directly
        async def mock_handle_flood_wait(func, *args, **kwargs):
            return await func(*args, **kwargs)

        client.handle_flood_wait = mock_handle_flood_wait

        # Mock the _get_dialog_filters_with_peers method
        with patch.object(client, "_get_dialog_filters_with_peers") as mock_get_filters:
            mock_folder_info = {
                1: {
                    "title": "AI & Tech",
                    "type": "DialogFilter",
                    "channel_ids": {200, 201},
                }
            }
            mock_get_filters.return_value = mock_folder_info

            channels = await client.get_channels_by_folders(["NonExistent"])

            # Should return empty list
            assert len(channels) == 0


@pytest.mark.asyncio
async def test_supergroup_filtering(test_telegram_config):
    """Test that supergroups are filtered out and only channels are included"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Create test chats with channel and supergroup
        test_chats = {}

        # Create mock channel (should be included)
        channel_chat = MagicMock()
        channel_chat.id = 100  # Use the peer channel_id directly
        channel_chat.title = "Test Channel"
        channel_chat.username = "test_channel"
        channel_chat.broadcast = True
        channel_chat.megagroup = False
        test_chats[100] = channel_chat

        # Create mock supergroup (should be filtered out)
        supergroup_chat = MagicMock()
        supergroup_chat.id = 200  # Use the peer channel_id directly
        supergroup_chat.title = "Test Supergroup"
        supergroup_chat.username = "test_supergroup"
        supergroup_chat.broadcast = False
        supergroup_chat.megagroup = True
        test_chats[200] = supergroup_chat

        # Mock the invoke method for GetPeerDialogs
        async def mock_invoke(request):
            from pyrogram.raw import functions

            if isinstance(request, functions.messages.GetPeerDialogs):
                # Create mock response for GetPeerDialogs
                mock_response = MagicMock()

                # Create mock dialogs and chats based on the requested peers
                mock_dialogs_list = []
                mock_chats_list = []

                for peer in request.peers:
                    if hasattr(peer, "channel_id"):
                        channel_id = peer.channel_id

                        if channel_id in test_chats:
                            # Create mock dialog for response
                            mock_dialog = MagicMock()
                            mock_dialog.peer = MagicMock()
                            mock_dialog.peer.channel_id = channel_id
                            mock_dialogs_list.append(mock_dialog)

                            # Create a regular mock chat object
                            chat_copy = MagicMock()
                            chat_copy.id = test_chats[channel_id].id
                            chat_copy.title = test_chats[channel_id].title
                            chat_copy.username = test_chats[channel_id].username
                            # Set broadcast/megagroup attributes directly
                            chat_copy.broadcast = test_chats[channel_id].broadcast
                            chat_copy.megagroup = test_chats[channel_id].megagroup

                            mock_chats_list.append(chat_copy)

                mock_response.dialogs = mock_dialogs_list
                mock_response.chats = mock_chats_list
                return mock_response

            # For other requests, return empty response
            return MagicMock()

        mock_client.invoke = mock_invoke

        client.client = mock_client

        # Mock isinstance to make our mock objects pass the type checks
        original_isinstance = isinstance

        def custom_isinstance(obj, class_or_tuple):
            result = original_isinstance(obj, class_or_tuple)

            # Make our mock objects pass the appropriate type checks
            from pyrogram.raw.types import Channel, Chat, User

            if hasattr(obj, "broadcast") and hasattr(obj, "megagroup"):
                if class_or_tuple == Channel:
                    return True
            elif hasattr(obj, "title") and not hasattr(obj, "broadcast"):
                if class_or_tuple == Chat:
                    return True
            elif hasattr(obj, "first_name") or hasattr(obj, "username"):
                if class_or_tuple == User:
                    return True

            return result

        with patch(
            "teleflux.telegram_client.isinstance", side_effect=custom_isinstance
        ):
            # Mock the _get_dialog_filters_with_peers method
            with patch.object(
                client, "_get_dialog_filters_with_peers"
            ) as mock_get_filters:
                # Create mock peers for both channel and supergroup
                mock_peer1 = MagicMock()
                mock_peer1.channel_id = 100  # Test Channel
                del mock_peer1.user_id
                del mock_peer1.chat_id

                mock_peer2 = MagicMock()
                mock_peer2.channel_id = 200  # Test Supergroup
                del mock_peer2.user_id
                del mock_peer2.chat_id

                mock_folder_info = {
                    "Test Folder": {
                        "id": 1,
                        "title": "Test Folder",
                        "type": "DialogFilter",
                        "include_peers": [mock_peer1, mock_peer2],
                    }
                }
                mock_get_filters.return_value = mock_folder_info

                channels = await client.get_channels_by_folders(["Test Folder"])

                # Should only get the 1 channel, supergroup should be filtered out
                assert len(channels) == 1

                channel = channels[0]
                assert channel.title == "Test Channel"
                assert channel.username == "test_channel"
                assert channel.folder_name == "Test Folder"


@pytest.mark.asyncio
async def test_cli_list_folders_exits_immediately():
    """Test that CLI exits immediately after --list-folders regardless of other flags"""
    import sys
    from unittest.mock import patch

    from teleflux.cli import main

    # Mock sys.argv to simulate command line arguments
    test_args = [
        "teleflux",
        "--config",
        "test_config.yml",
        "--list-folders",
        "--dry-run",  # This should be ignored
    ]

    with patch.object(sys, "argv", test_args):
        with patch("teleflux.cli.asyncio.run") as mock_run:
            with patch("teleflux.cli.Path") as mock_path:
                with patch("sys.exit") as mock_exit:
                    # Mock path exists
                    mock_path.return_value.exists.return_value = True

                    # Mock asyncio.run to return success
                    mock_run.return_value = 0  # Only one call expected

                    try:
                        main()
                    except SystemExit:
                        pass  # Expected due to sys.exit call

                    # Should call asyncio.run only once for list_folders, not for dry_run
                    assert mock_run.call_count == 1
                    mock_exit.assert_called_with(0)


@pytest.mark.asyncio
async def test_send_notification(test_telegram_config):
    """Test sending notification"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        client.client = mock_client

        await client.send_notification("Test message")

        mock_client.send_message.assert_called_once_with(
            chat_id="me", text="Test message"
        )


def test_generate_channel_hash(test_telegram_config):
    """Test channel hash generation"""
    client = TelegramClient(test_telegram_config)

    hash1 = client._generate_channel_hash(123456)
    hash2 = client._generate_channel_hash(123456)
    hash3 = client._generate_channel_hash(654321)

    # Same input should produce same hash
    assert hash1 == hash2

    # Different input should produce different hash
    assert hash1 != hash3

    # Hash should be 16 characters
    assert len(hash1) == 16
    assert len(hash3) == 16


@pytest.mark.asyncio
async def test_connect_disconnect(test_telegram_config):
    """Test connection and disconnection"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Test connect
        await client.connect()
        assert client.client is not None
        mock_client.start.assert_called_once()

        # Test disconnect
        await client.disconnect()
        mock_client.stop.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager(test_telegram_config):
    """Test async context manager"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        async with client as tg_client:
            assert tg_client is client
            assert client.client is not None
            mock_client.start.assert_called_once()

        mock_client.stop.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_folders_empty(test_telegram_config):
    """Test getting folders when no channels exist"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Create async iterator directly
        async_iter = AsyncIterator([])
        mock_client.get_dialogs = MagicMock(return_value=async_iter)

        client.client = mock_client

        # Mock the handle_flood_wait method to just call the function directly
        async def mock_handle_flood_wait(func, *args, **kwargs):
            return await func(*args, **kwargs)

        client.handle_flood_wait = mock_handle_flood_wait

        # Mock the _get_dialog_filters_with_peers method to return empty dict
        with patch.object(client, "_get_dialog_filters_with_peers") as mock_get_filters:
            mock_get_filters.return_value = {}

            folders = await client.get_all_folders()

            # Should return empty list
            assert len(folders) == 0


@pytest.mark.asyncio
async def test_get_channels_by_folders_handles_flood_wait(test_telegram_config):
    """Test that FloodWait errors are handled properly without application exit"""
    from unittest.mock import AsyncMock

    from pyrogram.errors import FloodWait

    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        client.client = mock_client

        # Mock the invoke method to raise FloodWait on first call, then succeed
        call_count = 0

        async def mock_invoke(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises FloodWait
                raise FloodWait(value=1)  # 1 second wait
            else:
                # Second call succeeds - create proper mock response
                from pyrogram.raw import functions

                if isinstance(request, functions.messages.GetPeerDialogs):
                    mock_response = MagicMock()

                    # Create mock dialog
                    mock_dialog = MagicMock()
                    mock_dialog.peer = MagicMock()
                    mock_dialog.peer.channel_id = 1126690784

                    # Create mock chat as regular object
                    mock_chat = MagicMock()
                    mock_chat.id = 1126690784
                    mock_chat.title = "Test Channel"
                    mock_chat.username = "testchannel"
                    mock_chat.broadcast = True
                    mock_chat.megagroup = False

                    mock_response.dialogs = [mock_dialog]
                    mock_response.chats = [mock_chat]
                    return mock_response

                return MagicMock()

        mock_client.invoke = AsyncMock(side_effect=mock_invoke)

        # Mock isinstance to make our mock objects pass the type checks
        original_isinstance = isinstance

        def custom_isinstance(obj, class_or_tuple):
            result = original_isinstance(obj, class_or_tuple)

            # Make our mock objects pass the appropriate type checks
            from pyrogram.raw.types import Channel, Chat, User

            if hasattr(obj, "broadcast") and hasattr(obj, "megagroup"):
                if class_or_tuple == Channel:
                    return True
            elif hasattr(obj, "title") and not hasattr(obj, "broadcast"):
                if class_or_tuple == Chat:
                    return True
            elif hasattr(obj, "first_name") or hasattr(obj, "username"):
                if class_or_tuple == User:
                    return True

            return result

        with patch(
            "teleflux.telegram_client.isinstance", side_effect=custom_isinstance
        ):
            # Mock the dialog filters
            with patch.object(
                client, "_get_dialog_filters_with_peers"
            ) as mock_get_filters:
                mock_peer = MagicMock()
                mock_peer.channel_id = 1126690784
                del mock_peer.user_id
                del mock_peer.chat_id

                mock_folder_info = {
                    "Test Folder": {
                        "id": 1,
                        "title": "Test Folder",
                        "type": "DialogFilter",
                        "include_peers": [mock_peer],
                        "exclude_peers": [],
                    }
                }
                mock_get_filters.return_value = mock_folder_info

                # Test that FloodWait is handled and doesn't cause application exit
                channels = await client.get_channels_by_folders(["Test Folder"])

                # Verify that the method completed successfully
                assert len(channels) == 1
                assert channels[0].title == "Test Channel"

                # Verify that invoke was called twice (first failed with FloodWait, second succeeded)
                assert call_count == 2


@pytest.mark.asyncio
async def test_get_unfoldered_channels(
    test_telegram_config, mock_dialogs, mock_dialog_filters
):
    """Test getting channels that are not in any folder"""
    client = TelegramClient(test_telegram_config)

    with patch("teleflux.telegram_client.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Create async iterator for get_dialogs
        async_iter = AsyncIterator(mock_dialogs)
        mock_client.get_dialogs = MagicMock(return_value=async_iter)

        client.client = mock_client

        # Mock the _get_dialog_filters_with_peers method
        with patch.object(client, "_get_dialog_filters_with_peers") as mock_get_filters:
            # Create mock folder info with include_peers for AI & Tech and News & Media folders only
            # This means Entertainment and Main channels will be unfoldered
            mock_peer1 = MagicMock()
            mock_peer1.channel_id = 200  # AI Channel 0
            del mock_peer1.user_id
            del mock_peer1.chat_id

            mock_peer2 = MagicMock()
            mock_peer2.channel_id = 201  # AI Channel 1
            del mock_peer2.user_id
            del mock_peer2.chat_id

            mock_peer3 = MagicMock()
            mock_peer3.channel_id = 300  # Private News Channel 0
            del mock_peer3.user_id
            del mock_peer3.chat_id

            mock_folder_info = {
                "AI & Tech": {
                    "id": 1,
                    "title": "AI & Tech",
                    "type": "DialogFilter",
                    "include_peers": [mock_peer1, mock_peer2],  # Only AI channels
                },
                "News & Media": {
                    "id": 2,
                    "title": "News & Media",
                    "type": "DialogFilter",
                    "include_peers": [mock_peer3],  # Only private news channel
                },
                # Entertainment folder is not included, so Entertainment Channel 0 will be unfoldered
                # Main channels (100, 101, 102) are also not included, so they will be unfoldered
            }
            mock_get_filters.return_value = mock_folder_info

            channels = await client.get_unfoldered_channels()

            # Should return 4 channels: 3 Main channels + 1 Entertainment channel
            assert len(channels) == 4

            # Check that we got the right channels (Main and Entertainment)
            channel_titles = [c.title for c in channels]
            assert "Main Channel 0" in channel_titles
            assert "Main Channel 1" in channel_titles
            assert "Main Channel 2" in channel_titles
            assert "Entertainment Channel 0" in channel_titles

            # Check that all returned channels have folder_name=None
            for channel in channels:
                assert channel.folder_name is None

            # Check that AI and News channels are NOT in the result
            ai_titles = ["AI Channel 0", "AI Channel 1"]
            news_titles = ["Private News Channel 0"]
            for title in ai_titles + news_titles:
                assert title not in channel_titles


@pytest.mark.asyncio
async def test_cli_list_unfoldered_channels():
    """Test that CLI can handle --list-unfoldered-channels flag"""
    import sys
    from unittest.mock import patch

    from teleflux.cli import main

    # Mock sys.argv to simulate command line arguments
    test_args = [
        "teleflux",
        "--config",
        "test_config.yml",
        "--list-unfoldered-channels",
    ]

    with patch.object(sys, "argv", test_args):
        with patch("teleflux.cli.asyncio.run") as mock_run:
            with patch("teleflux.cli.Path") as mock_path:
                with patch("sys.exit") as mock_exit:
                    # Mock path exists
                    mock_path.return_value.exists.return_value = True

                    # Mock asyncio.run to return success
                    mock_run.return_value = 0

                    try:
                        main()
                    except SystemExit:
                        pass  # Expected due to sys.exit call

                    # Should call asyncio.run once for list_unfoldered_channels_async
                    assert mock_run.call_count == 1
                    mock_exit.assert_called_with(0)
