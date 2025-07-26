"""Teleflux: Telegram to Miniflux synchronization tool.

This package provides functionality to synchronize Telegram channels organized in folders
with Miniflux RSS reader categories. It uses Telegram's folder structure to automatically
create and manage RSS feeds for channels via RSSHub integration.

Key features:
    - Two-way synchronization between Telegram folders and Miniflux categories
    - Support for both public and private channels
    - Automatic feed creation, update, and cleanup
    - Title synchronization with emoji handling options
    - Comprehensive error handling and logging
    - Dry-run mode for safe testing

Main components:
    - CLI: Command-line interface for running synchronization
    - Config: Configuration management and validation
    - Clients: Telegram and Miniflux API clients
    - Sync: Core synchronization logic
    - Notifier: Telegram notification system

Author:
    Nikita Petrov <petrov.nikita@gmail.com>

Version:
    1.0.0
"""

import warnings

# Suppress urllib3 OpenSSL warning on macOS/systems with LibreSSL
# This warning appears when urllib3 v2+ is used with LibreSSL instead of OpenSSL
# Common on macOS with Homebrew Python installations
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

__version__ = "1.0.0"
__author__ = "teleflux"
