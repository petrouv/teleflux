"""
Notification module tests
"""

from unittest.mock import AsyncMock, patch

import pytest

from teleflux.config import (
    Config,
    LoggingConfig,
    MinifluxConfig,
    RssHubConfig,
    SyncConfig,
    TelegramConfig,
)
from teleflux.notifier import TelegramNotifier
from teleflux.sync import SyncAction, SyncResult


@pytest.fixture
def test_telegram_config():
    """Test Telegram configuration fixture"""
    return TelegramConfig(
        api_id="12345",
        api_hash="test_hash",
        session_file="test.session",
        notify_chat_id="me",
    )


@pytest.fixture
def test_config():
    """Test full configuration fixture"""
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
            folders={"Test": "Test"},
            remove_absent_feeds=True,
            private_feed_mode="secret",
            validate_feeds=True,
            notify_no_changes=False,
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def test_config_with_notifications():
    """Test configuration with notify_no_changes enabled"""
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
            folders={"Test": "Test"},
            remove_absent_feeds=True,
            private_feed_mode="secret",
            validate_feeds=True,
            notify_no_changes=True,
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def test_sync_result():
    """Test sync result with some data"""
    return SyncResult(
        added_feeds=[
            SyncAction("add", "Test Channel 1", "http://example.com/1", "Tech"),
            SyncAction("add", "Test Channel 2", "http://example.com/2", "Tech"),
        ],
        removed_feeds=[SyncAction("remove", "Old Channel", "http://old.com", "Tech")],
        updated_titles=[
            SyncAction(
                action="update_title",
                channel_title="Updated Channel",
                feed_url="http://localhost:1200/telegram/channel/test",
                category_name="Tech",
                old_title="Old Title",
            )
        ],
        moved_feeds=[],
        errors=["Test error"],
        dry_run=False,
    )


@pytest.fixture
def test_dry_run_result():
    """Test dry run result"""
    return SyncResult(
        added_feeds=[SyncAction("add", "Test Channel", "http://example.com", "Tech")],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )


def test_format_sync_message_normal(test_config):
    """Test sync message formatting for normal mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[SyncAction("add", "Test Channel", "http://example.com", "News")],
        removed_feeds=[SyncAction("remove", "Old Channel", "http://old.com", "News")],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Added: 1 | Removed: 1" in message
    assert "**Added feeds** (1):" in message
    assert "**Removed feeds** (1):" in message
    assert "Test Channel" in message
    assert "Old Channel" in message
    assert "Sync Status: Synchronization completed successfully" in message
    # Check that status is first line
    assert message.startswith("Sync Status: Synchronization completed successfully")


def test_format_sync_message_dry_run(test_config):
    """Test sync message formatting for dry run mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[SyncAction("add", "Test Channel", "http://example.com", "News")],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Added: 1 (DRY RUN)" in message
    assert "**Would add feeds** (1):" in message
    assert "Test Channel" in message
    assert "Sync Status: Dry run completed successfully" in message
    # Check that status is first line
    assert message.startswith("Sync Status: Dry run completed successfully")


def test_format_sync_message_no_changes_normal(test_config):
    """Test sync message formatting with no changes in normal mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "Sync Status: No changes required" in message
    # Check that status is first line
    assert message.startswith("Sync Status: No changes required")


def test_format_sync_message_no_changes_dry_run(test_config):
    """Test sync message formatting with no changes in dry run mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "Sync Status: No changes would be made" in message
    # Check that status is first line
    assert message.startswith("Sync Status: No changes would be made")


def test_format_sync_message_with_errors_normal(test_config):
    """Test sync message formatting with errors in normal mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=["Error 1", "Error 2"],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Errors: 2" in message
    assert "**Errors** (2):" in message
    assert "Error 1" in message
    assert "Error 2" in message
    assert "Sync Status: ⚠️ Synchronization completed with errors" in message
    # Check that status is first line
    assert message.startswith("Sync Status: ⚠️ Synchronization completed with errors")


def test_format_sync_message_with_errors_dry_run(test_config):
    """Test sync message formatting with errors in dry run mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=["Error 1"],
        dry_run=True,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Errors: 1 (DRY RUN)" in message
    assert "**Errors** (1):" in message
    assert "Error 1" in message
    assert "Sync Status: ⚠️ Dry run completed with errors" in message
    # Check that status is first line
    assert message.startswith("Sync Status: ⚠️ Dry run completed with errors")


def test_format_sync_message_many_errors(test_config):
    """Test sync message formatting with many errors (no truncation)"""
    notifier = TelegramNotifier(test_config)

    errors = [f"Error {i}" for i in range(1, 11)]  # 10 errors
    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=errors,
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Errors** (10):" in message
    assert "Error 1" in message
    assert "Error 2" in message
    assert "Error 3" in message
    assert "Error 10" in message  # All errors should be shown
    # Check that status is first line
    assert message.startswith("Sync Status: ⚠️ Synchronization completed with errors")


def test_format_sync_message_with_updated_titles_normal(test_config):
    """Test sync message formatting with updated titles in normal mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[
            SyncAction(
                action="update_title",
                channel_title="New Channel Name",
                feed_url="http://localhost:1200/telegram/channel/test",
                category_name="News",
                old_title="Old Channel Name",
            )
        ],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Updated: 1" in message
    assert "**Updated titles** (1):" in message
    assert "Old Channel Name → New Channel Name" in message
    assert "Sync Status: Synchronization completed successfully" in message
    # Check that status is first line
    assert message.startswith("Sync Status: Synchronization completed successfully")


def test_format_sync_message_with_updated_titles_dry_run(test_config):
    """Test sync message formatting with updated titles in dry run mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[
            SyncAction(
                action="update_title",
                channel_title="New Channel Name",
                feed_url="http://localhost:1200/telegram/channel/test",
                category_name="News",
                old_title="Old Channel Name",
            )
        ],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Updated: 1 (DRY RUN)" in message
    assert "**Would update titles** (1):" in message
    assert "Old Channel Name → New Channel Name" in message
    assert "Sync Status: Dry run completed successfully" in message
    # Check that status is first line
    assert message.startswith("Sync Status: Dry run completed successfully")


