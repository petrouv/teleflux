"""Entry point for running Teleflux as a module.

This module allows Teleflux to be executed using `python -m teleflux` command.
It handles early warning suppression before importing other modules to prevent
urllib3 OpenSSL warnings on systems with LibreSSL.

Usage:
    python -m teleflux [options]

Examples:
    python -m teleflux -c config.yml
    python -m teleflux --dry-run
    python -m teleflux --list-folders
"""

import warnings

# Suppress urllib3 OpenSSL warning before any other imports that might trigger it
# This must be done early to catch warnings from dependency imports
warnings.filterwarnings(
    "ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+", category=UserWarning
)

from .cli import main

if __name__ == "__main__":
    main()
