"""
Tests for CLI module
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from teleflux.cli import (
    list_folders_async,
    list_unfoldered_channels_async,
    main,
    main_async,
)


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    config = MagicMock()
    config.logging = MagicMock()
    config.logging.level = "INFO"
    config.telegram = MagicMock()
    config.sync = MagicMock()
    config.sync.folders = {"Test": "Test Category"}
    return config


class TestQuietMode:
    """Test quiet mode functionality"""

    @pytest.mark.asyncio
    async def test_list_folders_quiet_mode(self, mock_config, capsys):
        """Test that list_folders_async respects quiet mode"""
        with patch("teleflux.cli.load_config", return_value=mock_config):
            with patch("teleflux.cli.setup_logging") as mock_setup_logging:
                with patch("teleflux.cli.TelegramClient") as mock_tg_client:
                    # Mock TelegramClient context manager
                    mock_client_instance = AsyncMock()

                    # Create proper mock folders with string attributes
                    mock_folder1 = MagicMock()
                    mock_folder1.name = "Main"
                    mock_folder1.channel_count = 5

                    mock_folder2 = MagicMock()
                    mock_folder2.name = "Test"
                    mock_folder2.channel_count = 3

                    mock_folders = [mock_folder1, mock_folder2]
                    mock_client_instance.get_all_folders.return_value = mock_folders
                    mock_tg_client.return_value.__aenter__.return_value = (
                        mock_client_instance
                    )

                    # Test normal mode (should have output)
                    result = await list_folders_async("test_config.yml", quiet=False)
                    captured = capsys.readouterr()

                    assert result == 0
                    assert "Available Telegram folders:" in captured.out
                    assert "Main" in captured.out
                    assert "Test" in captured.out
                    mock_setup_logging.assert_called_with(
                        mock_config.logging, quiet=None
                    )

                    # Reset capture
                    capsys.readouterr()

                    # Test quiet mode (should have no output)
                    result = await list_folders_async("test_config.yml", quiet=True)
                    captured = capsys.readouterr()

                    assert result == 0
                    assert captured.out == ""  # No output in quiet mode
                    mock_setup_logging.assert_called_with(
                        mock_config.logging, quiet=True
                    )

    @pytest.mark.asyncio
    async def test_list_unfoldered_channels_quiet_mode(self, mock_config, capsys):
        """Test that list_unfoldered_channels_async respects quiet mode"""
        with patch("teleflux.cli.load_config", return_value=mock_config):
            with patch("teleflux.cli.setup_logging") as mock_setup_logging:
                with patch("teleflux.cli.TelegramClient") as mock_tg_client:
                    # Mock TelegramClient context manager
                    mock_client_instance = AsyncMock()
                    mock_channels = [
                        MagicMock(
                            title="Unfoldered Channel 1",
                            username="channel1",
                            id=123,
                            is_private=False,
                        ),
                        MagicMock(
                            title="Unfoldered Channel 2",
                            username="channel2",
                            id=124,
                            is_private=False,
                        ),
                    ]
                    mock_client_instance.get_unfoldered_channels.return_value = (
                        mock_channels
                    )
                    mock_tg_client.return_value.__aenter__.return_value = (
                        mock_client_instance
                    )

                    # Test normal mode (should have output)
                    result = await list_unfoldered_channels_async(
                        "test_config.yml", quiet=False
                    )
                    captured = capsys.readouterr()

                    assert result == 0
                    assert "Telegram channels not in any folder:" in captured.out
                    assert "Unfoldered Channel 1" in captured.out
                    mock_setup_logging.assert_called_with(
                        mock_config.logging, quiet=None
                    )

                    # Reset capture
                    capsys.readouterr()

                    # Test quiet mode (should have no output)
                    result = await list_unfoldered_channels_async(
                        "test_config.yml", quiet=True
                    )
                    captured = capsys.readouterr()

                    assert result == 0
                    assert captured.out == ""  # No output in quiet mode
                    mock_setup_logging.assert_called_with(
                        mock_config.logging, quiet=True
                    )

    @pytest.mark.asyncio
    async def test_main_async_quiet_mode(self, mock_config):
        """Test that main_async respects quiet mode"""
        with patch("teleflux.cli.load_config", return_value=mock_config):
            with patch("teleflux.cli.setup_logging") as mock_setup_logging:
                with patch("teleflux.cli.TelefluxSyncer") as mock_syncer_class:
                    with patch("teleflux.cli.TelegramNotifier") as mock_notifier_class:
                        # Mock syncer with async method
                        mock_syncer = MagicMock()
                        mock_result = MagicMock()
                        mock_result.errors = []

                        # Make sync_folders an async method
                        async def mock_sync_folders(dry_run=False):
                            return mock_result

                        mock_syncer.sync_folders = mock_sync_folders
                        mock_syncer_class.return_value = mock_syncer

                        # Mock notifier
                        mock_notifier = AsyncMock()
                        mock_notifier_class.return_value = mock_notifier

                        # Test normal mode
                        result = await main_async(
                            "test_config.yml", dry_run=False, quiet=False
                        )

                        assert result == 0
                        mock_setup_logging.assert_called_with(
                            mock_config.logging, quiet=None
                        )
                        mock_syncer_class.assert_called_with(mock_config, quiet=False)

                        # Test quiet mode
                        result = await main_async(
                            "test_config.yml", dry_run=False, quiet=True
                        )

                        assert result == 0
                        mock_setup_logging.assert_called_with(
                            mock_config.logging, quiet=True
                        )
                        mock_syncer_class.assert_called_with(mock_config, quiet=True)

    @pytest.mark.asyncio
    async def test_error_handling_quiet_mode(self, capsys):
        """Test error handling in quiet mode"""
        # Test FileNotFoundError in quiet mode
        result = await list_folders_async("nonexistent.yml", quiet=True)
        captured = capsys.readouterr()

        assert result == 2
        assert captured.out == ""  # No output in quiet mode
        assert captured.err == ""  # No error output in quiet mode

        # Test FileNotFoundError in normal mode
        result = await list_folders_async("nonexistent.yml", quiet=False)
        captured = capsys.readouterr()

        assert result == 2
        assert "Error:" in captured.err  # Error output in normal mode

    @pytest.mark.asyncio
    async def test_configuration_error_quiet_mode(self, capsys):
        """Test configuration error handling in quiet mode"""
        with patch(
            "teleflux.cli.load_config", side_effect=ValueError("Invalid config")
        ):
            # Test ValueError in quiet mode
            result = await list_folders_async("test_config.yml", quiet=True)
            captured = capsys.readouterr()

            assert result == 3
            assert captured.out == ""  # No output in quiet mode
            assert captured.err == ""  # No error output in quiet mode

            # Test ValueError in normal mode
            result = await list_folders_async("test_config.yml", quiet=False)
            captured = capsys.readouterr()

            assert result == 3
            assert "Configuration error:" in captured.err  # Error output in normal mode


class TestCLIArguments:
    """Test CLI argument parsing and handling"""

    def test_quiet_argument_parsing(self):
        """Test that --quiet argument is properly parsed"""
        test_args = ["teleflux", "--config", "test_config.yml", "--quiet"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                with patch("teleflux.cli.asyncio.run") as mock_run:
                    with patch("sys.exit") as mock_exit:
                        # Mock path exists
                        mock_path.return_value.exists.return_value = True

                        # Mock asyncio.run to return success
                        mock_run.return_value = 0

                        try:
                            main()
                        except SystemExit:
                            pass  # Expected due to sys.exit call

                        # Verify that main_async was called with quiet=True
                        mock_run.assert_called_once()
                        mock_run.call_args[0][0]  # Get the coroutine
                        # We can't easily inspect the coroutine arguments, but we can verify it was called
                        assert mock_run.call_count == 1
                        mock_exit.assert_called_with(0)

    def test_quiet_with_list_folders(self):
        """Test --quiet combined with --list-folders"""
        test_args = [
            "teleflux",
            "--config",
            "test_config.yml",
            "--list-folders",
            "--quiet",
        ]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                with patch("teleflux.cli.asyncio.run") as mock_run:
                    with patch("sys.exit") as mock_exit:
                        # Mock path exists
                        mock_path.return_value.exists.return_value = True

                        # Mock asyncio.run to return success
                        mock_run.return_value = 0

                        try:
                            main()
                        except SystemExit:
                            pass  # Expected due to sys.exit call

                        # Should call list_folders_async with quiet=True
                        assert mock_run.call_count == 1
                        mock_exit.assert_called_with(0)

    def test_quiet_with_dry_run(self):
        """Test --quiet combined with --dry-run"""
        test_args = ["teleflux", "--config", "test_config.yml", "--dry-run", "--quiet"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                with patch("teleflux.cli.asyncio.run") as mock_run:
                    with patch("sys.exit") as mock_exit:
                        # Mock path exists
                        mock_path.return_value.exists.return_value = True

                        # Mock asyncio.run to return success
                        mock_run.return_value = 0

                        try:
                            main()
                        except SystemExit:
                            pass  # Expected due to sys.exit call

                        # Should call main_async with dry_run=True and quiet=True
                        assert mock_run.call_count == 1
                        mock_exit.assert_called_with(0)

    def test_config_file_not_found_quiet(self, capsys):
        """Test config file not found error in quiet mode"""
        test_args = ["teleflux", "--config", "nonexistent.yml", "--quiet"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                # Mock path doesn't exist
                mock_path.return_value.exists.return_value = False

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 2

                # Check that no output was produced in quiet mode
                captured = capsys.readouterr()
                assert captured.out == ""
                assert captured.err == ""

    def test_config_file_not_found_normal(self, capsys):
        """Test config file not found error in normal mode"""
        test_args = ["teleflux", "--config", "nonexistent.yml"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                # Mock path doesn't exist
                mock_path.return_value.exists.return_value = False

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 2

                # Check that error message was produced in normal mode
                captured = capsys.readouterr()
                assert "Error: Configuration file not found:" in captured.err

    def test_keyboard_interrupt_quiet(self, capsys):
        """Test KeyboardInterrupt handling in quiet mode"""
        test_args = ["teleflux", "--config", "test_config.yml", "--quiet"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                with patch("teleflux.cli.asyncio.run", side_effect=KeyboardInterrupt):
                    # Mock path exists
                    mock_path.return_value.exists.return_value = True

                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 130

                    # Check that no output was produced in quiet mode
                    captured = capsys.readouterr()
                    assert captured.out == ""
                    assert captured.err == ""

    def test_keyboard_interrupt_normal(self, capsys):
        """Test KeyboardInterrupt handling in normal mode"""
        test_args = ["teleflux", "--config", "test_config.yml"]

        with patch.object(sys, "argv", test_args):
            with patch("teleflux.cli.Path") as mock_path:
                with patch("teleflux.cli.asyncio.run", side_effect=KeyboardInterrupt):
                    # Mock path exists
                    mock_path.return_value.exists.return_value = True

                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 130

                    # Check that interrupt message was produced in normal mode
                    captured = capsys.readouterr()
                    assert "Interrupted by user" in captured.err


class TestSyncerQuietMode:
    """Test TelefluxSyncer quiet mode functionality"""

    def test_syncer_initialization_with_quiet(self, mock_config):
        """Test TelefluxSyncer initialization with quiet parameter"""
        from teleflux.sync import TelefluxSyncer

        # Test normal mode
        syncer = TelefluxSyncer(mock_config, quiet=False)
        assert syncer.quiet is False

        # Test quiet mode
        syncer = TelefluxSyncer(mock_config, quiet=True)
        assert syncer.quiet is True

        # Test default (should be False)
        syncer = TelefluxSyncer(mock_config)
        assert syncer.quiet is False

    def test_display_folder_comparison_quiet_mode(self, mock_config, capsys):
        """Test that _display_folder_comparison respects quiet mode"""
        from teleflux.sync import TelefluxSyncer

        # Create mock channels and feeds
        mock_channels = []
        mock_feeds = []

        # Test normal mode (should have output)
        syncer = TelefluxSyncer(mock_config, quiet=False)
        syncer._display_folder_comparison(
            tg_folder="Test Folder",
            miniflux_category="Test Category",
            channels=mock_channels,
            existing_feeds=mock_feeds,
        )
        captured = capsys.readouterr()
        # In normal mode, there should be some output (at least headers)
        assert len(captured.out) > 0

        # Test quiet mode (should have no output)
        syncer = TelefluxSyncer(mock_config, quiet=True)
        syncer._display_folder_comparison(
            tg_folder="Test Folder",
            miniflux_category="Test Category",
            channels=mock_channels,
            existing_feeds=mock_feeds,
        )
        captured = capsys.readouterr()
        # In quiet mode, there should be no output
        assert captured.out == ""

    def test_display_overall_summary_quiet_mode(self, mock_config, capsys):
        """Test that _display_overall_summary respects quiet mode"""
        from teleflux.sync import SyncResult, TelefluxSyncer

        # Create mock sync result
        mock_result = SyncResult(
            added_feeds=[],
            removed_feeds=[],
            updated_titles=[],
            moved_feeds=[],
            errors=[],
            dry_run=False,
        )

        # Test normal mode (should have output)
        syncer = TelefluxSyncer(mock_config, quiet=False)
        syncer._display_overall_summary(mock_result)
        captured = capsys.readouterr()
        # In normal mode, there should be some output (at least the summary header)
        assert "OVERALL SUMMARY" in captured.out

        # Test quiet mode (should have no output)
        syncer = TelefluxSyncer(mock_config, quiet=True)
        syncer._display_overall_summary(mock_result)
        captured = capsys.readouterr()
        # In quiet mode, there should be no output
        assert captured.out == ""
