"""Configuration loading and validation module.

This module handles loading, parsing, and validating configuration from YAML files.
It provides dataclasses for different configuration sections and comprehensive
validation with helpful error messages.

The configuration supports both dictionary and list formats for folder mappings,
authentication via username/password or API tokens for Miniflux, and extensive
customization options for synchronization behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class TelegramConfig:
    """Telegram API configuration.

    Attributes:
        api_id: Telegram API ID obtained from https://my.telegram.org
        api_hash: Telegram API hash obtained from https://my.telegram.org
        session_file: Path to Telegram session file for authentication persistence
        notify_chat_id: Chat ID for sending notifications ("me" for saved messages, "@username" for bots, or numeric ID)
    """

    api_id: int
    api_hash: str
    session_file: str
    notify_chat_id: str | int


@dataclass
class MinifluxConfig:
    """Miniflux API configuration.

    Supports authentication via either username/password or API token.
    API token is preferred for security and performance.

    Attributes:
        url: Miniflux server URL (without trailing slash)
        username: Username for basic authentication (optional if using token)
        password: Password for basic authentication (optional if using token)
        token: API token for authentication (preferred method)
    """

    url: str
    username: str = None
    password: str = None
    token: str = None


@dataclass
class RssHubConfig:
    """RSSHub configuration.

    RSSHub is used to generate RSS feeds for Telegram channels.

    Attributes:
        base_url: RSSHub server URL (without trailing slash)
    """

    base_url: str


@dataclass
class SyncConfig:
    """Synchronization configuration.

    Controls how channels are mapped to categories and how synchronization behaves.

    Attributes:
        folders: Mapping of Telegram folder names to Miniflux category names
        remove_absent_feeds: Whether to remove feeds not present in Telegram folders
        private_feed_mode: How to handle private channels ("secret" or "skip")
        validate_feeds: Whether to validate feed URLs before creating feeds
        notify_no_changes: Whether to send notifications when no changes are made
        keep_emojis_in_titles: Whether to preserve emojis in feed titles
        disable_title_updates: Whether to disable automatic title updates
    """

    folders: dict[str, str]
    remove_absent_feeds: bool = True
    private_feed_mode: str = "skip"
    validate_feeds: bool = True
    notify_no_changes: bool = False
    keep_emojis_in_titles: bool = False
    disable_title_updates: bool = False


@dataclass
class LoggingConfig:
    """Logging configuration.

    Attributes:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        file: Log file path (optional, logs to console if not specified)
        quiet: If True, only show ERROR and CRITICAL messages for automated runs
    """

    level: str = "INFO"
    file: str = None
    quiet: bool = False


@dataclass
class NotificationsConfig:
    """Notifications configuration.

    Attributes:
        enabled: Whether to send Telegram notifications after synchronization
        chat_id: Chat ID to send notifications to (defaults to "me")
    """

    enabled: bool = True
    chat_id: str = "me"


@dataclass
class Config:
    """Main application configuration.

    Contains all configuration sections required for Teleflux operation.

    Attributes:
        telegram: Telegram API configuration
        miniflux: Miniflux API configuration
        rsshub: RSSHub configuration
        sync: Synchronization configuration
        logging: Logging configuration
        notifications: Notifications configuration
    """

    telegram: TelegramConfig
    miniflux: MinifluxConfig
    rsshub: RssHubConfig
    sync: SyncConfig
    logging: LoggingConfig = None
    notifications: NotificationsConfig = None


def load_config(config_path: str | Path) -> Config:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Validated configuration object

    Raises:
        FileNotFoundError: If configuration file is not found
        ValueError: If configuration is invalid or has parsing errors
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        error_str = str(e)
        # Check if this looks like a mixed folder format error and provide helpful message
        if "could not find expected ':'" in error_str:
            try:
                with open(config_path, encoding="utf-8") as f:
                    content = f.read()
                if "folders:" in content:
                    raise ValueError(
                        f"YAML parsing error in configuration file: {config_path}\n"
                        f"It looks like you might be mixing dictionary and list formats in the 'folders' section.\n"
                        f"Please use either:\n"
                        f'  Dictionary format: folders: {{"AI": "AI", "Tech": "Technology"}}\n'
                        f'  List format: folders: ["AI", "Tech"]\n'
                        f"Original error: {e}"
                    )
            except ValueError:
                # Re-raise our custom ValueError
                raise
            except:
                # Ignore other exceptions when reading file
                pass
        # If we get here, it's not a mixed format error
        raise ValueError(f"YAML parsing error in {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Error reading configuration file {config_path}: {e}")

    # Validate required sections
    required_sections = ["telegram", "miniflux", "rsshub", "sync", "logging"]
    for section in required_sections:
        if section not in data:
            raise ValueError(f"Missing required section: {section}")

    # Validate Telegram configuration
    tg_config = data["telegram"]
    required_tg_fields = ["api_id", "api_hash", "notify_chat_id"]
    for field in required_tg_fields:
        if field not in tg_config:
            raise ValueError(f"Missing required field telegram.{field}")

    # Handle session_file with default value and ensure directory exists
    session_file = tg_config.get("session_file", "data/teleflux.session")
    session_path = Path(session_file)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    # Validate Miniflux configuration
    mf_config = data["miniflux"]
    required_mf_fields = ["url"]
    for field in required_mf_fields:
        if field not in mf_config:
            raise ValueError(f"Missing required field miniflux.{field}")

    # Validate RssHub configuration
    rh_config = data["rsshub"]
    if "base_url" not in rh_config:
        raise ValueError("Missing required field rsshub.base_url")

    # Validate Sync configuration
    sync_config = data["sync"]
    required_sync_fields = ["folders", "remove_absent_feeds", "private_feed_mode"]
    for field in required_sync_fields:
        if field not in sync_config:
            raise ValueError(f"Missing required field sync.{field}")

    # Process folders configuration - support both dict and list formats
    folders_config = sync_config["folders"]
    if isinstance(folders_config, dict):
        # Current format: {"AI": "AI", "Tech": "Technology"}
        folders = dict(folders_config)
    elif isinstance(folders_config, list):
        # New format: ["AI", "Tech"] - folder name same as category name
        folders = {folder: folder for folder in folders_config}
    else:
        raise ValueError("sync.folders must be a dictionary or a list")

    # Validate private feed mode
    if sync_config["private_feed_mode"] not in ["secret", "skip"]:
        raise ValueError("sync.private_feed_mode must be 'secret' or 'skip'")

    # Validate Logging configuration
    log_config = data["logging"]
    if "level" not in log_config:
        raise ValueError("Missing required field logging.level")

    if log_config["level"] not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        raise ValueError("logging.level must be one of: DEBUG, INFO, WARNING, ERROR")

    # Convert notify_chat_id to proper type (string "me"/"@username" or integer chat ID)
    notify_chat_id = tg_config["notify_chat_id"]
    if notify_chat_id == "me":
        # "me" is always valid
        pass
    elif isinstance(notify_chat_id, str) and notify_chat_id.startswith("@") and len(notify_chat_id) > 1:
        # @username format is valid (must have at least one character after @)
        notify_chat_id = str(notify_chat_id)
    else:
        # Try to convert to integer (numeric chat ID)
        try:
            notify_chat_id = int(notify_chat_id)
        except (ValueError, TypeError):
            raise ValueError("telegram.notify_chat_id must be 'me', '@username', or a number")

    # Create configuration objects with validated data
    return Config(
        telegram=TelegramConfig(
            api_id=int(tg_config["api_id"]),
            api_hash=str(tg_config["api_hash"]),
            session_file=str(session_file),
            notify_chat_id=notify_chat_id,
        ),
        miniflux=MinifluxConfig(
            url=str(mf_config["url"]).rstrip("/"),  # Remove trailing slash
            username=str(mf_config.get("username")),
            password=str(mf_config.get("password")),
            token=str(mf_config.get("token")),
        ),
        rsshub=RssHubConfig(
            base_url=str(rh_config["base_url"]).rstrip("/")
        ),  # Remove trailing slash
        sync=SyncConfig(
            folders=folders,
            remove_absent_feeds=bool(sync_config["remove_absent_feeds"]),
            private_feed_mode=str(sync_config["private_feed_mode"]),
            validate_feeds=bool(sync_config.get("validate_feeds", True)),
            notify_no_changes=bool(sync_config.get("notify_no_changes", False)),
            keep_emojis_in_titles=bool(sync_config.get("keep_emojis_in_titles", False)),
            disable_title_updates=bool(sync_config.get("disable_title_updates", False)),
        ),
        logging=LoggingConfig(
            level=str(log_config["level"]),
            file=str(log_config.get("file")),
            quiet=bool(log_config.get("quiet", False)),
        ),
        notifications=NotificationsConfig(
            enabled=bool(data.get("notifications", {}).get("enabled", True)),
            chat_id=str(data.get("notifications", {}).get("chat_id", "me")),
        ),
    )


def setup_logging(config: LoggingConfig, quiet: bool = None) -> None:
    """Set up logging according to configuration.

    Configures logging level, format, and output destination. In quiet mode,
    only ERROR and CRITICAL messages are shown for use in automated scripts.

    Args:
        config: Logging configuration
        quiet: If True, only show ERROR and CRITICAL messages for cron/automated runs.
               If None, uses the quiet setting from config.
    """
    # Use CLI quiet argument if provided, otherwise use config setting
    is_quiet = quiet if quiet is not None else config.quiet

    if is_quiet:
        # In quiet mode, only show ERROR and CRITICAL messages
        level = logging.ERROR
    else:
        # Use configured level
        level = getattr(logging, config.level.upper())

    # Configure basic logging with timestamp and structured format
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress verbose Pyrogram logs - only show WARNING and above
    # Pyrogram can be very chatty with connection details and session info
    pyrogram_loggers = [
        "pyrogram",
        "pyrogram.dispatcher",
        "pyrogram.session.session",
        "pyrogram.connection.connection",
        "pyrogram.session.auth",
        "pyrogram.crypto.aes",
        "pyrogram.session.internals.msg_id",
        "pyrogram.session.internals.seq_no",
    ]

    for logger_name in pyrogram_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
