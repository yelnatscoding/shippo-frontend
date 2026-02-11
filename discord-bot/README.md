# Discord Shipping Bot

Discord bot with calendar sync, shipping labels, Google Drive notifications, and AI chat.

## Features

### Calendar Sync
- Monitors email accounts via IMAP for calendar invites
- Parses iCal (.ics) files and plain text events
- Posts events to Discord with RSVP buttons (✅ ❌ ❓)
- Creates native Discord scheduled events

### Shipping Labels
- Natural language: "Ship 5lbs to Austin TX 78701"
- Fetches rates from EasyPost
- Click to select rate and purchase label
- Labels stored with PDF in database
- Commands:
  - `/labels` - View your recent labels
  - `/label <tracking>` - Re-download label PDF
  - `/void <tracking>` - Void a label

### Google Drive Notifications
- Watches configured folders for changes
- Posts when files are added, modified, or deleted
- Configurable file type filters

### AI Chat Assistant
- @mention the bot with questions
- Has access to calendar events, drive files, and shipping data
- `/ask <question>` - Ask directly via slash command

## Setup

### 1. Create Discord Bot

1. Go to https://discord.com/developers/applications
2. Click "New Application" and give it a name
3. Go to "Bot" section and click "Add Bot"
4. Copy the bot token
5. Enable these Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent (optional)
6. Go to "OAuth2" > "URL Generator"
7. Select scopes: `bot`, `applications.commands`
8. Select permissions:
   - Send Messages
   - Create Public Threads
   - Send Messages in Threads
   - Manage Events
   - Add Reactions
   - Read Message History
   - Attach Files
   - Use Slash Commands
9. Copy the generated URL and open it to invite the bot to your server

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
EMAIL_PASS_1=your_purelymail_password
EMAIL_PASS_2=optional_second_account_password
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
POSTGRES_URL=postgresql://user:pass@host/db
```

### 3. Configure Bot Settings

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your channel IDs and settings:
- Get channel IDs by enabling Developer Mode in Discord, then right-click a channel

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Initialize Database

```bash
python -c "from services.database import Database; Database().init_schema()"
```

### 6. Run Bot

```bash
python bot.py
```

## Deploy as Service (Linux)

```bash
# Copy service file (edit paths first!)
sudo cp discord-bot.service /etc/systemd/system/

# Edit the service file with correct paths
sudo nano /etc/systemd/system/discord-bot.service

# Enable and start
sudo systemctl enable discord-bot
sudo systemctl start discord-bot

# Check status
sudo systemctl status discord-bot

# View logs
journalctl -u discord-bot -f

# Restart after updates
sudo systemctl restart discord-bot
```

## Configuration Reference

### config.yaml

```yaml
discord:
  bot_token_env: "DISCORD_BOT_TOKEN"

calendar:
  channel_id: "123456789012345678"  # Channel for calendar events
  poll_interval_seconds: 60
  accounts:
    - email: "calendar@yourdomain.com"
      imap_host: "imap.purelymail.com"
      smtp_host: "smtp.purelymail.com"
      password_env: "EMAIL_PASS_1"

shipping:
  channel_id: "123456789012345678"  # Channel for shipping requests
  default_origin_address:
    name: "Your Name"
    street1: "123 Main St"
    city: "Your City"
    state: "CA"
    zip: "90001"

drive:
  channel_id: "123456789012345678"  # Channel for drive notifications
  poll_interval_seconds: 300
  watched_folders:
    - folder_id: "1ABC123..."  # Get from Google Drive URL
      name: "Shipping Documents"
      notify_on: [created, modified, deleted]
      file_types: [pdf, docx, xlsx]  # Optional filter

ai_chat:
  channel_id: "123456789012345678"  # Channel for AI chat (optional)
  trigger: "mention"  # Only respond to @mentions
  context_sources: [calendar, drive, shipping]
```

## Troubleshooting

### Bot not responding
- Check that the bot is online in Discord
- Verify channel IDs in config.yaml
- Check logs: `journalctl -u discord-bot -f`

### Calendar events not syncing
- Verify email credentials in .env
- Check IMAP server settings
- Look for errors in logs

### Drive notifications not working
- Ensure service account has access to folders
- Check GOOGLE_SERVICE_ACCOUNT_JSON is valid JSON
- Verify folder IDs are correct

### Shipping not working
- Check EASYPOST_API_KEY is set in parent .env
- Verify shipping clients are importable

## License

MIT
