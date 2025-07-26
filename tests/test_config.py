"""
Configuration module tests
"""

import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import yaml

from teleflux.config import Config, load_config


def test_load_valid_config():
    """Test loading valid configuration"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"News": "News", "Tech": "Tech"},
            "remove_absent_feeds": True,
            "private_feed_mode": "secret",
        },
        "logging": {"level": "INFO"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)

        assert isinstance(config, Config)
        assert config.telegram.api_id == 12345  # api_id is converted to int
        assert config.telegram.api_hash == "test_hash"
        assert config.telegram.notify_chat_id == "me"
        assert config.miniflux.url == "http://localhost:8080"
        assert config.miniflux.token == "test_token"
        assert config.rsshub.base_url == "http://localhost:1200"
        assert config.sync.folders == {"News": "News", "Tech": "Tech"}
        assert config.sync.remove_absent_feeds is True
        assert config.sync.private_feed_mode == "secret"
        assert config.logging.level == "INFO"

    finally:
        Path(config_path).unlink()


def test_load_config_with_numeric_chat_id():
    """Test loading configuration with numeric chat_id"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": 123456789,
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"Test": "Test"},
            "remove_absent_feeds": False,
            "private_feed_mode": "skip",
        },
        "logging": {"level": "DEBUG"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)
        assert config.telegram.notify_chat_id == 123456789

    finally:
        Path(config_path).unlink()


def test_load_config_missing_file():
    """Test loading non-existent file"""
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yml")


def test_load_config_missing_section():
    """Test loading configuration with missing section"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        }
        # Missing other required sections
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required section"):
            load_config(config_path)

    finally:
        Path(config_path).unlink()


def test_load_config_invalid_private_feed_mode():
    """Test loading configuration with invalid private_feed_mode"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"Test": "Test"},
            "remove_absent_feeds": True,
            "private_feed_mode": "invalid_mode",  # Invalid value
        },
        "logging": {"level": "INFO"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="private_feed_mode must be"):
            load_config(config_path)

    finally:
        Path(config_path).unlink()


def test_load_config_invalid_logging_level():
    """Test loading configuration with invalid logging level"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"Test": "Test"},
            "remove_absent_feeds": True,
            "private_feed_mode": "secret",
        },
        "logging": {"level": "INVALID_LEVEL"},  # Invalid value
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="logging.level must be"):
            load_config(config_path)

    finally:
        Path(config_path).unlink()


def test_load_config_with_folders_list():
    """Test loading configuration with folders as list"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": ["AI", "Technology", "Science"],  # List format
            "remove_absent_feeds": True,
            "private_feed_mode": "secret",
        },
        "logging": {"level": "INFO"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)

        # Should convert list to dict with same key-value pairs
        expected_folders = {
            "AI": "AI",
            "Technology": "Technology",
            "Science": "Science",
        }
        assert config.sync.folders == expected_folders

    finally:
        Path(config_path).unlink()


