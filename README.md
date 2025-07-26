# Teleflux

<p align="center">
  <img src="icon.png" alt="Teleflux Icon" width="128" height="128">
</p>

Synchronize your Telegram channels with Miniflux RSS reader through automated RSS feed creation.

Teleflux monitors your Telegram channel folders and automatically creates corresponding RSS feeds in Miniflux, keeping your RSS reader organized exactly like your Telegram folders.

## What Teleflux Does

- Automatically creates RSS feeds for all channels in your Telegram folders
- Maps each Telegram folder to a category in Miniflux
- Keeps feed titles updated with current channel names
- Removes feeds for channels you've unfollowed
- Sends you notifications about synchronization results

## Related Services

This project integrates with the following services:

- **[Miniflux](https://miniflux.app)** - A minimalist and opinionated RSS reader
- **[RSSHub](https://docs.rsshub.app)** - Everything is RSSible - generates RSS feeds for various platforms including Telegram
- **[Telegram](https://telegram.org)** - Cloud-based instant messaging service

## Requirements

Before installing Teleflux, you need:

1. **Python 3.9 or higher** - with updated pip/setuptools
2. **Miniflux RSS reader** - running somewhere accessible
3. **RSSHub instance** - for generating RSS feeds from Telegram channels
4. **Telegram API credentials** - obtained from Telegram

### Python Compatibility Note

Teleflux requires modern build tools for installation. If you're using Python 3.9, you'll need to upgrade pip and setuptools first, as the default versions don't support editable installs with `pyproject.toml`.

## Installation

### Step 1: Install Teleflux

Clone and install the application:

```bash
git clone https://github.com/petrouv/teleflux.git
cd teleflux
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# For Python 3.9 users: upgrade pip and setuptools first
pip install --upgrade pip setuptools wheel

# Install Teleflux
pip install -e .

# Alternative: if you encounter issues with editable install
# pip install .

# Create config directory
mkdir -p config
```

### Step 2: Get Telegram API Credentials

1. Go to https://my.telegram.org/apps
2. Log in with your Telegram account
3. Create a new application (any name works)
4. Copy the `api_id` (number) and `api_hash` (long string)
5. Save these values - you'll need them for configuration

### Step 3: Create Telegram Session

Before using Teleflux, you must create a Telegram session file:

```bash
# This will prompt you to enter your phone number and verification code
teleflux --dry-run
```

Follow the prompts:
- Enter your phone number (with country code, e.g., +1234567890)
- Enter the verification code sent to your Telegram app
- If you have two-factor authentication, enter your password

This creates a session file that allows Teleflux to access your Telegram account without asking for codes again.

## Configuration

Create a configuration file at `config/config.yml`:

```yaml
telegram:
  api_id: 12345678                    # Your API ID from my.telegram.org
  api_hash: "your_api_hash_here"      # Your API hash from my.telegram.org
  session_file: "data/teleflux.session"  # Where to store the session
  notify_chat_id: "me"                # "me" for Saved Messages, "@username" for bots, or numeric ID

miniflux:
  url: "https://your-miniflux.com"    # Your Miniflux URL
  token: "your_miniflux_token"        # Your Miniflux API token

rsshub:
  base_url: "https://rsshub.app"      # RSSHub instance URL

sync:
  folders:
    - "News"                          # List of Telegram folders to sync
    - "Technology"
    - "Entertainment"
  
  remove_absent_feeds: true           # Remove feeds for unfollowed channels
  private_feed_mode: "skip"           # How to handle private channels (skip or secret)
  validate_feeds: true                # Check if RSS feeds work before adding
  keep_emojis_in_titles: false        # Remove emojis from feed titles
  disable_title_updates: false       # Keep feed titles updated
  notify_no_changes: false            # Send notifications even when no changes made

logging:
  level: "INFO"                       # How much detail in logs (DEBUG, INFO, WARNING, ERROR)
  quiet: false                        # Only show ERROR and CRITICAL messages (for automated runs)

notifications:
  enabled: true                       # Enable/disable Telegram notifications
  chat_id: "me"                       # Chat to send notifications to (optional)
```

### Getting Your Miniflux API Token

1. Open your Miniflux web interface
2. Go to Settings → API Keys
3. Create a new API key
4. Copy the token and paste it in your config file

## Initial Setup

### Step 1: Organize Your Telegram Channels

Organize your Telegram channels into folders:

1. In Telegram, go to Settings → Folders
2. Create folders like "News", "Technology", "Entertainment"
3. Add relevant channels to each folder

### Step 2: List Your Folders

See which folders Teleflux can find:

```bash
teleflux --list-folders
```

This shows all your Telegram folders and how many channels are in each.

### Step 3: Check Unorganized Channels

See which channels aren't in any folder:

```bash
teleflux --list-unfoldered-channels
```

Consider organizing these channels into folders for better management.

### Step 4: Test Configuration

Run a dry-run to see what Teleflux would do without making changes:

```bash
teleflux --dry-run
```

This shows exactly what feeds would be created, updated, or removed.

## Usage

### Basic Synchronization

```bash
# Run synchronization
teleflux

# Use a different config file
teleflux --config /path/to/config.yml

# Run without making changes (preview only)
teleflux --dry-run

# Run quietly (for automated scripts)
teleflux --quiet
```

The `--quiet` flag suppresses all output except errors. You can also configure quiet mode in your config file using `logging.quiet: true`, which is useful for Docker deployments and automated runs. The CLI flag takes precedence over the config setting.

### Management Commands

```bash
# List all your Telegram folders
teleflux --list-folders

# Show channels not in any folder
teleflux --list-unfoldered-channels

# Use a custom session file location
teleflux --session-file /path/to/session.session
```

## Folder Configuration Options

You can configure folder mapping in two ways:

**Simple format** (folder name becomes category name):
```yaml
sync:
  folders:
    - "News"
    - "Technology"
    - "Entertainment"
```

**Advanced format** (map folder names to different category names):
```yaml
sync:
  folders:
    "My News": "News"
    "Tech Stuff": "Technology"
    "Fun Things": "Entertainment"
```

## Automation

### Scheduled Synchronization

To run Teleflux automatically every hour, add this to your crontab:

```bash
# Edit your crontab
crontab -e

# Add this line (adjust paths as needed)
0 * * * * cd /path/to/teleflux && /path/to/teleflux/.venv/bin/teleflux --quiet
```

For daily synchronization at 6 AM:
```bash
0 6 * * * cd /path/to/teleflux && /path/to/teleflux/.venv/bin/teleflux --quiet
```

### Using with Docker

Teleflux includes ready-to-use Docker configuration:

- **Docker Compose**: Use the included `docker-compose.yml` file in the repository
- **Dockerfile**: Build your own image using the provided `Dockerfile`
- **Pre-built Image**: Use the image from GitHub Container Registry: `ghcr.io/petrouv/teleflux:latest`

#### Preparation for Docker Launch

Before running the Docker container, you need to prepare the required directories and configuration:

```bash
# Create necessary directories
mkdir -p config data

# Copy configuration template and customize it
cp config/config.yml.example config/config.yml
# Edit config/config.yml with your settings (see Configuration section above)

# Get your user ID and update docker-compose.yml
id -u
# Replace "1000" in docker-compose.yml with your actual user ID
```

Edit the `user` field in `docker-compose.yml` to match your user ID (obtained from `id -u` command). This ensures proper file permissions for the mounted volumes.

```bash
# Using the included docker-compose.yml
docker-compose up -d

# Or using the pre-built image directly
docker run -v ./config:/app/config -v ./data:/app/data ghcr.io/petrouv/teleflux:latest
```

## Troubleshooting

### Common Issues

**"Configuration file not found"**
- Make sure `config/config.yml` exists in the project directory
- Use `--config` to specify a different location

**"Failed to connect to Telegram"**
- Check your internet connection
- Verify your `api_id` and `api_hash` are correct
- Recreate the session file if needed

**"Miniflux API error"**
- Verify your Miniflux URL is correct and accessible
- Check that your API token is valid
- Ensure Miniflux is running and reachable

**"RSSHub connection failed"**
- Verify your RSSHub URL is correct
- Check if RSSHub is running and accessible
- Try using a public RSSHub instance like https://rsshub.app

### Session File Issues

If you need to recreate your Telegram session:

1. Delete the existing session file: `rm data/teleflux.session`
2. Run Teleflux again: `teleflux --dry-run`
3. Enter your phone number and verification code when prompted

### Private Channels

For private Telegram channels, Teleflux can either:
- `skip` - ignore private channels (default)
- `secret` - create RSS feeds using channel hashes (advanced)

Set `private_feed_mode` in your config file accordingly.

## Emoji Handling

Teleflux automatically removes emojis from channel titles when creating RSS feeds, making your RSS reader cleaner and more readable.

**Default behavior (recommended):**
```yaml
sync:
  keep_emojis_in_titles: false  # Removes emojis from feed titles
```

**Examples:**
- "🚀 Tech News 📱" becomes "Tech News"
- "AI & ML 🤖💡 Updates" becomes "AI & ML Updates"
- "📰 Daily News 🔥" becomes "Daily News"

**To preserve emojis:**
```yaml
sync:
  keep_emojis_in_titles: true   # Keeps emojis in feed titles
```

This setting affects both new feeds and title updates for existing feeds.

## Understanding Notifications

Teleflux sends you Telegram notifications after each synchronization, showing:
- Number of feeds added, updated, or removed
- Any errors that occurred
- Summary of changes made

### Notification Destinations

You can configure where notifications are sent using the `notify_chat_id` setting:

```yaml
telegram:
  notify_chat_id: "me"           # Send to your Saved Messages (default)
  # notify_chat_id: "@your_bot"  # Send to a specific bot
  # notify_chat_id: 123456789    # Send to a specific chat ID
```

**Options:**
- `"me"` - Sends notifications to your Saved Messages
- `"@username"` - Sends notifications to a specific bot or user
- Numeric ID - Sends notifications to a specific chat

### Notification Frequency

By default, notifications are only sent when there are actual changes or errors. If you want to receive notifications even when no changes were made (useful for monitoring that synchronization is running), you can enable this behavior:

```yaml
sync:
  notify_no_changes: true    # Send notifications even when no changes made
```

You can also completely disable notifications by adding a `notifications` section to your config:

```yaml
notifications:
  enabled: false
```

## Exit Codes

Teleflux uses different exit codes to indicate what happened:
- `0` - Success
- `2` - Configuration file not found
- `3` - Configuration error
- `4` - Application error
- `5` - External service unavailable (Telegram/Miniflux/RSSHub)
- `130` - Interrupted by user (Ctrl+C)

This helps with automated scripts and monitoring.