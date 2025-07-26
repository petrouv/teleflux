"""Command-line interface for Teleflux.

This module provides the main CLI entry point and command-line argument handling
for the Teleflux synchronization tool. It supports multiple operations including
synchronization, folder listing, and dry-run mode.

The CLI provides comprehensive error handling with meaningful exit codes and
supports both interactive and automated (quiet) operation modes for integration
with cron jobs and system services.

Exit codes:
    0: Success (including successful sync with external service errors)
    2: Configuration file not found
    3: Configuration validation error
    4: Critical application error (bug in code)
    5: External service error (Telegram/Miniflux unavailable)
    130: Interrupted by user (Ctrl+C)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config, setup_logging
from .notifier import TelegramNotifier
from .sync import TelefluxSyncer
from .telegram_client import TelegramClient

logger = logging.getLogger(__name__)


async def list_folders_async(
    config_path: str, quiet: bool = False, session_file: str = None
) -> int:
    """List all available Telegram folders with channel counts.

    Connects to Telegram API and retrieves information about all folders
    (dialog filters) and their associated channels. Displays current
    configuration mapping and validates folder existence.

    Args:
        config_path: Path to configuration file
        quiet: If True, suppress non-error output for automated scripts
        session_file: Custom path to session file (overrides config)

    Returns:
        Exit code (0=success, 2=config not found, 3=config error,
        4=critical error, 5=external service error)
    """
    try:
        # Load configuration
        config = load_config(config_path)

        # Override session file if provided via CLI
        if session_file:
            config.telegram.session_file = session_file
            # Ensure session file directory exists
            session_path = Path(session_file)
            session_path.parent.mkdir(parents=True, exist_ok=True)

        # Setup logging with user's configured level (or quiet mode)
        # Pass quiet only if explicitly set via CLI, otherwise use config setting
        setup_logging(config.logging, quiet=quiet if quiet else None)

        logger.info("Listing Telegram folders")
        logger.info(f"Configuration loaded from: {config_path}")

        # Connect to Telegram and get folders
        try:
            async with TelegramClient(config.telegram) as tg_client:
                folders = await tg_client.get_all_folders()
        except Exception as e:
            # Telegram API errors are external service errors, not critical app errors
            if not quiet:
                print(f"External service error: {e}", file=sys.stderr)
            logger.error(f"Failed to connect to Telegram: {e}")
            return 5

        # Display folders (suppress in quiet mode)
        if not quiet:
            print("\nAvailable Telegram folders:")
            print("=" * 40)

            total_channels = 0
            for folder in folders:
                total_channels += folder.channel_count
                if folder.name == "Main":
                    print(f"* {folder.name:<20} {folder.channel_count:>3} channels")
                else:
                    print(f"  {folder.name:<20} {folder.channel_count:>3} channels")

            print("=" * 40)
            print(f"Total: {len(folders)} folders, {total_channels} channels")

            # Show current configuration mapping and validate folder existence
            print("\nCurrent configuration mapping:")
            folder_names = [f.name for f in folders]
            invalid_folders = []

            for tg_folder, miniflux_category in config.sync.folders.items():
                folder_exists = tg_folder in folder_names
                status = "[OK]" if folder_exists else "[NOT FOUND]"
                print(f"{status} {tg_folder} -> {miniflux_category}")
                if not folder_exists:
                    invalid_folders.append(tg_folder)

            if invalid_folders:
                print(
                    "\nWarning: Some configured folders don't exist in your Telegram account!"
                )

        return 0

    except FileNotFoundError as e:
        if not quiet:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        if not quiet:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        # This should only catch critical application errors (bugs in our code)
        # External service errors are handled separately with code 5
        if not quiet:
            print(f"Critical error: {e}", file=sys.stderr)
        logger.exception("Critical error")
        return 4


async def list_unfoldered_channels_async(
    config_path: str, quiet: bool = False, session_file: str = None
) -> int:
    """List all Telegram channels that are not in any folder.

    Retrieves and displays channels that are in the default "Main" folder
    and not organized into any custom folders. Useful for identifying
    channels that need organization.

    Args:
        config_path: Path to configuration file
        quiet: If True, suppress non-error output for automated scripts
        session_file: Custom path to session file (overrides config)

    Returns:
        Exit code (0=success, 2=config not found, 3=config error,
        4=critical error, 5=external service error)
    """
    try:
        # Load configuration
        config = load_config(config_path)

        # Override session file if provided via CLI
        if session_file:
            config.telegram.session_file = session_file
            # Ensure session file directory exists
            session_path = Path(session_file)
            session_path.parent.mkdir(parents=True, exist_ok=True)

        # Setup logging with user's configured level (or quiet mode)
        # Pass quiet only if explicitly set via CLI, otherwise use config setting
        setup_logging(config.logging, quiet=quiet if quiet else None)

        logger.info("Listing Telegram channels not in any folder")
        logger.info(f"Configuration loaded from: {config_path}")

        # Connect to Telegram and get unfoldered channels
        try:
            async with TelegramClient(config.telegram) as tg_client:
                channels = await tg_client.get_unfoldered_channels()
        except Exception as e:
            # Telegram API errors are external service errors, not critical app errors
            if not quiet:
                print(f"External service error: {e}", file=sys.stderr)
            logger.error(f"Failed to connect to Telegram: {e}")
            return 5

        # Display channels (suppress in quiet mode)
        if not quiet:
            print("\nTelegram channels not in any folder:")
            print("=" * 60)

            if not channels:
                print("No channels found outside of folders.")
                print("All your channels are organized in folders!")
            else:
                for i, channel in enumerate(channels, 1):
                    if channel.is_private:
                        # Private channel - show title and hash
                        print(f"{i:3d}. {channel.title}")
                        print(f"     Private channel (ID: {channel.id})")
                        if channel.channel_hash:
                            print(f"     Hash: {channel.channel_hash}")
                    else:
                        # Public channel - show title and username
                        print(f"{i:3d}. {channel.title}")
                        print(f"     @{channel.username} (ID: {channel.id})")
                    print()

            print("=" * 60)
            print(f"Total: {len(channels)} channels not in any folder")

            if channels:
                print("\nThese channels are currently in the 'Main' folder.")
                print(
                    "Consider organizing them into custom folders for better management."
                )

        return 0

    except FileNotFoundError as e:
        if not quiet:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        if not quiet:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        # This should only catch critical application errors (bugs in our code)
        # External service errors are handled separately with code 5
        if not quiet:
            print(f"Critical error: {e}", file=sys.stderr)
        logger.exception("Critical error")
        return 4


async def main_async(
    config_path: str,
    dry_run: bool = False,
    quiet: bool = False,
    session_file: str = None,
) -> int:
    """Main asynchronous application function for synchronization.

    Orchestrates the complete synchronization process including configuration
    loading, client initialization, synchronization execution, and notification
    sending. Handles both normal and dry-run modes.

    Args:
        config_path: Path to configuration file
        dry_run: If True, only show what would be done without making changes
        quiet: If True, suppress non-error output for automated scripts
        session_file: Custom path to session file (overrides config)

    Returns:
        Exit code (0=success, 2=config not found, 3=config error,
        4=critical error, 5=external service error)
    """
    try:
        # Load configuration
        config = load_config(config_path)

        # Override session file if provided via CLI
        if session_file:
            config.telegram.session_file = session_file
            # Ensure session file directory exists
            session_path = Path(session_file)
            session_path.parent.mkdir(parents=True, exist_ok=True)

        # Setup logging
        # Pass quiet only if explicitly set via CLI, otherwise use config setting
        setup_logging(config.logging, quiet=quiet if quiet else None)

        if dry_run:
            logger.info("Starting teleflux in DRY RUN mode")
            logger.info("No actual changes will be made")
        else:
            logger.info("Starting teleflux")

        logger.info(f"Configuration loaded from: {config_path}")

        # Create synchronizer and perform synchronization
        syncer = TelefluxSyncer(config, quiet=quiet)

        try:
            result = await syncer.sync_folders(dry_run=dry_run)
        except Exception as e:
            # If synchronizer itself crashes (not external service errors),
            # this is a critical application error
            logger.error(f"Critical synchronization failure: {e}")
            logger.exception("Full traceback")
            if not quiet:
                print(f"Critical error: {e}", file=sys.stderr)
            return 4

        # Send notification (only in non-dry-run mode and if enabled)
        if not dry_run and config.notifications.enabled:
            try:
                notifier = TelegramNotifier(config)
                await notifier.send_sync_notification(result)
            except Exception as e:
                # Notification errors are not critical - log but don't affect exit code
                logger.error(f"Failed to send notification: {e}")
                # Add to result errors for completeness but don't change exit code
        elif not dry_run:
            logger.info("Notifications are disabled in configuration")
        else:
            logger.info("Skipping notification in dry run mode")

        # Determine exit code
        # Even if there were synchronization errors, the process itself finished successfully.
        # Log the issues, but exit with 0 so that orchestrators like Docker treat the run as successful.
        if result.errors:
            logger.warning(
                f"Synchronization completed with errors: {len(result.errors)}"
            )

        if dry_run:
            logger.info("Dry run completed successfully")
        else:
            logger.info("Synchronization completed successfully")

        return 0

    except FileNotFoundError as e:
        if not quiet:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        if not quiet:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        # This should only catch critical application errors (bugs in our code)
        # Configuration and connection issues are handled above
        if not quiet:
            print(f"Critical error: {e}", file=sys.stderr)
        logger.exception("Critical error")
        return 4


def main() -> None:
    """CLI application entry point.

    Parses command-line arguments, validates configuration file existence,
    and dispatches to appropriate async functions based on requested operation.
    Handles keyboard interrupts gracefully and provides comprehensive help.
    """
    parser = argparse.ArgumentParser(
        description="Synchronize Telegram channels with Miniflux categories via RssHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python -m teleflux
  python -m teleflux -c ~/teleflux.yml
  python -m teleflux -s ~/my-session.session
  python -m teleflux -c ~/teleflux.yml -d
  python -m teleflux -c ~/teleflux.yml -l
  python -m teleflux -c ~/teleflux.yml -u
  python -m teleflux -c ~/teleflux.yml -q
  teleflux -c /etc/teleflux/config.yml --dry-run
  teleflux -c /etc/teleflux/config.yml -q  # For cron jobs

Exit codes:
  0 - Success (including successful sync with external service errors)
  2 - Configuration file not found
  3 - Configuration validation error
  4 - Critical application error (bug in code)
  5 - External service error (Telegram/Miniflux unavailable)
  130 - Interrupted by user (Ctrl+C)

Note: Title updates are enabled by default. To disable them, add 'disable_title_updates: true'
      to your config file under the 'sync' section.

      Use --quiet for automated runs (cron, systemd timers) to suppress non-error output.

      For Docker and orchestration tools: Exit code 0 means the application ran successfully,
      even if there were errors communicating with external services (Telegram/Miniflux).
      Check logs for details on external service errors.
        """,
    )

    # Get the directory where the script is located for default config path
    script_dir = Path(__file__).parent.parent
    default_config_path = script_dir / "config" / "config.yml"

    parser.add_argument(
        "-c",
        "--config",
        default=str(default_config_path),
        help=f"Path to YAML configuration file (default: {default_config_path})",
    )

    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )

    parser.add_argument(
        "-l",
        "--list-folders",
        action="store_true",
        help="List all available Telegram folders",
    )

    parser.add_argument(
        "-u",
        "--list-unfoldered-channels",
        action="store_true",
        help="List all Telegram channels that are not in any folder",
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress non-error output"
    )

    parser.add_argument(
        "-s",
        "--session-file",
        help="Custom path to Telegram session file (overrides config, default: data/teleflux.session)",
    )

    parser.add_argument(
        "-v", "--version", action="version", version=f"teleflux {__version__}"
    )

    args = parser.parse_args()

    # Check configuration file existence
    config_path = Path(args.config)
    if not config_path.exists():
        if not args.quiet:
            print(
                f"Error: Configuration file not found: {config_path}", file=sys.stderr
            )
            if args.config == str(default_config_path):
                print(
                    f"Hint: Create a config.yml file in {script_dir}/config/ or specify a custom path with --config",
                    file=sys.stderr,
                )
        sys.exit(2)

    # Run appropriate function(s) based on command-line arguments
    try:
        exit_code = 0

        # If list-unfoldered-channels is requested, run it and exit
        if args.list_unfoldered_channels:
            exit_code = asyncio.run(
                list_unfoldered_channels_async(
                    str(config_path), quiet=args.quiet, session_file=args.session_file
                )
            )
            sys.exit(exit_code)
            return  # Ensure function exits even if sys.exit is mocked

        # If list-folders is requested, run it first
        if args.list_folders:
            exit_code = asyncio.run(
                list_folders_async(
                    str(config_path), quiet=args.quiet, session_file=args.session_file
                )
            )

            # Always exit after listing folders, regardless of other flags
            sys.exit(exit_code)
            return  # Ensure function exits even if sys.exit is mocked

        # Run sync (either normal or dry-run)
        exit_code = asyncio.run(
            main_async(
                str(config_path),
                dry_run=args.dry_run,
                quiet=args.quiet,
                session_file=args.session_file,
            )
        )

        sys.exit(exit_code)
    except KeyboardInterrupt:
        if not args.quiet:
            print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