def test_format_sync_message_many_updated_titles(test_config):
    """Test sync message formatting with many updated titles (no truncation)"""
    notifier = TelegramNotifier(test_config)

    updated_titles = []
    for i in range(1, 11):  # 10 updated titles
        updated_titles.append(
            SyncAction(
                action="update_title",
                channel_title=f"New Channel {i}",
                feed_url=f"http://localhost:1200/telegram/channel/test{i}",
                category_name="News",
                old_title=f"Old Channel {i}",
            )
        )

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=updated_titles,
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Updated titles** (10):" in message
    assert "Old Channel 1 → New Channel 1" in message
    assert "Old Channel 5 → New Channel 5" in message
    assert "Old Channel 10 → New Channel 10" in message  # All titles should be shown
    # Check that status is first line
    assert message.startswith("Sync Status: Synchronization completed successfully")


def test_format_sync_message_mixed_operations(test_config):
    """Test sync message formatting with mixed operations"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[
            SyncAction("add", "Added Channel", "http://example.com/add", "News")
        ],
        removed_feeds=[
            SyncAction("remove", "Removed Channel", "http://example.com/remove", "News")
        ],
        updated_titles=[
            SyncAction(
                action="update_title",
                channel_title="Updated Channel",
                feed_url="http://localhost:1200/telegram/channel/test",
                category_name="News",
                old_title="Old Title",
            )
        ],
        moved_feeds=[],
        errors=["Some error"],
        dry_run=False,
    )

    message = notifier._format_sync_message(result)

    # Check message content
    assert "**Summary**: Added: 1 | Removed: 1 | Updated: 1 | Errors: 1" in message
    assert "**Added feeds** (1):" in message
    assert "Added Channel" in message
    assert "**Removed feeds** (1):" in message
    assert "Removed Channel" in message
    assert "**Updated titles** (1):" in message
    assert "Old Title → Updated Channel" in message
    assert "**Errors** (1):" in message
    assert "Some error" in message
    assert "Sync Status: ⚠️ Synchronization completed with errors" in message
    # Check that status is first line
    assert message.startswith("Sync Status: ⚠️ Synchronization completed with errors")


@pytest.mark.asyncio
async def test_send_sync_notification_normal(test_config):
    """Test sending sync notification in normal mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was NOT sent (notify_no_changes is False by default)
        mock_tg_instance.send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_send_sync_notification_dry_run(test_config):
    """Test sending sync notification in dry run mode"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was NOT sent (notify_no_changes is False, even for dry run)
        mock_tg_instance.send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_send_sync_notification_no_changes_disabled(test_config):
    """Test that no notification is sent when notify_no_changes is False"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was NOT sent (notify_no_changes is False)
        mock_tg_instance.send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_send_sync_notification_no_changes_enabled(
    test_config_with_notifications,
):
    """Test that notification is sent when notify_no_changes is True"""
    notifier = TelegramNotifier(test_config_with_notifications)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was sent (notify_no_changes is True)
        mock_tg_instance.send_notification.assert_called_once()
        call_args = mock_tg_instance.send_notification.call_args[0][0]
        assert "Sync Status: No changes required" in call_args


@pytest.mark.asyncio
async def test_send_sync_notification_with_changes_always_sent(test_config):
    """Test that notification is always sent when there are changes, regardless of notify_no_changes"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[SyncAction("add", "Test Channel", "http://example.com", "News")],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=False,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was sent (there are changes)
        mock_tg_instance.send_notification.assert_called_once()
        call_args = mock_tg_instance.send_notification.call_args[0][0]
        assert "**Added feeds** (1):" in call_args


@pytest.mark.asyncio
async def test_send_sync_notification_with_errors_always_sent(test_config):
    """Test that notification is always sent when there are errors, regardless of notify_no_changes"""
    notifier = TelegramNotifier(test_config)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=["Test error"],
        dry_run=False,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was sent (there are errors)
        mock_tg_instance.send_notification.assert_called_once()
        call_args = mock_tg_instance.send_notification.call_args[0][0]
        assert "**Errors** (1):" in call_args


@pytest.mark.asyncio
async def test_send_sync_notification_dry_run_with_notifications(
    test_config_with_notifications,
):
    """Test sending sync notification in dry run mode when notify_no_changes is True"""
    notifier = TelegramNotifier(test_config_with_notifications)

    result = SyncResult(
        added_feeds=[],
        removed_feeds=[],
        updated_titles=[],
        moved_feeds=[],
        errors=[],
        dry_run=True,
    )

    with patch("teleflux.notifier.TelegramClient") as mock_tg_client:
        mock_tg_instance = AsyncMock()
        mock_tg_client.return_value.__aenter__.return_value = mock_tg_instance

        await notifier.send_sync_notification(result)

        # Check that message was sent (notify_no_changes is True)
        mock_tg_instance.send_notification.assert_called_once()
        call_args = mock_tg_instance.send_notification.call_args[0][0]
        assert "Sync Status: No changes would be made" in call_args
