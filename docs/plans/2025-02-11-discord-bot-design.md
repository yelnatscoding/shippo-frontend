# Discord Bot Design

## Overview

A Discord bot for the shipping tool project that provides:
- Calendar sync via email (IMAP/SMTP)
- Shipping label creation via natural conversation
- Google Drive change notifications
- AI-powered chat assistant

## Architecture

```
discord-bot/
├── bot.py                 # Main entry point
├── config.yaml            # Channel IDs, watched folders, email accounts
├── cogs/
│   ├── calendar.py        # Calendar sync + RSVP handling
│   ├── shipping.py        # Natural language shipping quotes/labels
│   ├── drive.py           # Google Drive change notifications
│   └── assistant.py       # AI chat with full context access
├── services/
│   ├── email_client.py    # IMAP reader + SMTP sender (for RSVPs)
│   ├── calendar_parser.py # Parse iCal, Google invites, plain text
│   ├── gemini_client.py   # Natural language parsing for shipping + AI chat
│   ├── drive_watcher.py   # Google Drive API polling
│   └── shipping_client.py # Reuses existing rate/label logic
├── requirements.txt
└── discord-bot.service    # systemd unit file for auto-start
```

## Tech Stack

- `discord.py` - Bot framework
- `google-generativeai` - Natural language parsing + AI chat
- `imapclient` + `smtplib` - Email handling
- `icalendar` - Calendar parsing
- `psycopg2` - Postgres (Neon DB)
- `google-api-python-client` - Drive API
- Existing shipping clients from `shippo-frontend/lib/`

## Feature 1: Calendar Sync

### Flow
1. Bot checks Purelymail accounts via IMAP every 60 seconds
2. Parses incoming emails for calendar events:
   - `.ics` attachments → `icalendar` library
   - Google Calendar links → extracted and fetched
   - Plain text → Gemini extracts date/time/title/location
3. When event found:
   - Posts embed to configured channel with event details
   - Creates native Discord Scheduled Event
   - Adds reaction buttons: ✅ Accept | ❌ Decline | ❓ Maybe
4. RSVP flow:
   - User clicks reaction
   - Bot sends reply email via SMTP to original sender
   - Updates Discord embed to show who responded
   - Stores RSVP in Postgres

### Config
```yaml
calendar:
  channel_id: "123456789"
  poll_interval_seconds: 60
  accounts:
    - email: "calendar@yourdomain.com"
      imap_host: "imap.purelymail.com"
      smtp_host: "smtp.purelymail.com"
      password_env: "EMAIL_PASS_1"
```

## Feature 2: Shipping Labels

### Flow
1. User sends natural language message:
   - "I need to ship a 5lb package to Austin TX"
   - "Quote me for 44x29x26 box, 13 pounds, going to 78263"
2. Gemini parses to extract dimensions, weight, destination
3. Bot fetches rates from all providers in parallel
4. Displays embed with options:
   ```
   📦 Shipping Quote to 78263

   1️⃣ USPS Priority - $12.45 (3 days)
   2️⃣ UPS Ground - $15.20 (4 days)
   3️⃣ FedEx Home - $18.90 (2 days)

   Click a number to purchase, ❌ to cancel
   ```
5. User clicks reaction → Bot confirms → Creates label → Posts tracking + PDF

### Label Storage (Postgres)
```sql
labels table:
- id (primary key)
- tracking_number
- carrier
- service
- provider
- provider_label_id      -- for voiding
- provider_shipment_id   -- for voiding
- rate_amount
- label_pdf_base64
- label_url
- from_address (JSON)
- to_address (JSON)
- parcel (JSON)
- status (active, voided)
- created_at
- voided_at
- discord_user_id
- discord_message_id
```

### Commands
- `!labels` - List recent labels
- `!label <tracking>` - Re-download PDF
- `!void <tracking>` - Void label (with confirmation)