def test_load_config_with_folders_dict():
    """Test loading configuration with folders as dict (existing format)"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {
                "AI": "Artificial Intelligence",
                "Tech": "Technology",
            },  # Dict format
            "remove_absent_feeds": True,
            "private_feed_mode": "secret",
        },
        "logging": {"level": "INFO"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)

        # Should keep dict as is
        expected_folders = {"AI": "Artificial Intelligence", "Tech": "Technology"}
        assert config.sync.folders == expected_folders

    finally:
        Path(config_path).unlink()


def test_load_config_invalid_folders_format():
    """Test loading configuration with invalid folders format"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": "invalid_format",  # Invalid format (string)
            "remove_absent_feeds": True,
            "private_feed_mode": "secret",
        },
        "logging": {"level": "INFO"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(
            ValueError, match="sync.folders must be a dictionary or a list"
        ):
            load_config(config_path)

    finally:
        Path(config_path).unlink()


def test_load_config_mixed_folders_format_error(tmp_path):
    """Test loading config with mixed folders format (should fail)"""
    config_content = """
telegram:
  api_id: "123456"
  api_hash: "abcdef"
  session_file: "test.session"
  notify_chat_id: "me"

miniflux:
  url: "http://localhost:8080"
  token: "test_token"

rsshub:
  base_url: "http://localhost:1200"

sync:
  folders: {"AI": "AI", "Tech": "Technology", - "News"}  # Mixed format - invalid
  remove_absent_feeds: true
  private_feed_mode: "skip"

logging:
  level: "INFO"
"""

    config_file = tmp_path / "config.yml"
    config_file.write_text(config_content)

    with pytest.raises(ValueError, match="YAML parsing error"):
        load_config(config_file)


def test_load_config_with_keep_emojis_option(tmp_path):
    """Test loading config with keep_emojis_in_titles option"""
    config_content = """
telegram:
  api_id: "123456"
  api_hash: "abcdef"
  session_file: "test.session"
  notify_chat_id: "me"

miniflux:
  url: "http://localhost:8080"
  token: "test_token"

rsshub:
  base_url: "http://localhost:1200"

sync:
  folders:
    - "AI"
    - "Tech"
  remove_absent_feeds: true
  private_feed_mode: "skip"
  keep_emojis_in_titles: true

logging:
  level: "INFO"
"""

    config_file = tmp_path / "config.yml"
    config_file.write_text(config_content)

    config = load_config(config_file)

    assert config.sync.keep_emojis_in_titles is True


def test_load_config_keep_emojis_default_false(tmp_path):
    """Test that keep_emojis_in_titles defaults to False when not specified"""
    config_content = """
telegram:
  api_id: "123456"
  api_hash: "abcdef"
  session_file: "test.session"
  notify_chat_id: "me"

miniflux:
  url: "http://localhost:8080"
  token: "test_token"

rsshub:
  base_url: "http://localhost:1200"

sync:
  folders:
    - "AI"
    - "Tech"
  remove_absent_feeds: true
  private_feed_mode: "skip"

logging:
  level: "INFO"
"""

    config_file = tmp_path / "config.yml"
    config_file.write_text(config_content)

    config = load_config(config_file)

    assert config.sync.keep_emojis_in_titles is False


def test_load_config_with_disable_title_updates():
    """Test loading configuration with disable_title_updates parameter"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"Test": "Test"},
            "remove_absent_feeds": False,
            "private_feed_mode": "skip",
            "disable_title_updates": True,  # Test the new parameter
        },
        "logging": {"level": "DEBUG"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)
        assert config.sync.disable_title_updates is True

    finally:
        Path(config_path).unlink()


def test_load_config_disable_title_updates_defaults_to_false():
    """Test that disable_title_updates defaults to False when not specified"""
    config_data = {
        "telegram": {
            "api_id": "12345",
            "api_hash": "test_hash",
            "session_file": "test.session",
            "notify_chat_id": "me",
        },
        "miniflux": {"url": "http://localhost:8080", "token": "test_token"},
        "rsshub": {"base_url": "http://localhost:1200"},
        "sync": {
            "folders": {"Test": "Test"},
            "remove_absent_feeds": True,
            "private_feed_mode": "skip",
            # disable_title_updates not specified
        },
        "logging": {"level": "INFO"},
    }

    with patch("builtins.open", mock_open(read_data=yaml.dump(config_data))):
        with patch("pathlib.Path.exists", return_value=True):
            config = load_config("test.yml")

            # Should default to False
            assert config.sync.disable_title_updates is False


def test_setup_logging_normal_mode():
    """Test setup_logging in normal mode"""
    import logging

    from teleflux.config import LoggingConfig, setup_logging

    config = LoggingConfig(level="INFO")

    # Clear any existing handlers
    logging.getLogger().handlers.clear()

    setup_logging(config, quiet=False)

    # Check that logging level is set to INFO
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_quiet_mode():
    """Test setup_logging in quiet mode"""
    import logging

    from teleflux.config import LoggingConfig, setup_logging

    config = LoggingConfig(level="INFO")

    # Clear any existing handlers
    logging.getLogger().handlers.clear()

    setup_logging(config, quiet=True)

    # Check that logging level is set to ERROR in quiet mode
    assert logging.getLogger().level == logging.ERROR


def test_setup_logging_quiet_mode_overrides_config():
    """Test that quiet mode overrides configured logging level"""
    import logging

    from teleflux.config import LoggingConfig, setup_logging

    # Even with DEBUG level configured, quiet mode should set ERROR level
    config = LoggingConfig(level="DEBUG")

    # Clear any existing handlers
    logging.getLogger().handlers.clear()

    setup_logging(config, quiet=True)

    # Check that logging level is set to ERROR, not DEBUG
    assert logging.getLogger().level == logging.ERROR


def test_setup_logging_default_quiet_false():
    """Test that setup_logging defaults to quiet=False"""
    import logging

    from teleflux.config import LoggingConfig, setup_logging

    config = LoggingConfig(level="WARNING")

    # Clear any existing handlers
    logging.getLogger().handlers.clear()

    # Call without quiet parameter (should default to False)
    setup_logging(config)

    # Check that logging level is set to WARNING (not ERROR)
    assert logging.getLogger().level == logging.WARNING
