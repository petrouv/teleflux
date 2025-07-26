"""
Synchronization module tests
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from teleflux.config import (
    Config,
    LoggingConfig,
    MinifluxConfig,
    RssHubConfig,
    SyncConfig,
    TelegramConfig,
)
from teleflux.miniflux_client import MinifluxCategory, MinifluxFeed
from teleflux.sync import SyncAction, SyncResult, TelefluxSyncer
from teleflux.telegram_client import TelegramChannel, TelegramFolder


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    return Config(
        telegram=TelegramConfig(
            api_id="12345",
            api_hash="test_hash",
            session_file="test.session",
            notify_chat_id="me",
        ),
        miniflux=MinifluxConfig(url="http://localhost:8080", token="test_token"),
        rsshub=RssHubConfig(base_url="http://localhost:1200"),
        sync=SyncConfig(
            folders={"News": "News", "Tech": "Technology"},
            remove_absent_feeds=True,
            private_feed_mode="secret",
            validate_feeds=True,
            notify_no_changes=False,
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def test_channels():
    """Test channels fixture"""
    return [
        TelegramChannel(
            id=123456,
            username="test_channel",
            title="Test Channel",
            is_private=False,
            folder_name="News",
        ),
        TelegramChannel(
            id=-987654,
            username=None,
            title="Private Channel",
            is_private=True,
            folder_name="Tech",
            channel_hash="abc123",
        ),
    ]


@pytest.fixture
def test_folders():
    """Test folders fixture"""
    return [
        TelegramFolder(id=None, name="Main", channel_count=5),
        TelegramFolder(id=1, name="Folder_1", channel_count=3),
        TelegramFolder(id=2, name="Folder_2", channel_count=2),
    ]


@pytest.fixture
def test_categories():
    """Test categories fixture"""
    return [
        MinifluxCategory(id=1, title="News"),
        MinifluxCategory(id=2, title="Technology"),
    ]


@pytest.fixture
def test_feeds():
    """Test feeds fixture"""
    return [
        MinifluxFeed(
            id=1,
            title="Old Feed",
            feed_url="http://localhost:1200/telegram/channel/old_channel",
            category_id=1,
        )
    ]


def test_build_rss_url_public_channel(test_config):
    """Test RSS URL building for public channel"""
    syncer = TelefluxSyncer(test_config)

    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Test Channel",
        is_private=False,
        folder_name="News",
    )

    url = syncer._build_rss_url(channel)
    assert url == "http://localhost:1200/telegram/channel/test_channel"


def test_build_rss_url_private_channel_secret_mode(test_config):
    """Test RSS URL building for private channel in secret mode"""
    syncer = TelefluxSyncer(test_config)

    channel = TelegramChannel(
        id=-987654,
        username=None,
        title="Private Channel",
        is_private=True,
        folder_name="Tech",
        channel_hash="abc123",
    )

    url = syncer._build_rss_url(channel)
    assert url == "http://localhost:1200/telegram/channel/987654?secret=abc123"


def test_build_rss_url_private_channel_skip_mode(test_config):
    """Test RSS URL building for private channel in skip mode"""
    test_config.sync.private_feed_mode = "skip"
    syncer = TelefluxSyncer(test_config)

    channel = TelegramChannel(
        id=-987654,
        username=None,
        title="Private Channel",
        is_private=True,
        folder_name="Tech",
        channel_hash="abc123",
    )

    url = syncer._build_rss_url(channel)
    assert url == ""


def test_build_rss_url_public_channel_no_username(test_config):
    """Test RSS URL building for public channel without username"""
    syncer = TelefluxSyncer(test_config)

    channel = TelegramChannel(
        id=123456,
        username=None,
        title="Test Channel",
        is_private=False,
        folder_name="News",
    )

    url = syncer._build_rss_url(channel)
    assert url == ""


def test_is_telegram_feed_public_channel(test_config):
    """Test Telegram feed detection for public channel"""
    syncer = TelefluxSyncer(test_config)

    # Telegram feed URL
    telegram_url = "http://localhost:1200/telegram/channel/test_channel"
    assert syncer._is_telegram_feed(telegram_url) is True

    # Non-Telegram feed URL
    non_telegram_url = "https://techcrunch.com/category/artificial-intelligence/feed/"
    assert syncer._is_telegram_feed(non_telegram_url) is False

    # Different RssHub URL (not our instance)
    different_rsshub_url = "http://other-rsshub.com/telegram/channel/test_channel"
    assert syncer._is_telegram_feed(different_rsshub_url) is False


def test_is_telegram_feed_private_channel(test_config):
    """Test Telegram feed detection for private channel"""
    syncer = TelefluxSyncer(test_config)

    # Private Telegram feed URL with secret
    private_url = "http://localhost:1200/telegram/channel/123456?secret=abc123"
    assert syncer._is_telegram_feed(private_url) is True

    # URL with telegram path but different domain
    wrong_domain_url = "http://example.com/telegram/channel/123456"
    assert syncer._is_telegram_feed(wrong_domain_url) is False


@pytest.mark.asyncio
async def test_sync_folders_happy_path(
    test_config, test_channels, test_categories, test_feeds, test_folders
):
    """Test successful folder synchronization"""
    syncer = TelefluxSyncer(test_config)

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = test_channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=test_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=test_categories)
        syncer.miniflux_client.get_or_create_category = MagicMock()
        syncer.miniflux_client.create_feed = MagicMock()
        syncer.miniflux_client.delete_feed = MagicMock()

        # Setup return values for category creation
        syncer.miniflux_client.get_or_create_category.side_effect = test_categories

        # Perform synchronization
        result = await syncer.sync_folders()

        # Check result
        assert isinstance(result, SyncResult)
        assert len(result.added_feeds) == 2  # Two new channels
        assert len(result.removed_feeds) == 1  # One old feed removed
        assert len(result.errors) == 0
        assert result.dry_run is False

        # Check method calls
        mock_tg_instance.get_channels_by_folders.assert_called_once_with(
            ["News", "Tech"]
        )
        assert syncer.miniflux_client.create_feed.call_count == 2
        assert syncer.miniflux_client.delete_feed.call_count == 1


@pytest.mark.asyncio
async def test_sync_folders_dry_run(
    test_config, test_channels, test_categories, test_feeds, test_folders
):
    """Test dry run synchronization"""
    syncer = TelefluxSyncer(test_config)

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = test_channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=test_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=test_categories)
        syncer.miniflux_client.create_feed = MagicMock()
        syncer.miniflux_client.delete_feed = MagicMock()

        # Perform dry run synchronization
        result = await syncer.sync_folders(dry_run=True)

        # Check result
        assert isinstance(result, SyncResult)
        assert len(result.added_feeds) == 2  # Two new channels would be added
        assert len(result.removed_feeds) == 1  # One old feed would be removed
        assert len(result.errors) == 0
        assert result.dry_run is True

        # Check that no actual changes were made
        syncer.miniflux_client.create_feed.assert_not_called()
        syncer.miniflux_client.delete_feed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_folders_with_errors(test_config):
    """Test synchronization with errors"""
    syncer = TelefluxSyncer(test_config)

    # Mock TelegramClient with error
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_client.return_value.__aenter__.side_effect = Exception(
            "Connection error"
        )

        # Perform synchronization
        result = await syncer.sync_folders()

        # Check result
        assert isinstance(result, SyncResult)
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.errors) == 1
        assert "Failed to get channels from Telegram" in result.errors[0]


@pytest.mark.asyncio
async def test_sync_folders_add_feeds_only(test_config):
    """Test folder synchronization - add feeds only"""
    syncer = TelefluxSyncer(test_config)

    channels = [
        TelegramChannel(
            id=123456,
            username="new_channel",
            title="New Channel",
            is_private=False,
            folder_name="News",
        )
    ]

    categories = [MinifluxCategory(id=1, title="News")]
    existing_feeds = []  # No existing feeds

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.get_or_create_category = MagicMock(
            return_value=categories[0]
        )
        syncer.miniflux_client.create_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders()

        # Check result
        assert len(result.added_feeds) == 1
        assert len(result.removed_feeds) == 0
        assert len(result.errors) == 0
        assert result.added_feeds[0].channel_title == "New Channel"
        assert result.added_feeds[0].action == "add"

        # Check calls
        syncer.miniflux_client.create_feed.assert_called_once_with(
            "http://localhost:1200/telegram/channel/new_channel",
            1,
            validate=True,
            title="New Channel",
        )


@pytest.mark.asyncio
async def test_sync_folders_remove_feeds_only(test_config):
    """Test folder synchronization with only feed removal"""
    syncer = TelefluxSyncer(test_config)

    # Mock existing feeds that should be removed
    existing_feeds = [
        MinifluxFeed(
            id=1,
            title="Old Feed",
            feed_url="http://localhost:1200/telegram/channel/old_channel",
            category_id=1,
        )
    ]

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = []  # No channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.delete_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Verify feed was deleted
        syncer.miniflux_client.delete_feed.assert_called_once_with(1)

        # Verify result
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 1
        assert result.removed_feeds[0].action == "remove"
        assert result.removed_feeds[0].channel_title == "Old Feed"
        assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_sync_folders_update_titles(test_config):
    """Test folder synchronization with title updates"""
    syncer = TelefluxSyncer(test_config)

    # Channel with updated title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Updated Channel Title",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with old title
    existing_feed = MinifluxFeed(
        id=1,
        title="Old Channel Title",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Check result
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.updated_titles) == 1
        assert result.updated_titles[0].old_title == "Old Channel Title"
        assert len(result.errors) == 0

        # Title should be updated
        syncer.miniflux_client.update_feed.assert_called_once_with(
            1, "Updated Channel Title"
        )


@pytest.mark.asyncio
async def test_sync_folders_move_feeds(test_config):
    """Test folder synchronization with feed moves between categories"""
    syncer = TelefluxSyncer(test_config)

    # Channel that should be in Tech category
    channel = TelegramChannel(
        id=123456,
        username="tech_channel",
        title="Tech Channel",
        is_private=False,
        folder_name="Tech",
    )

    # Existing feed in wrong category (News instead of Tech)
    existing_feed = MinifluxFeed(
        id=1,
        title="Tech Channel",
        feed_url="http://localhost:1200/telegram/channel/tech_channel",
        category_id=1,  # News category
    )

    categories = [
        MinifluxCategory(id=1, title="News"),
        MinifluxCategory(id=2, title="Technology"),
    ]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed_category = MagicMock()
        syncer.miniflux_client.get_category_by_id = MagicMock(
            return_value=categories[0]
        )  # News category

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Check result
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.moved_feeds) == 1
        assert result.moved_feeds[0].action == "move_category"
        assert result.moved_feeds[0].channel_title == "Tech Channel"
        assert result.moved_feeds[0].category_name == "Technology"
        assert result.moved_feeds[0].old_category == "News"
        assert len(result.errors) == 0

        # Check that update_feed_category was called
        syncer.miniflux_client.update_feed_category.assert_called_once_with(1, 2)


@pytest.mark.asyncio
async def test_plan_synchronization_conflict_resolution(test_config):
    """Test synchronization planning with conflict resolution"""
    syncer = TelefluxSyncer(test_config)

    # Channel that appears in multiple folders
    channels = [
        TelegramChannel(
            id=123456,
            username="shared_channel",
            title="Shared Channel",
            is_private=False,
            folder_name="News",  # First folder (higher priority)
        ),
        TelegramChannel(
            id=123456,
            username="shared_channel",
            title="Shared Channel",
            is_private=False,
            folder_name="Tech",  # Second folder (lower priority)
        ),
    ]

    # Test planning
    channel_assignments, conflicts = await syncer._plan_synchronization(channels)

    # Check that conflict was detected
    assert len(conflicts) == 1
    assert conflicts[0]["channel"].title == "Shared Channel"
    assert conflicts[0]["existing_folder"] == "News"
    assert conflicts[0]["new_folder"] == "Tech"

    # Check that channel was assigned to first folder (higher priority)
    feed_url = "http://localhost:1200/telegram/channel/shared_channel"
    assert feed_url in channel_assignments
    category_name, folder_name, channel = channel_assignments[feed_url]
    assert category_name == "News"
    assert folder_name == "News"


def test_filter_channels_secret_mode(test_config):
    """Test channel filtering in secret mode"""
    syncer = TelefluxSyncer(test_config)

    channels = [
        TelegramChannel(
            id=123456,
            username="public_channel",
            title="Public Channel",
            is_private=False,
            folder_name="News",
        ),
        TelegramChannel(
            id=-987654,
            username=None,
            title="Private Channel",
            is_private=True,
            folder_name="Tech",
            channel_hash="abc123",
        ),
    ]

    # In secret mode, all channels should be kept
    filtered = syncer._filter_channels(channels)
    assert len(filtered) == 2


def test_filter_channels_skip_mode(test_config):
    """Test channel filtering in skip mode"""
    test_config.sync.private_feed_mode = "skip"
    syncer = TelefluxSyncer(test_config)

    channels = [
        TelegramChannel(
            id=123456,
            username="public_channel",
            title="Public Channel",
            is_private=False,
            folder_name="News",
        ),
        TelegramChannel(
            id=-987654,
            username=None,
            title="Private Channel",
            is_private=True,
            folder_name="Tech",
            channel_hash="abc123",
        ),
    ]

    # In skip mode, private channels should be filtered out
    filtered = syncer._filter_channels(channels)
    assert len(filtered) == 1
    assert filtered[0].title == "Public Channel"


def test_filter_channels_empty_list(test_config):
    """Test channel filtering with empty list"""
    syncer = TelefluxSyncer(test_config)

    filtered = syncer._filter_channels([])
    assert len(filtered) == 0


def test_build_rss_url_case_insensitive(test_config):
    """Test RSS URL building with case insensitive usernames"""
    syncer = TelefluxSyncer(test_config)

    channel = TelegramChannel(
        id=123456,
        username="Test_Channel",
        title="Test Channel",
        is_private=False,
        folder_name="News",
    )

    url = syncer._build_rss_url(channel)
    # Username should be converted to lowercase
    assert url == "http://localhost:1200/telegram/channel/test_channel"


def test_normalize_url_for_comparison(test_config):
    """Test URL normalization for case-insensitive comparison"""
    syncer = TelefluxSyncer(test_config)

    url1 = "http://localhost:1200/telegram/channel/Test_Channel"
    url2 = "HTTP://LOCALHOST:1200/TELEGRAM/CHANNEL/TEST_CHANNEL"

    normalized1 = syncer._normalize_url_for_comparison(url1)
    normalized2 = syncer._normalize_url_for_comparison(url2)

    assert normalized1 == normalized2
    assert normalized1 == "http://localhost:1200/telegram/channel/test_channel"


def test_create_url_mapping(test_config):
    """Test URL mapping creation for case-insensitive comparison"""
    syncer = TelefluxSyncer(test_config)

    urls = {
        "http://localhost:1200/telegram/channel/Test_Channel",
        "http://localhost:1200/telegram/channel/Another_Channel",
    }

    mapping = syncer._create_url_mapping(urls)

    assert len(mapping) == 2
    assert "http://localhost:1200/telegram/channel/test_channel" in mapping
    assert "http://localhost:1200/telegram/channel/another_channel" in mapping

    # Original URLs should be preserved as values
    assert (
        mapping["http://localhost:1200/telegram/channel/test_channel"]
        == "http://localhost:1200/telegram/channel/Test_Channel"
    )


def test_find_matching_url(test_config):
    """Test finding matching URL using case-insensitive comparison"""
    syncer = TelefluxSyncer(test_config)

    urls = {
        "http://localhost:1200/telegram/channel/Test_Channel",
        "http://localhost:1200/telegram/channel/Another_Channel",
    }

    mapping = syncer._create_url_mapping(urls)

    # Test case-insensitive matching
    target_url = "HTTP://LOCALHOST:1200/TELEGRAM/CHANNEL/TEST_CHANNEL"
    match = syncer._find_matching_url(target_url, mapping)

    assert match == "http://localhost:1200/telegram/channel/Test_Channel"

    # Test no match
    no_match_url = "http://localhost:1200/telegram/channel/nonexistent"
    no_match = syncer._find_matching_url(no_match_url, mapping)

    assert no_match is None


@pytest.mark.asyncio
async def test_sync_folders_case_insensitive_matching(test_config):
    """Test case-insensitive URL matching during synchronization"""
    syncer = TelefluxSyncer(test_config)

    # Channel with mixed case username
    channels = [
        TelegramChannel(
            id=123456,
            username="Test_Channel",
            title="Test Channel",
            is_private=False,
            folder_name="News",
        )
    ]

    # Existing feed with different case URL
    existing_feeds = [
        MinifluxFeed(
            id=1,
            title="Test Channel",
            feed_url="http://localhost:1200/telegram/channel/test_channel",  # lowercase
            category_id=1,
        )
    ]

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.create_feed = MagicMock()
        syncer.miniflux_client.delete_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders()

        # Should not add or remove feeds due to case-insensitive matching
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.errors) == 0

        # No feeds should be created or deleted
        syncer.miniflux_client.create_feed.assert_not_called()
        syncer.miniflux_client.delete_feed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_folders_case_insensitive_title_update(test_config):
    """Test case-insensitive URL matching with title updates"""
    syncer = TelefluxSyncer(test_config)

    # Channel with mixed case username and updated title
    channels = [
        TelegramChannel(
            id=123456,
            username="Test_Channel",
            title="Updated Channel Title",
            is_private=False,
            folder_name="News",
        )
    ]

    # Existing feed with different case URL and old title
    existing_feeds = [
        MinifluxFeed(
            id=1,
            title="Old Channel Title",
            feed_url="http://localhost:1200/telegram/channel/test_channel",  # lowercase
            category_id=1,
        )
    ]

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should update title due to case-insensitive URL matching
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.updated_titles) == 1
        assert result.updated_titles[0].old_title == "Old Channel Title"
        assert len(result.errors) == 0

        # Title should be updated
        syncer.miniflux_client.update_feed.assert_called_once_with(
            1, "Updated Channel Title"
        )


@pytest.mark.asyncio
async def test_sync_folders_update_titles_remove_emojis_default(test_config):
    """Test title updates with emoji removal (default behavior)"""
    syncer = TelefluxSyncer(test_config)

    # Channel with emojis in title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="📰 News Channel 🔥",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with emojis in title
    existing_feed = MinifluxFeed(
        id=1,
        title="📰 News Channel 🔥",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should update title to remove emojis
        assert len(result.updated_titles) == 1
        assert result.updated_titles[0].old_title == "📰 News Channel 🔥"

        # Title should be updated with emojis removed
        syncer.miniflux_client.update_feed.assert_called_once_with(1, "News Channel")


@pytest.mark.asyncio
async def test_sync_folders_update_titles_keep_emojis_enabled(test_config):
    """Test title updates with emoji preservation when enabled"""
    test_config.sync.keep_emojis_in_titles = True
    syncer = TelefluxSyncer(test_config)

    # Channel with emojis in title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="📰 News Channel 🔥",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with different title
    existing_feed = MinifluxFeed(
        id=1,
        title="Old News Channel",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should update title keeping emojis
        assert len(result.updated_titles) == 1
        assert result.updated_titles[0].old_title == "Old News Channel"

        # Title should be updated with emojis preserved
        syncer.miniflux_client.update_feed.assert_called_once_with(
            1, "📰 News Channel 🔥"
        )


@pytest.mark.asyncio
async def test_sync_folders_update_titles_no_change_needed_with_emojis(test_config):
    """Test that no title update occurs when titles match after emoji processing"""
    syncer = TelefluxSyncer(test_config)

    # Channel with emojis in title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="📰 News Channel 🔥",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with title that matches after emoji removal
    existing_feed = MinifluxFeed(
        id=1,
        title="News Channel",  # Matches channel title after emoji removal
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should not update title since it matches after emoji removal
        assert len(result.updated_titles) == 0

        # No title update should occur
        syncer.miniflux_client.update_feed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_folders_add_feed_remove_emojis_default(test_config):
    """Test adding new feed with emoji removal (default behavior)"""
    syncer = TelefluxSyncer(test_config)

    # Channel with emojis in title
    channel = TelegramChannel(
        id=123456,
        username="new_channel",
        title="📰 New Channel 🔥",
        is_private=False,
        folder_name="News",
    )

    categories = [MinifluxCategory(id=1, title="News")]
    existing_feeds = []  # No existing feeds

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.get_or_create_category = MagicMock(
            return_value=categories[0]
        )
        syncer.miniflux_client.create_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should add feed with emojis removed from title
        assert len(result.added_feeds) == 1
        assert result.added_feeds[0].channel_title == "📰 New Channel 🔥"

        # Feed should be created with emojis removed from title
        syncer.miniflux_client.create_feed.assert_called_once_with(
            "http://localhost:1200/telegram/channel/new_channel",
            1,
            validate=True,
            title="New Channel",  # Emojis removed
        )


@pytest.mark.asyncio
async def test_sync_folders_add_feed_keep_emojis_enabled(test_config):
    """Test adding new feed with emoji preservation when enabled"""
    test_config.sync.keep_emojis_in_titles = True
    syncer = TelefluxSyncer(test_config)

    # Channel with emojis in title
    channel = TelegramChannel(
        id=123456,
        username="new_channel",
        title="📰 New Channel 🔥",
        is_private=False,
        folder_name="News",
    )

    categories = [MinifluxCategory(id=1, title="News")]
    existing_feeds = []  # No existing feeds

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.get_or_create_category = MagicMock(
            return_value=categories[0]
        )
        syncer.miniflux_client.create_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should add feed with emojis preserved in title
        assert len(result.added_feeds) == 1
        assert result.added_feeds[0].channel_title == "📰 New Channel 🔥"

        # Feed should be created with emojis preserved in title
        syncer.miniflux_client.create_feed.assert_called_once_with(
            "http://localhost:1200/telegram/channel/new_channel",
            1,
            validate=True,
            title="📰 New Channel 🔥",  # Emojis preserved
        )


@pytest.mark.asyncio
async def test_sync_folders_title_updates_enabled_by_default(test_config):
    """Test that title updates are enabled by default"""
    syncer = TelefluxSyncer(test_config)

    # Channel with updated title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Updated Channel Title",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with old title
    existing_feed = MinifluxFeed(
        id=1,
        title="Old Channel Title",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should update title since title updates are enabled by default
        assert len(result.updated_titles) == 1
        assert result.updated_titles[0].old_title == "Old Channel Title"

        # Title should be updated
        syncer.miniflux_client.update_feed.assert_called_once_with(
            1, "Updated Channel Title"
        )


@pytest.mark.asyncio
async def test_sync_folders_title_updates_disabled_by_config(test_config):
    """Test that title updates can be disabled by configuration"""
    test_config.sync.disable_title_updates = True
    syncer = TelefluxSyncer(test_config)

    # Channel with updated title
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Updated Channel Title",
        is_private=False,
        folder_name="News",
    )

    # Existing feed with old title
    existing_feed = MinifluxFeed(
        id=1,
        title="Old Channel Title",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.update_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should not update title since title updates are disabled
        assert len(result.updated_titles) == 0

        # No title update should occur
        syncer.miniflux_client.update_feed.assert_not_called()


def test_sync_action_dataclass():
    """Test SyncAction dataclass with all fields"""
    # Test basic action
    action = SyncAction(
        action="add",
        channel_title="Test Channel",
        feed_url="http://example.com/feed",
        category_name="News",
    )

    assert action.action == "add"
    assert action.channel_title == "Test Channel"
    assert action.feed_url == "http://example.com/feed"
    assert action.category_name == "News"
    assert action.old_title is None
    assert action.old_category is None

    # Test action with old_title
    update_action = SyncAction(
        action="update_title",
        channel_title="New Title",
        feed_url="http://example.com/feed",
        category_name="News",
        old_title="Old Title",
    )

    assert update_action.old_title == "Old Title"

    # Test action with old_category
    move_action = SyncAction(
        action="move_category",
        channel_title="Test Channel",
        feed_url="http://example.com/feed",
        category_name="Tech",
        old_category="News",
    )

    assert move_action.old_category == "News"


def test_sync_result_dataclass():
    """Test SyncResult dataclass with all fields"""
    # Create sample actions
    add_action = SyncAction("add", "Channel 1", "http://example.com/1", "News")
    remove_action = SyncAction("remove", "Channel 2", "http://example.com/2", "Tech")
    update_action = SyncAction(
        "update_title",
        "Channel 3",
        "http://example.com/3",
        "News",
        old_title="Old Title",
    )
    move_action = SyncAction(
        "move_category",
        "Channel 4",
        "http://example.com/4",
        "Tech",
        old_category="News",
    )

    result = SyncResult(
        added_feeds=[add_action],
        removed_feeds=[remove_action],
        updated_titles=[update_action],
        moved_feeds=[move_action],
        errors=["Test error"],
        dry_run=True,
    )

    assert len(result.added_feeds) == 1
    assert len(result.removed_feeds) == 1
    assert len(result.updated_titles) == 1
    assert len(result.moved_feeds) == 1
    assert len(result.errors) == 1
    assert result.dry_run is True

    # Test default values
    default_result = SyncResult(
        added_feeds=[], removed_feeds=[], updated_titles=[], moved_feeds=[], errors=[]
    )

    assert default_result.dry_run is False


def test_get_category_name_by_id(test_config):
    """Test _get_category_name_by_id helper method"""
    syncer = TelefluxSyncer(test_config)

    # Mock successful category retrieval
    category = MinifluxCategory(id=1, title="News")
    syncer.miniflux_client.get_category_by_id = MagicMock(return_value=category)

    result = syncer._get_category_name_by_id(1)
    assert result == "News"
    syncer.miniflux_client.get_category_by_id.assert_called_once_with(1)

    # Mock category not found
    syncer.miniflux_client.get_category_by_id = MagicMock(return_value=None)

    result = syncer._get_category_name_by_id(999)
    assert result == "Category 999"

    # Mock exception
    syncer.miniflux_client.get_category_by_id = MagicMock(
        side_effect=Exception("API Error")
    )

    result = syncer._get_category_name_by_id(1)
    assert result == "Category 1"


@pytest.mark.asyncio
async def test_sync_folders_complex_scenario(test_config):
    """Test complex synchronization scenario with multiple operations"""
    syncer = TelefluxSyncer(test_config)

    # Channels: one new, one to move, one to update title
    channels = [
        TelegramChannel(
            id=123456,
            username="new_channel",
            title="New Channel",
            is_private=False,
            folder_name="News",
        ),
        TelegramChannel(
            id=789012,
            username="move_channel",
            title="Move Channel",
            is_private=False,
            folder_name="Tech",  # Should move from News to Tech
        ),
        TelegramChannel(
            id=345678,
            username="update_channel",
            title="Updated Title",
            is_private=False,
            folder_name="News",
        ),
    ]

    # Existing feeds
    existing_feeds = [
        MinifluxFeed(
            id=1,
            title="Move Channel",
            feed_url="http://localhost:1200/telegram/channel/move_channel",
            category_id=1,  # News category, should move to Tech
        ),
        MinifluxFeed(
            id=2,
            title="Old Title",
            feed_url="http://localhost:1200/telegram/channel/update_channel",
            category_id=1,  # News category, should update title
        ),
        MinifluxFeed(
            id=3,
            title="Remove Channel",
            feed_url="http://localhost:1200/telegram/channel/remove_channel",
            category_id=1,  # Should be removed
        ),
    ]

    categories = [
        MinifluxCategory(id=1, title="News"),
        MinifluxCategory(id=2, title="Technology"),
    ]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = channels

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.get_or_create_category = MagicMock(
            return_value=categories[0]
        )
        syncer.miniflux_client.create_feed = MagicMock()
        syncer.miniflux_client.update_feed = MagicMock()
        syncer.miniflux_client.update_feed_category = MagicMock()
        syncer.miniflux_client.delete_feed = MagicMock()
        syncer.miniflux_client.get_category_by_id = MagicMock(
            return_value=categories[0]
        )

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Check results
        assert len(result.added_feeds) == 1  # new_channel
        assert len(result.moved_feeds) == 1  # move_channel
        assert len(result.updated_titles) == 1  # update_channel
        assert len(result.removed_feeds) == 1  # remove_channel
        assert len(result.errors) == 0

        # Check specific actions
        assert result.added_feeds[0].channel_title == "New Channel"
        assert result.moved_feeds[0].channel_title == "Move Channel"
        assert result.moved_feeds[0].category_name == "Technology"
        assert result.moved_feeds[0].old_category == "News"
        assert result.updated_titles[0].channel_title == "Updated Title"
        assert result.updated_titles[0].old_title == "Old Title"
        assert result.removed_feeds[0].channel_title == "Remove Channel"

        # Check method calls
        syncer.miniflux_client.create_feed.assert_called_once()
        syncer.miniflux_client.update_feed_category.assert_called_once_with(1, 2)
        syncer.miniflux_client.update_feed.assert_called_once_with(2, "Updated Title")
        syncer.miniflux_client.delete_feed.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_sync_folders_no_changes_optimization(test_config):
    """Test that sync_folders optimizes when no changes are needed"""
    syncer = TelefluxSyncer(test_config)

    # Channel that matches existing feed exactly
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Test Channel",
        is_private=False,
        folder_name="News",
    )

    # Existing feed that matches perfectly
    existing_feed = MinifluxFeed(
        id=1,
        title="Test Channel",
        feed_url="http://localhost:1200/telegram/channel/test_channel",
        category_id=1,
    )

    categories = [MinifluxCategory(id=1, title="News")]

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=[existing_feed])
        syncer.miniflux_client.get_categories = MagicMock(return_value=categories)
        syncer.miniflux_client.create_feed = MagicMock()
        syncer.miniflux_client.update_feed = MagicMock()
        syncer.miniflux_client.update_feed_category = MagicMock()
        syncer.miniflux_client.delete_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should have no changes
        assert len(result.added_feeds) == 0
        assert len(result.removed_feeds) == 0
        assert len(result.updated_titles) == 0
        assert len(result.moved_feeds) == 0
        assert len(result.errors) == 0

        # No API calls should be made for changes
        syncer.miniflux_client.create_feed.assert_not_called()
        syncer.miniflux_client.update_feed.assert_not_called()
        syncer.miniflux_client.update_feed_category.assert_not_called()
        syncer.miniflux_client.delete_feed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_folders_with_new_category_creation(test_config):
    """Test synchronization with new category creation"""
    syncer = TelefluxSyncer(test_config)

    # Channel for a category that doesn't exist yet
    channel = TelegramChannel(
        id=123456,
        username="test_channel",
        title="Test Channel",
        is_private=False,
        folder_name="News",
    )

    # No existing categories (will need to create News category)
    existing_categories = []
    existing_feeds = []

    # New category that will be created
    new_category = MinifluxCategory(id=1, title="News")

    # Mock TelegramClient
    with patch("teleflux.sync.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance
        mock_tg_instance.get_channels_by_folders.return_value = [channel]

        # Mock MinifluxClient methods
        syncer.miniflux_client.get_feeds = MagicMock(return_value=existing_feeds)
        syncer.miniflux_client.get_categories = MagicMock(
            return_value=existing_categories
        )
        syncer.miniflux_client.get_or_create_category = MagicMock(
            return_value=new_category
        )
        syncer.miniflux_client.create_feed = MagicMock()

        # Perform synchronization
        result = await syncer.sync_folders(dry_run=False)

        # Should create new category and add feed
        assert len(result.added_feeds) == 1
        assert result.added_feeds[0].category_name == "News"

        # Check that category was created
        syncer.miniflux_client.get_or_create_category.assert_called_once_with("News")

        # Check that feed was created in new category
        syncer.miniflux_client.create_feed.assert_called_once_with(
            "http://localhost:1200/telegram/channel/test_channel",
            1,
            validate=True,
            title="Test Channel",
        )