### Config
```yaml
shipping:
  channel_id: "987654321"
  default_origin_zip: "91761"
  max_options_shown: 5
```

## Feature 3: Google Drive Notifications

### Flow
1. Bot checks Google Drive API every 5 minutes
2. Detects changes in watched folders:
   - New files added
   - Files modified
   - Files deleted
3. Posts embed:
   ```
   📁 Drive Update

   ➕ New: invoice_march.pdf
   📝 Edited: shipping_rates.xlsx
   🗑️ Deleted: old_notes.doc

   Folder: Shipping Documents
   ```
4. File names link directly to Google Drive

### Config
```yaml
drive:
  channel_id: "111222333"
  poll_interval_seconds: 300
  watched_folders:
    - folder_id: "1abc123..."
      name: "Shipping Documents"
      notify_on: [created, modified, deleted]
      file_types: [pdf, xlsx, docx]
    - folder_id: "2def456..."
      name: "Team Calendar"
      notify_on: [created]
      file_types: []
```

## Feature 4: AI Chat Assistant

### Flow
1. User @mentions bot in AI channel:
   - "@Bot what's the next meeting?"
   - "@Bot find the invoice PDF from last week"
   - "@Bot what was the tracking number for Austin?"
2. Bot gathers context from:
   - Calendar events (Postgres)
   - Google Drive file index
   - Shipping label history
3. Sends question + context to Gemini
4. Returns natural language response with relevant links

### Future Enhancement
- Thread-based conversations for cleaner channel

### Config
```yaml
ai_chat:
  channel_id: "444555666"
  trigger: "mention"
  context_sources: [calendar, drive, shipping]
```

## Deployment

### Discord Bot Setup
1. Go to Discord Developer Portal
2. Create Application → Create Bot → Copy token
3. Enable "Message Content Intent"
4. Generate invite link with permissions:
   - Send Messages
   - Create Events
   - Add Reactions
   - Read Message History
   - Attach Files

### Environment Variables
```bash
DISCORD_BOT_TOKEN=your_bot_token
EMAIL_PASS_1=purelymail_password_1
EMAIL_PASS_2=purelymail_password_2
GEMINI_API_KEY=your_gemini_key
GOOGLE_SERVICE_ACCOUNT_JSON={}
# Postgres already configured in .env.local
```

### systemd Service
```ini
[Unit]
Description=Discord Shipping Bot
After=network.target

[Service]
WorkingDirectory=/path/to/discord-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
User=stanhuang

[Install]
WantedBy=multi-user.target
```

### Deploy Commands
```bash
sudo cp discord-bot.service /etc/systemd/system/
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
```

## Configuration File Template

```yaml
# discord-bot/config.yaml

discord:
  bot_token_env: "DISCORD_BOT_TOKEN"

calendar:
  channel_id: ""
  poll_interval_seconds: 60
  accounts:
    - email: ""
      imap_host: "imap.purelymail.com"
      smtp_host: "smtp.purelymail.com"
      password_env: "EMAIL_PASS_1"

shipping:
  channel_id: ""
  default_origin_zip: "91761"
  max_options_shown: 5

drive:
  channel_id: ""
  poll_interval_seconds: 300
  watched_folders: []

ai_chat:
  channel_id: ""
  trigger: "mention"
  context_sources: [calendar, drive, shipping]

database:
  url_env: "POSTGRES_URL"
```

## Feature Summary

| Feature | Trigger | Action |
|---------|---------|--------|
| Calendar Sync | IMAP poll (60s) | Post event + Create Discord event + RSVP buttons |
| RSVP Response | Button click | Send email reply via SMTP |
| Shipping Quote | Natural language | Gemini parses → Fetch rates → Show options |
| Label Purchase | Reaction click | Create label → Store in Postgres → Post PDF |
| Label Management | `!labels`, `!void` | Re-download PDF, void with provider API |
| Drive Notifications | API poll (5min) | Post changes to channel |
| AI Chat | @mention | Query all data → Gemini response |
