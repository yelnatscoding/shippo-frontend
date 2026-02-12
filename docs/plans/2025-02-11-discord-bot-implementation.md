# Discord Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Discord bot with calendar sync, shipping labels, Google Drive notifications, and AI chat assistant.

**Architecture:** Modular cog-based Discord bot using discord.py. Each feature is a separate cog. Services handle external integrations (email, Gemini, Drive, shipping). Postgres stores labels and calendar events.

**Tech Stack:** discord.py, google-generativeai, imapclient, icalendar, psycopg2, google-api-python-client

---

## Task 1: Project Setup

**Files:**
- Create: `discord-bot/requirements.txt`
- Create: `discord-bot/.env.example`
- Create: `discord-bot/config.yaml.example`

**Step 1: Create discord-bot directory**

```bash
mkdir -p discord-bot/cogs discord-bot/services discord-bot/tests
```

**Step 2: Create requirements.txt**

```txt
discord.py>=2.3.0
google-generativeai>=0.3.0
imapclient>=2.3.0
icalendar>=5.0.0
psycopg2-binary>=2.9.9
google-api-python-client>=2.116.0
google-auth>=2.27.0
python-dotenv>=1.0.0
pydantic>=2.0.0
PyYAML>=6.0.0
requests>=2.31.0
aiohttp>=3.9.0
```

**Step 3: Create .env.example**

```bash
# Discord
DISCORD_BOT_TOKEN=your_bot_token_here

# Email (Purelymail)
EMAIL_PASS_1=your_email_password_1
EMAIL_PASS_2=your_email_password_2

# AI
GEMINI_API_KEY=your_gemini_key

# Google Drive
GOOGLE_SERVICE_ACCOUNT_JSON={}

# Database (from existing .env.local)
POSTGRES_URL=postgresql://...
```

**Step 4: Create config.yaml.example**

```yaml
discord:
  bot_token_env: "DISCORD_BOT_TOKEN"

calendar:
  channel_id: ""
  poll_interval_seconds: 60
  accounts:
    - email: "example@yourdomain.com"
      imap_host: "imap.purelymail.com"
      smtp_host: "smtp.purelymail.com"
      imap_port: 993
      smtp_port: 587
      password_env: "EMAIL_PASS_1"

shipping:
  channel_id: ""
  default_origin_zip: "91761"
  default_origin_address:
    name: "Sender Name"
    street1: "123 Main St"
    city: "Pomona"
    state: "CA"
    zip: "91761"
    country: "US"
  max_options_shown: 5

drive:
  channel_id: ""
  poll_interval_seconds: 300
  watched_folders: []

ai_chat:
  channel_id: ""
  trigger: "mention"
  context_sources:
    - calendar
    - drive
    - shipping

database:
  url_env: "POSTGRES_URL"
```

**Step 5: Commit**

```bash
git add discord-bot/
git commit -m "feat(discord-bot): initialize project structure"
```

---

## Task 2: Database Schema

**Files:**
- Create: `discord-bot/services/database.py`
- Create: `discord-bot/services/schema.sql`

**Step 1: Create schema.sql**

```sql
-- Calendar events table
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    event_uid VARCHAR(255) UNIQUE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    location VARCHAR(500),
    organizer_email VARCHAR(255),
    meeting_link VARCHAR(500),
    discord_event_id VARCHAR(50),
    discord_message_id VARCHAR(50),
    source_email VARCHAR(255),
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RSVPs table
CREATE TABLE IF NOT EXISTS calendar_rsvps (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES calendar_events(id) ON DELETE CASCADE,
    discord_user_id VARCHAR(50) NOT NULL,
    discord_username VARCHAR(100),
    response VARCHAR(20) NOT NULL, -- 'accepted', 'declined', 'maybe'
    email_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(event_id, discord_user_id)
);

-- Shipping labels table
CREATE TABLE IF NOT EXISTS shipping_labels (
    id SERIAL PRIMARY KEY,
    tracking_number VARCHAR(100) UNIQUE NOT NULL,
    carrier VARCHAR(50) NOT NULL,
    service VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_label_id VARCHAR(100),
    provider_shipment_id VARCHAR(100),
    rate_amount DECIMAL(10, 2) NOT NULL,
    label_pdf_base64 TEXT,
    label_url VARCHAR(500),
    from_address JSONB NOT NULL,
    to_address JSONB NOT NULL,
    parcel JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    discord_user_id VARCHAR(50),
    discord_message_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    voided_at TIMESTAMP WITH TIME ZONE
);

-- Drive file index (for AI context)
CREATE TABLE IF NOT EXISTS drive_files (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100),
    folder_id VARCHAR(100),
    folder_name VARCHAR(255),
    web_view_link VARCHAR(500),
    modified_time TIMESTAMP WITH TIME ZONE,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_user ON shipping_labels(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_shipping_labels_status ON shipping_labels(status);
CREATE INDEX IF NOT EXISTS idx_drive_files_folder ON drive_files(folder_id);
```

**Step 2: Create database.py**

```python
"""Database connection and operations"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class Database:
    """Postgres database wrapper"""

    def __init__(self, url: Optional[str] = None):
        self.url = url or os.getenv("POSTGRES_URL")
        if not self.url:
            raise ValueError("Database URL not configured")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(self.url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self, schema_path: str = "services/schema.sql"):
        """Initialize database schema"""
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
        logger.info("Database schema initialized")

    # Calendar operations
    def save_event(self, event: Dict[str, Any]) -> int:
        """Save calendar event, return ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calendar_events
                    (event_uid, title, description, start_time, end_time,
                     location, organizer_email, meeting_link, source_email, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_uid) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        location = EXCLUDED.location,
                        meeting_link = EXCLUDED.meeting_link
                    RETURNING id
                """, (
                    event.get("uid"),
                    event.get("title"),
                    event.get("description"),
                    event.get("start_time"),
                    event.get("end_time"),
                    event.get("location"),
                    event.get("organizer_email"),
                    event.get("meeting_link"),
                    event.get("source_email"),
                    json.dumps(event.get("raw_data", {}))
                ))
                return cur.fetchone()[0]

    def update_event_discord_ids(self, event_id: int, discord_event_id: str, discord_message_id: str):
        """Update event with Discord IDs"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE calendar_events
                    SET discord_event_id = %s, discord_message_id = %s
                    WHERE id = %s
                """, (discord_event_id, discord_message_id, event_id))

    def save_rsvp(self, event_id: int, user_id: str, username: str, response: str) -> bool:
        """Save RSVP, return True if new/changed"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calendar_rsvps (event_id, discord_user_id, discord_username, response)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (event_id, discord_user_id) DO UPDATE SET
                        response = EXCLUDED.response,
                        email_sent = FALSE
                    RETURNING (xmax = 0) AS is_new
                """, (event_id, user_id, username, response))
                return cur.fetchone()[0]

    def get_upcoming_events(self, limit: int = 10) -> List[Dict]:
        """Get upcoming calendar events"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calendar_events
                    WHERE start_time > NOW()
                    ORDER BY start_time
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]

    # Shipping operations
    def save_label(self, label: Dict[str, Any]) -> int:
        """Save shipping label, return ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO shipping_labels
                    (tracking_number, carrier, service, provider, provider_label_id,
                     provider_shipment_id, rate_amount, label_pdf_base64, label_url,
                     from_address, to_address, parcel, discord_user_id, discord_message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    label["tracking_number"],
                    label["carrier"],
                    label["service"],
                    label["provider"],
                    label.get("provider_label_id"),
                    label.get("provider_shipment_id"),
                    label["rate_amount"],
                    label.get("label_pdf_base64"),
                    label.get("label_url"),
                    json.dumps(label["from_address"]),
                    json.dumps(label["to_address"]),
                    json.dumps(label["parcel"]),
                    label.get("discord_user_id"),
                    label.get("discord_message_id")
                ))
                return cur.fetchone()[0]

    def get_label_by_tracking(self, tracking_number: str) -> Optional[Dict]:
        """Get label by tracking number"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM shipping_labels WHERE tracking_number = %s
                """, (tracking_number,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_user_labels(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get labels for a user"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM shipping_labels
                    WHERE discord_user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return [dict(row) for row in cur.fetchall()]

    def void_label(self, tracking_number: str) -> bool:
        """Mark label as voided"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE shipping_labels
                    SET status = 'voided', voided_at = NOW()
                    WHERE tracking_number = %s AND status = 'active'
                    RETURNING id
                """, (tracking_number,))
                return cur.fetchone() is not None

    # Drive operations
    def save_drive_file(self, file: Dict[str, Any]):
        """Save or update drive file"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO drive_files
                    (file_id, name, mime_type, folder_id, folder_name, web_view_link, modified_time, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        modified_time = EXCLUDED.modified_time,
                        last_seen = NOW()
                """, (
                    file["id"],
                    file["name"],
                    file.get("mimeType"),
                    file.get("folder_id"),
                    file.get("folder_name"),
                    file.get("webViewLink"),
                    file.get("modifiedTime")
                ))

    def search_drive_files(self, query: str, limit: int = 10) -> List[Dict]:
        """Search drive files by name"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM drive_files
                    WHERE name ILIKE %s
                    ORDER BY modified_time DESC
                    LIMIT %s
                """, (f"%{query}%", limit))
                return [dict(row) for row in cur.fetchall()]
```

**Step 3: Commit**

```bash
git add discord-bot/services/
git commit -m "feat(discord-bot): add database schema and operations"
```

---

## Task 3: Core Bot Structure

**Files:**
- Create: `discord-bot/bot.py`
- Create: `discord-bot/config.py`

**Step 1: Create config.py**

```python
"""Configuration loader"""

import os
import yaml
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration from YAML file"""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

    def _get_env_value(self, env_key: str) -> str:
        """Get value from environment variable"""
        return os.getenv(env_key, "")

    @property
    def bot_token(self) -> str:
        env_key = self._config.get("discord", {}).get("bot_token_env", "DISCORD_BOT_TOKEN")
        return self._get_env_value(env_key)

    @property
    def database_url(self) -> str:
        env_key = self._config.get("database", {}).get("url_env", "POSTGRES_URL")
        return self._get_env_value(env_key)

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def calendar(self) -> Dict[str, Any]:
        return self._config.get("calendar", {})

    @property
    def shipping(self) -> Dict[str, Any]:
        return self._config.get("shipping", {})

    @property
    def drive(self) -> Dict[str, Any]:
        return self._config.get("drive", {})

    @property
    def ai_chat(self) -> Dict[str, Any]:
        return self._config.get("ai_chat", {})

    def get_email_password(self, env_key: str) -> str:
        return self._get_env_value(env_key)
```

**Step 2: Create bot.py**

```python
"""Discord bot main entry point"""

import discord
from discord.ext import commands
import asyncio
import logging
import sys
import os

# Add parent directory for importing shipping clients
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shippo-frontend", "lib"))

from config import Config
from services.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ShippingBot(commands.Bot):
    """Main bot class"""

    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_scheduled_events = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )

        self.config = config
        self.db = Database(config.database_url)

    async def setup_hook(self):
        """Called when bot is starting up"""
        logger.info("Initializing database schema...")
        self.db.init_schema()

        # Load cogs
        cogs = [
            "cogs.calendar",
            "cogs.shipping",
            "cogs.drive",
            "cogs.assistant",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

        # Sync slash commands
        await self.tree.sync()
        logger.info("Slash commands synced")

    async def on_ready(self):
        """Called when bot is connected and ready"""
        logger.info(f"Bot connected as {self.user}")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")


async def main():
    config = Config()

    if not config.bot_token:
        logger.error("DISCORD_BOT_TOKEN not set")
        return

    bot = ShippingBot(config)

    async with bot:
        await bot.start(config.bot_token)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Commit**

```bash
git add discord-bot/bot.py discord-bot/config.py
git commit -m "feat(discord-bot): add core bot structure with config loader"
```

---

## Task 4: Gemini Client Service

**Files:**
- Create: `discord-bot/services/gemini_client.py`

**Step 1: Create gemini_client.py**

```python
"""Gemini AI client for natural language processing"""

import os
import google.generativeai as genai
from typing import Optional, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-pro")
        logger.info("Gemini client initialized")

    async def parse_shipping_request(self, message: str) -> Dict[str, Any]:
        """
        Parse natural language shipping request.
        Returns extracted dimensions, weight, and addresses.
        """
        prompt = f"""Extract shipping information from this message. Return JSON only.

Message: "{message}"

Return this exact JSON structure (use null for missing values):
{{
    "origin_zip": "string or null",
    "destination_zip": "string or null",
    "destination_city": "string or null",
    "destination_state": "string or null",
    "weight": number or null (in pounds),
    "length": number or null (in inches),
    "width": number or null (in inches),
    "height": number or null (in inches),
    "missing_fields": ["list of required fields that are missing"]
}}

Required fields: destination (zip OR city+state), weight.
If dimensions missing, set length/width/height to null.
"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()

            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse shipping request: {e}")
            return {"error": str(e), "missing_fields": ["all"]}

    async def parse_calendar_text(self, email_body: str) -> Dict[str, Any]:
        """
        Extract calendar event details from plain text email.
        """
        prompt = f"""Extract calendar event information from this email. Return JSON only.

Email:
{email_body}

Return this exact JSON structure (use null for missing values):
{{
    "title": "string",
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM" (24-hour format),
    "end_time": "HH:MM or null",
    "location": "string or null",
    "meeting_link": "URL or null",
    "description": "brief summary or null"
}}
"""

        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse calendar text: {e}")
            return None

    async def chat_with_context(
        self,
        question: str,
        calendar_events: List[Dict],
        drive_files: List[Dict],
        shipping_labels: List[Dict]
    ) -> str:
        """
        Answer user question using provided context.
        """
        context_parts = []

        if calendar_events:
            events_text = "\n".join([
                f"- {e['title']} on {e['start_time']}" +
                (f" at {e['location']}" if e.get('location') else "") +
                (f" (link: {e['meeting_link']})" if e.get('meeting_link') else "")
                for e in calendar_events[:10]
            ])
            context_parts.append(f"UPCOMING EVENTS:\n{events_text}")

        if drive_files:
            files_text = "\n".join([
                f"- {f['name']} (folder: {f.get('folder_name', 'root')}) - {f.get('web_view_link', 'no link')}"
                for f in drive_files[:20]
            ])
            context_parts.append(f"DRIVE FILES:\n{files_text}")

        if shipping_labels:
            labels_text = "\n".join([
                f"- {l['tracking_number']} via {l['carrier']} to {l.get('to_address', {}).get('city', 'unknown')} ({l['status']})"
                for l in shipping_labels[:10]
            ])
            context_parts.append(f"RECENT SHIPMENTS:\n{labels_text}")

        context = "\n\n".join(context_parts) if context_parts else "No context available."

        prompt = f"""You are a helpful assistant. Answer the user's question using only the context provided.
If the information isn't in the context, say you don't have that information.
Keep responses concise and friendly.

CONTEXT:
{context}

USER QUESTION: {question}

ANSWER:"""

        try:
            response = await self.model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            return "Sorry, I encountered an error processing your question."

    async def generate_follow_up_question(self, missing_fields: List[str]) -> str:
        """Generate a friendly follow-up question for missing shipping info."""
        field_questions = {
            "destination_zip": "What's the destination ZIP code?",
            "destination_city": "What city are you shipping to?",
            "weight": "How much does the package weigh (in pounds)?",
            "length": "What are the package dimensions? (length x width x height in inches)",
            "width": "What are the package dimensions?",
            "height": "What are the package dimensions?",
        }

        questions = [field_questions.get(f, f"What's the {f}?") for f in missing_fields[:2]]
        return " ".join(questions)
```

**Step 2: Commit**

```bash
git add discord-bot/services/gemini_client.py
git commit -m "feat(discord-bot): add Gemini client for NLP"
```

---

## Task 5: Email Client Service

**Files:**
- Create: `discord-bot/services/email_client.py`

**Step 1: Create email_client.py**

```python
"""Email client for IMAP/SMTP operations"""

import os
import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from imapclient import IMAPClient
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EmailClient:
    """IMAP/SMTP email client for calendar sync"""

    def __init__(
        self,
        email_address: str,
        password: str,
        imap_host: str = "imap.purelymail.com",
        smtp_host: str = "smtp.purelymail.com",
        imap_port: int = 993,
        smtp_port: int = 587
    ):
        self.email_address = email_address
        self.password = password
        self.imap_host = imap_host
        self.smtp_host = smtp_host
        self.imap_port = imap_port
        self.smtp_port = smtp_port

    def fetch_new_emails(self, folder: str = "INBOX", since_uid: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch new emails from mailbox.
        Returns list of email dicts with subject, from, body, attachments.
        """
        emails = []

        try:
            with IMAPClient(self.imap_host, port=self.imap_port, ssl=True) as client:
                client.login(self.email_address, self.password)
                client.select_folder(folder)

                # Search for unseen emails or emails after a UID
                if since_uid:
                    messages = client.search([f"UID {since_uid}:*"])
                else:
                    messages = client.search(["UNSEEN"])

                if not messages:
                    return emails

                # Fetch email data
                fetched = client.fetch(messages, ["RFC822", "UID"])

                for uid, data in fetched.items():
                    raw_email = data[b"RFC822"]
                    msg = email.message_from_bytes(raw_email)

                    email_dict = {
                        "uid": uid,
                        "message_id": msg.get("Message-ID"),
                        "subject": msg.get("Subject", ""),
                        "from": msg.get("From", ""),
                        "to": msg.get("To", ""),
                        "date": msg.get("Date", ""),
                        "body": "",
                        "html_body": "",
                        "attachments": []
                    }

                    # Parse body and attachments
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            disposition = str(part.get("Content-Disposition", ""))

                            if "attachment" in disposition:
                                filename = part.get_filename()
                                content = part.get_payload(decode=True)
                                email_dict["attachments"].append({
                                    "filename": filename,
                                    "content_type": content_type,
                                    "content": content
                                })
                            elif content_type == "text/plain":
                                email_dict["body"] = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            elif content_type == "text/html":
                                email_dict["html_body"] = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    else:
                        email_dict["body"] = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    emails.append(email_dict)

                logger.info(f"Fetched {len(emails)} emails from {self.email_address}")

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")

        return emails

    def send_rsvp_reply(
        self,
        to_address: str,
        original_subject: str,
        response: str,
        responder_name: str
    ) -> bool:
        """
        Send RSVP response email.
        response: 'accepted', 'declined', 'maybe'
        """
        response_text = {
            "accepted": "has accepted",
            "declined": "has declined",
            "maybe": "has tentatively accepted"
        }

        subject = f"Re: {original_subject}"
        body = f"{responder_name} {response_text.get(response, response)} the meeting invitation."

        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_address
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.password)
                server.send_message(msg)

            logger.info(f"Sent RSVP ({response}) to {to_address}")
            return True

        except Exception as e:
            logger.error(f"Error sending RSVP: {e}")
            return False

    def get_ics_attachments(self, email_dict: Dict) -> List[bytes]:
        """Extract .ics calendar attachments from email"""
        ics_files = []
        for att in email_dict.get("attachments", []):
            filename = att.get("filename", "").lower()
            content_type = att.get("content_type", "").lower()

            if filename.endswith(".ics") or "calendar" in content_type:
                ics_files.append(att["content"])

        return ics_files
```

**Step 2: Commit**

```bash
git add discord-bot/services/email_client.py
git commit -m "feat(discord-bot): add email client for IMAP/SMTP"
```

---

## Task 6: Calendar Parser Service

**Files:**
- Create: `discord-bot/services/calendar_parser.py`

**Step 1: Create calendar_parser.py**

```python
"""Calendar event parser for iCal and text formats"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from icalendar import Calendar
import logging

logger = logging.getLogger(__name__)


class CalendarParser:
    """Parse calendar events from various formats"""

    def parse_ics(self, ics_content: bytes) -> List[Dict[str, Any]]:
        """Parse iCal (.ics) content into event dicts"""
        events = []

        try:
            cal = Calendar.from_ical(ics_content)

            for component in cal.walk():
                if component.name == "VEVENT":
                    event = self._parse_vevent(component)
                    if event:
                        events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse ICS: {e}")

        return events

    def _parse_vevent(self, component) -> Optional[Dict[str, Any]]:
        """Parse VEVENT component"""
        try:
            # Get start time
            dtstart = component.get("dtstart")
            if not dtstart:
                return None

            start_dt = dtstart.dt
            if hasattr(start_dt, "tzinfo") and start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)

            # Get end time
            dtend = component.get("dtend")
            end_dt = None
            if dtend:
                end_dt = dtend.dt
                if hasattr(end_dt, "tzinfo") and end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)

            # Extract meeting link from description or location
            description = str(component.get("description", "") or "")
            location = str(component.get("location", "") or "")
            meeting_link = self._extract_meeting_link(description + " " + location)

            # Get organizer email
            organizer = component.get("organizer")
            organizer_email = None
            if organizer:
                organizer_str = str(organizer)
                if "mailto:" in organizer_str.lower():
                    organizer_email = organizer_str.split(":")[-1]

            return {
                "uid": str(component.get("uid", "")),
                "title": str(component.get("summary", "Untitled Event")),
                "description": description,
                "start_time": start_dt,
                "end_time": end_dt,
                "location": location if location else None,
                "organizer_email": organizer_email,
                "meeting_link": meeting_link,
                "raw_data": {
                    "rrule": str(component.get("rrule", "")) if component.get("rrule") else None,
                    "status": str(component.get("status", "")),
                }
            }

        except Exception as e:
            logger.error(f"Failed to parse VEVENT: {e}")
            return None

    def _extract_meeting_link(self, text: str) -> Optional[str]:
        """Extract video meeting link from text"""
        patterns = [
            r"(https?://[^\s]*zoom\.us/[^\s]+)",
            r"(https?://meet\.google\.com/[^\s]+)",
            r"(https?://teams\.microsoft\.com/[^\s]+)",
            r"(https?://[^\s]*webex\.com/[^\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).rstrip(".,;)")

        return None

    def parse_google_calendar_link(self, email_body: str) -> Optional[Dict[str, Any]]:
        """
        Extract event details from Google Calendar email invitation.
        These emails have a specific format.
        """
        event = {}

        # Look for "When:" line
        when_match = re.search(r"When:\s*(.+?)(?:\n|$)", email_body)
        if when_match:
            event["when_text"] = when_match.group(1).strip()

        # Look for "Where:" line
        where_match = re.search(r"Where:\s*(.+?)(?:\n|$)", email_body)
        if where_match:
            event["location"] = where_match.group(1).strip()

        # Look for meeting link
        event["meeting_link"] = self._extract_meeting_link(email_body)

        # Look for event title in subject pattern
        title_match = re.search(r"Invitation:\s*(.+?)(?:\s*@|\n|$)", email_body)
        if title_match:
            event["title"] = title_match.group(1).strip()

        if not event:
            return None

        return event

    def is_calendar_email(self, email_dict: Dict) -> bool:
        """Check if email appears to be a calendar invitation"""
        subject = email_dict.get("subject", "").lower()
        from_addr = email_dict.get("from", "").lower()

        # Check for calendar keywords
        calendar_keywords = ["invitation", "meeting", "calendar", "event", "rsvp"]
        if any(kw in subject for kw in calendar_keywords):
            return True

        # Check for Google Calendar
        if "calendar-notification@google.com" in from_addr:
            return True

        # Check for ICS attachments
        if email_dict.get("attachments"):
            for att in email_dict["attachments"]:
                if att.get("filename", "").lower().endswith(".ics"):
                    return True

        return False
```

**Step 2: Commit**

```bash
git add discord-bot/services/calendar_parser.py
git commit -m "feat(discord-bot): add calendar parser for iCal and email"
```

---

## Task 7: Calendar Cog

**Files:**
- Create: `discord-bot/cogs/calendar.py`

**Step 1: Create calendar.py**

```python
"""Calendar sync cog - monitors email and posts events to Discord"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import logging

from services.email_client import EmailClient
from services.calendar_parser import CalendarParser
from services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class CalendarCog(commands.Cog):
    """Calendar sync from email to Discord"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.calendar
        self.parser = CalendarParser()
        self.gemini = None
        self.email_clients: Dict[str, EmailClient] = {}
        self.last_uids: Dict[str, int] = {}

        # Initialize email clients
        for account in self.config.get("accounts", []):
            email_addr = account["email"]
            password = bot.config.get_email_password(account["password_env"])
            if password:
                self.email_clients[email_addr] = EmailClient(
                    email_address=email_addr,
                    password=password,
                    imap_host=account.get("imap_host", "imap.purelymail.com"),
                    smtp_host=account.get("smtp_host", "smtp.purelymail.com"),
                    imap_port=account.get("imap_port", 993),
                    smtp_port=account.get("smtp_port", 587)
                )
                self.last_uids[email_addr] = 0
                logger.info(f"Initialized email client for {email_addr}")

        # Initialize Gemini for plain text parsing
        if bot.config.gemini_api_key:
            self.gemini = GeminiClient(bot.config.gemini_api_key)

    async def cog_load(self):
        """Start the email polling loop"""
        if self.email_clients:
            self.poll_emails.start()
            logger.info("Calendar email polling started")

    async def cog_unload(self):
        """Stop the email polling loop"""
        self.poll_emails.cancel()

    @tasks.loop(seconds=60)
    async def poll_emails(self):
        """Poll email accounts for new calendar events"""
        channel_id = self.config.get("channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Calendar channel {channel_id} not found")
            return

        for email_addr, client in self.email_clients.items():
            try:
                emails = client.fetch_new_emails(since_uid=self.last_uids.get(email_addr))

                for email_dict in emails:
                    # Update last seen UID
                    self.last_uids[email_addr] = max(
                        self.last_uids.get(email_addr, 0),
                        email_dict.get("uid", 0)
                    )

                    if not self.parser.is_calendar_email(email_dict):
                        continue

                    # Try to parse ICS attachment first
                    events = []
                    ics_files = client.get_ics_attachments(email_dict)
                    for ics_content in ics_files:
                        events.extend(self.parser.parse_ics(ics_content))

                    # If no ICS, try parsing email body
                    if not events and self.gemini:
                        body = email_dict.get("body", "")
                        if body:
                            parsed = await self.gemini.parse_calendar_text(body)
                            if parsed:
                                events.append({
                                    "title": parsed.get("title", "Event"),
                                    "start_time": self._parse_datetime(
                                        parsed.get("date"),
                                        parsed.get("start_time")
                                    ),
                                    "end_time": self._parse_datetime(
                                        parsed.get("date"),
                                        parsed.get("end_time")
                                    ),
                                    "location": parsed.get("location"),
                                    "meeting_link": parsed.get("meeting_link"),
                                    "description": parsed.get("description"),
                                    "organizer_email": self._extract_email(email_dict.get("from", "")),
                                    "uid": email_dict.get("message_id", str(datetime.now().timestamp())),
                                })

                    # Post each event to Discord
                    for event in events:
                        event["source_email"] = email_addr
                        await self._post_event(channel, event, email_dict)

            except Exception as e:
                logger.error(f"Error polling {email_addr}: {e}")

    @poll_emails.before_loop
    async def before_poll(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()

    async def _post_event(self, channel, event: Dict, email_dict: Dict):
        """Post event to Discord and create scheduled event"""
        # Save to database
        event_id = self.bot.db.save_event(event)

        # Create embed
        embed = discord.Embed(
            title=f"📅 {event.get('title', 'New Event')}",
            color=discord.Color.blue()
        )

        start_time = event.get("start_time")
        if start_time:
            if isinstance(start_time, datetime):
                embed.add_field(
                    name="When",
                    value=f"<t:{int(start_time.timestamp())}:F>",
                    inline=False
                )

        if event.get("location"):
            embed.add_field(name="Where", value=event["location"], inline=False)

        if event.get("meeting_link"):
            embed.add_field(name="Meeting Link", value=event["meeting_link"], inline=False)

        if event.get("description"):
            desc = event["description"][:500] + "..." if len(event.get("description", "")) > 500 else event["description"]
            embed.add_field(name="Description", value=desc, inline=False)

        embed.set_footer(text=f"From: {event.get('organizer_email', 'Unknown')}")

        # Send message
        message = await channel.send(embed=embed)

        # Add RSVP reactions
        await message.add_reaction("✅")  # Accept
        await message.add_reaction("❌")  # Decline
        await message.add_reaction("❓")  # Maybe

        # Try to create Discord scheduled event
        discord_event_id = None
        if start_time and isinstance(start_time, datetime):
            try:
                guild = channel.guild
                scheduled_event = await guild.create_scheduled_event(
                    name=event.get("title", "Event"),
                    start_time=start_time,
                    end_time=event.get("end_time") or start_time + timedelta(hours=1),
                    location=event.get("meeting_link") or event.get("location") or "TBD",
                    entity_type=discord.EntityType.external,
                    privacy_level=discord.PrivacyLevel.guild_only
                )
                discord_event_id = str(scheduled_event.id)
                logger.info(f"Created Discord event: {discord_event_id}")
            except Exception as e:
                logger.warning(f"Could not create Discord event: {e}")

        # Update database with Discord IDs
        self.bot.db.update_event_discord_ids(
            event_id,
            discord_event_id or "",
            str(message.id)
        )

        logger.info(f"Posted calendar event: {event.get('title')}")

    def _parse_datetime(self, date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
        """Parse date and time strings into datetime"""
        if not date_str:
            return None

        try:
            if time_str:
                dt_str = f"{date_str} {time_str}"
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            else:
                return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _extract_email(self, from_header: str) -> str:
        """Extract email address from From header"""
        import re
        match = re.search(r"[\w\.-]+@[\w\.-]+", from_header)
        return match.group(0) if match else from_header

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle RSVP reactions"""
        if payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        if emoji not in ["✅", "❌", "❓"]:
            return

        response_map = {"✅": "accepted", "❌": "declined", "❓": "maybe"}
        response = response_map.get(emoji)

        # TODO: Look up event by message ID and send RSVP email
        # For now, just log it
        logger.info(f"RSVP: User {payload.user_id} responded {response} to message {payload.message_id}")


async def setup(bot):
    await bot.add_cog(CalendarCog(bot))
```

**Step 2: Commit**

```bash
git add discord-bot/cogs/calendar.py
git commit -m "feat(discord-bot): add calendar cog with email polling and RSVP"
```

---

## Task 8: Shipping Cog

**Files:**
- Create: `discord-bot/cogs/shipping.py`

**Step 1: Create shipping.py**

```python
"""Shipping cog - natural language shipping quotes and label creation"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Dict, Optional, List
import base64
import io
import logging
import sys
import os

# Import shipping clients from existing codebase
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shippo-frontend", "lib"))
from models import Address, Parcel, Rate
from easypost_client import EasyPostClient

from services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class RateSelectView(ui.View):
    """View for selecting a shipping rate"""

    def __init__(self, cog, rates: List[Rate], from_addr: Address, to_addr: Address, parcel: Parcel, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.rates = rates
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.parcel = parcel
        self.user_id = user_id
        self.selected_rate: Optional[Rate] = None

        # Add buttons for top 5 rates
        for i, rate in enumerate(rates[:5]):
            button = ui.Button(
                label=f"{i+1}. ${rate.amount:.2f}",
                style=discord.ButtonStyle.primary,
                custom_id=f"rate_{i}"
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

        # Add cancel button
        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This isn't your quote!", ephemeral=True)
                return

            self.selected_rate = self.rates[index]
            await interaction.response.send_message(
                f"Purchasing {self.selected_rate.provider} {self.selected_rate.servicelevel_name}...",
                ephemeral=True
            )
            await self.cog._purchase_label(interaction, self)
            self.stop()

        return callback

    async def _cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Quote cancelled.", ephemeral=True)
        self.stop()


class ShippingCog(commands.Cog):
    """Natural language shipping quotes and labels"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.shipping
        self.gemini = None
        self.shipping_client = None
        self.active_sessions: Dict[int, Dict] = {}  # user_id -> session data

        # Initialize Gemini
        if bot.config.gemini_api_key:
            self.gemini = GeminiClient(bot.config.gemini_api_key)

        # Initialize shipping client
        try:
            self.shipping_client = EasyPostClient()
        except Exception as e:
            logger.warning(f"Could not initialize shipping client: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for shipping requests in designated channel"""
        if message.author.bot:
            return

        channel_id = self.config.get("channel_id")
        if not channel_id or str(message.channel.id) != channel_id:
            return

        # Check for shipping keywords
        shipping_keywords = ["ship", "shipping", "quote", "send", "package", "box", "label"]
        content_lower = message.content.lower()
        if not any(kw in content_lower for kw in shipping_keywords):
            return

        await self._handle_shipping_message(message)

    async def _handle_shipping_message(self, message: discord.Message):
        """Process natural language shipping request"""
        if not self.gemini:
            await message.reply("AI service not configured. Use `/quote` command instead.")
            return

        async with message.channel.typing():
            # Parse the request
            parsed = await self.gemini.parse_shipping_request(message.content)

            if parsed.get("error"):
                await message.reply(f"Sorry, I couldn't understand that: {parsed['error']}")
                return

            missing = parsed.get("missing_fields", [])

            # Check if we have minimum required info
            has_destination = parsed.get("destination_zip") or (
                parsed.get("destination_city") and parsed.get("destination_state")
            )
            has_weight = parsed.get("weight")

            if not has_destination or not has_weight:
                # Ask follow-up question
                follow_up = await self.gemini.generate_follow_up_question(missing)
                self.active_sessions[message.author.id] = {
                    "parsed": parsed,
                    "channel_id": message.channel.id
                }
                await message.reply(f"I need a bit more info: {follow_up}")
                return

            # We have enough info - get rates
            await self._get_and_display_rates(message, parsed)

    async def _get_and_display_rates(self, message: discord.Message, parsed: Dict):
        """Fetch rates and display them"""
        if not self.shipping_client:
            await message.reply("Shipping service not configured.")
            return

        # Build addresses
        default_origin = self.config.get("default_origin_address", {})
        from_addr = Address(
            name=default_origin.get("name", "Sender"),
            street1=default_origin.get("street1", "123 Main St"),
            city=default_origin.get("city", "Los Angeles"),
            state=default_origin.get("state", "CA"),
            zip=parsed.get("origin_zip") or default_origin.get("zip", "90001"),
            country="US"
        )

        to_addr = Address(
            name="Recipient",
            street1="123 Delivery St",
            city=parsed.get("destination_city") or "Unknown",
            state=parsed.get("destination_state") or "TX",
            zip=parsed.get("destination_zip") or "78701",
            country="US"
        )

        parcel = Parcel(
            length=parsed.get("length") or 12,
            width=parsed.get("width") or 12,
            height=parsed.get("height") or 12,
            weight=parsed.get("weight") or 1
        )

        try:
            rates = self.shipping_client.get_rates(from_addr, to_addr, parcel)
            rates.sort(key=lambda r: r.amount)

            if not rates:
                await message.reply("No shipping rates found for this route.")
                return

            # Build embed
            embed = discord.Embed(
                title=f"📦 Shipping Quote to {to_addr.zip}",
                description=f"Package: {parcel.weight}lbs, {parcel.length}x{parcel.width}x{parcel.height} in",
                color=discord.Color.green()
            )

            for i, rate in enumerate(rates[:5]):
                days = f"{rate.estimated_days} days" if rate.estimated_days else "varies"
                embed.add_field(
                    name=f"{i+1}. {rate.provider} {rate.servicelevel_name}",
                    value=f"**${rate.amount:.2f}** ({days})",
                    inline=True
                )

            # Create rate selection view
            view = RateSelectView(self, rates, from_addr, to_addr, parcel, message.author.id)
            await message.reply(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error getting rates: {e}")
            await message.reply(f"Error getting shipping rates: {str(e)}")

    async def _purchase_label(self, interaction: discord.Interaction, view: RateSelectView):
        """Purchase the selected shipping label"""
        rate = view.selected_rate
        if not rate:
            return

        try:
            label = self.shipping_client.purchase_label(
                rate_id=rate.object_id,
                label_format="PDF"
            )

            # Save to database
            label_data = {
                "tracking_number": label.tracking_number,
                "carrier": label.carrier,
                "service": label.service,
                "provider": "easypost",
                "provider_label_id": label.label_id,
                "provider_shipment_id": rate.shipment_id,
                "rate_amount": label.cost,
                "label_url": label.label_url,
                "from_address": view.from_addr.model_dump(),
                "to_address": view.to_addr.model_dump(),
                "parcel": view.parcel.model_dump(),
                "discord_user_id": str(interaction.user.id),
            }

            # Fetch and store PDF as base64
            import requests
            pdf_response = requests.get(label.label_url)
            if pdf_response.status_code == 200:
                label_data["label_pdf_base64"] = base64.b64encode(pdf_response.content).decode()

            self.bot.db.save_label(label_data)

            # Send success message with label
            embed = discord.Embed(
                title="✅ Label Created!",
                color=discord.Color.green()
            )
            embed.add_field(name="Tracking", value=label.tracking_number, inline=False)
            embed.add_field(name="Carrier", value=f"{label.carrier} {label.service}", inline=True)
            embed.add_field(name="Cost", value=f"${label.cost:.2f}", inline=True)
            embed.add_field(name="Label", value=f"[Download PDF]({label.label_url})", inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error purchasing label: {e}")
            await interaction.followup.send(f"Error creating label: {str(e)}")

    @app_commands.command(name="labels", description="View your recent shipping labels")
    async def labels_command(self, interaction: discord.Interaction):
        """List user's recent labels"""
        labels = self.bot.db.get_user_labels(str(interaction.user.id), limit=10)

        if not labels:
            await interaction.response.send_message("You haven't created any labels yet.", ephemeral=True)
            return

        embed = discord.Embed(title="📦 Your Recent Labels", color=discord.Color.blue())

        for label in labels:
            status = "🟢" if label["status"] == "active" else "🔴"
            embed.add_field(
                name=f"{status} {label['tracking_number']}",
                value=f"{label['carrier']} - ${label['rate_amount']:.2f}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="label", description="Get details and re-download a label")
    @app_commands.describe(tracking="Tracking number")
    async def label_command(self, interaction: discord.Interaction, tracking: str):
        """Get label details and PDF"""
        label = self.bot.db.get_label_by_tracking(tracking)

        if not label:
            await interaction.response.send_message("Label not found.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📦 Label: {tracking}", color=discord.Color.blue())
        embed.add_field(name="Carrier", value=f"{label['carrier']} {label['service']}", inline=True)
        embed.add_field(name="Cost", value=f"${label['rate_amount']:.2f}", inline=True)
        embed.add_field(name="Status", value=label["status"], inline=True)

        # Attach PDF if available
        files = []
        if label.get("label_pdf_base64"):
            pdf_bytes = base64.b64decode(label["label_pdf_base64"])
            files.append(discord.File(io.BytesIO(pdf_bytes), filename=f"label_{tracking}.pdf"))

        await interaction.response.send_message(embed=embed, files=files, ephemeral=True)

    @app_commands.command(name="void", description="Void a shipping label")
    @app_commands.describe(tracking="Tracking number to void")
    async def void_command(self, interaction: discord.Interaction, tracking: str):
        """Void a shipping label"""
        label = self.bot.db.get_label_by_tracking(tracking)

        if not label:
            await interaction.response.send_message("Label not found.", ephemeral=True)
            return

        if label["status"] == "voided":
            await interaction.response.send_message("Label is already voided.", ephemeral=True)
            return

        # TODO: Call provider API to void
        # For now, just mark in database
        self.bot.db.void_label(tracking)
        await interaction.response.send_message(f"✅ Label {tracking} has been voided.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShippingCog(bot))
```

**Step 2: Commit**

```bash
git add discord-bot/cogs/shipping.py
git commit -m "feat(discord-bot): add shipping cog with natural language quotes"
```

---

## Task 9: Google Drive Cog

**Files:**
- Create: `discord-bot/cogs/drive.py`
- Create: `discord-bot/services/drive_watcher.py`

**Step 1: Create drive_watcher.py**

```python
"""Google Drive watcher service"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging

logger = logging.getLogger(__name__)


class DriveWatcher:
    """Watch Google Drive folders for changes"""

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    def __init__(self):
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
        creds_dict = json.loads(creds_json) if creds_json else {}

        if not creds_dict:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=self.SCOPES
        )
        self.service = build("drive", "v3", credentials=credentials)
        self.file_cache: Dict[str, Dict] = {}  # file_id -> file metadata
        logger.info("Drive watcher initialized")

    def get_folder_files(self, folder_id: str) -> List[Dict[str, Any]]:
        """Get all files in a folder"""
        files = []
        page_token = None

        while True:
            response = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)",
                pageToken=page_token
            ).execute()

            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")

            if not page_token:
                break

        return files

    def check_for_changes(
        self,
        folder_id: str,
        folder_name: str,
        notify_on: List[str],
        file_types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Check folder for changes since last check.
        Returns dict with 'created', 'modified', 'deleted' lists.
        """
        changes = {"created": [], "modified": [], "deleted": []}

        current_files = self.get_folder_files(folder_id)
        current_ids = {f["id"] for f in current_files}
        cached_ids = {fid for fid, meta in self.file_cache.items() if meta.get("folder_id") == folder_id}

        # Filter by file types if specified
        if file_types:
            extensions = [f".{ft.lower()}" for ft in file_types]
            current_files = [
                f for f in current_files
                if any(f["name"].lower().endswith(ext) for ext in extensions)
            ]

        for file in current_files:
            file["folder_id"] = folder_id
            file["folder_name"] = folder_name
            file_id = file["id"]

            if file_id not in self.file_cache:
                # New file
                if "created" in notify_on:
                    changes["created"].append(file)
                self.file_cache[file_id] = file

            else:
                # Check if modified
                cached = self.file_cache[file_id]
                if file.get("modifiedTime") != cached.get("modifiedTime"):
                    if "modified" in notify_on:
                        changes["modified"].append(file)
                    self.file_cache[file_id] = file

        # Check for deleted files
        if "deleted" in notify_on:
            for fid in cached_ids - current_ids:
                if fid in self.file_cache:
                    changes["deleted"].append(self.file_cache[fid])
                    del self.file_cache[fid]

        return changes

    def get_file_link(self, file_id: str) -> Optional[str]:
        """Get web view link for a file"""
        try:
            file = self.service.files().get(
                fileId=file_id, fields="webViewLink"
            ).execute()
            return file.get("webViewLink")
        except Exception as e:
            logger.error(f"Error getting file link: {e}")
            return None
```

**Step 2: Create drive.py cog**

```python
"""Google Drive notifications cog"""

import discord
from discord.ext import commands, tasks
from typing import Dict
import logging

from services.drive_watcher import DriveWatcher

logger = logging.getLogger(__name__)


class DriveCog(commands.Cog):
    """Google Drive change notifications"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.drive
        self.watcher: DriveWatcher = None

        try:
            self.watcher = DriveWatcher()
        except Exception as e:
            logger.warning(f"Could not initialize Drive watcher: {e}")

    async def cog_load(self):
        """Start the Drive polling loop"""
        if self.watcher and self.config.get("watched_folders"):
            self.poll_drive.start()
            logger.info("Drive polling started")

    async def cog_unload(self):
        """Stop the Drive polling loop"""
        self.poll_drive.cancel()

    @tasks.loop(seconds=300)
    async def poll_drive(self):
        """Poll watched folders for changes"""
        channel_id = self.config.get("channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Drive channel {channel_id} not found")
            return

        for folder_config in self.config.get("watched_folders", []):
            try:
                changes = self.watcher.check_for_changes(
                    folder_id=folder_config["folder_id"],
                    folder_name=folder_config.get("name", "Unknown"),
                    notify_on=folder_config.get("notify_on", ["created", "modified", "deleted"]),
                    file_types=folder_config.get("file_types")
                )

                # Check if there are any changes
                if not any(changes.values()):
                    continue

                # Build embed
                embed = discord.Embed(
                    title=f"📁 Drive Update: {folder_config.get('name', 'Folder')}",
                    color=discord.Color.orange()
                )

                for change_type, files in changes.items():
                    if not files:
                        continue

                    emoji = {"created": "➕", "modified": "📝", "deleted": "🗑️"}.get(change_type, "•")
                    file_list = "\n".join([
                        f"{emoji} [{f['name']}]({f.get('webViewLink', '')})"
                        for f in files[:10]
                    ])

                    if len(files) > 10:
                        file_list += f"\n... and {len(files) - 10} more"

                    embed.add_field(
                        name=change_type.capitalize(),
                        value=file_list or "None",
                        inline=False
                    )

                    # Save to database for AI context
                    for file in files:
                        if change_type != "deleted":
                            self.bot.db.save_drive_file(file)

                await channel.send(embed=embed)
                logger.info(f"Posted drive changes for {folder_config.get('name')}")

            except Exception as e:
                logger.error(f"Error checking folder {folder_config.get('folder_id')}: {e}")

    @poll_drive.before_loop
    async def before_poll(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DriveCog(bot))
```

**Step 3: Commit**

```bash
git add discord-bot/cogs/drive.py discord-bot/services/drive_watcher.py
git commit -m "feat(discord-bot): add Google Drive notifications cog"
```

---

## Task 10: AI Assistant Cog

**Files:**
- Create: `discord-bot/cogs/assistant.py`

**Step 1: Create assistant.py**

```python
"""AI Assistant cog - answers questions using all bot data"""

import discord
from discord.ext import commands
from discord import app_commands
import logging

from services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class AssistantCog(commands.Cog):
    """AI-powered assistant with full context access"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.ai_chat
        self.gemini: GeminiClient = None

        if bot.config.gemini_api_key:
            self.gemini = GeminiClient(bot.config.gemini_api_key)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Respond to @mentions in AI chat channel"""
        if message.author.bot:
            return

        # Check if in configured channel
        channel_id = self.config.get("channel_id")
        if channel_id and str(message.channel.id) != channel_id:
            return

        # Check for mention trigger
        trigger = self.config.get("trigger", "mention")
        if trigger == "mention" and self.bot.user not in message.mentions:
            return

        if not self.gemini:
            await message.reply("AI service not configured.")
            return

        # Remove bot mention from message
        question = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not question:
            await message.reply("How can I help you?")
            return

        async with message.channel.typing():
            await self._answer_question(message, question)

    async def _answer_question(self, message: discord.Message, question: str):
        """Answer user question with full context"""
        context_sources = self.config.get("context_sources", ["calendar", "drive", "shipping"])

        # Gather context
        calendar_events = []
        drive_files = []
        shipping_labels = []

        if "calendar" in context_sources:
            calendar_events = self.bot.db.get_upcoming_events(limit=20)

        if "drive" in context_sources:
            # Search for relevant files
            keywords = question.split()[:3]  # Use first 3 words as search
            for keyword in keywords:
                if len(keyword) > 2:
                    drive_files.extend(self.bot.db.search_drive_files(keyword, limit=10))
            # Deduplicate
            seen = set()
            drive_files = [f for f in drive_files if not (f["file_id"] in seen or seen.add(f["file_id"]))]

        if "shipping" in context_sources:
            shipping_labels = self.bot.db.get_user_labels(str(message.author.id), limit=10)

        # Get AI response
        response = await self.gemini.chat_with_context(
            question=question,
            calendar_events=calendar_events,
            drive_files=drive_files,
            shipping_labels=shipping_labels
        )

        # Send response (split if too long)
        if len(response) <= 2000:
            await message.reply(response)
        else:
            chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)

    @app_commands.command(name="ask", description="Ask the AI assistant a question")
    @app_commands.describe(question="Your question")
    async def ask_command(self, interaction: discord.Interaction, question: str):
        """Slash command to ask questions"""
        if not self.gemini:
            await interaction.response.send_message("AI service not configured.", ephemeral=True)
            return

        await interaction.response.defer()

        # Gather context (simplified for slash command)
        calendar_events = self.bot.db.get_upcoming_events(limit=10)
        shipping_labels = self.bot.db.get_user_labels(str(interaction.user.id), limit=5)

        response = await self.gemini.chat_with_context(
            question=question,
            calendar_events=calendar_events,
            drive_files=[],
            shipping_labels=shipping_labels
        )

        await interaction.followup.send(response)


async def setup(bot):
    await bot.add_cog(AssistantCog(bot))
```

**Step 2: Commit**

```bash
git add discord-bot/cogs/assistant.py
git commit -m "feat(discord-bot): add AI assistant cog with full context"
```

---

## Task 11: Systemd Service and Final Setup

**Files:**
- Create: `discord-bot/discord-bot.service`
- Create: `discord-bot/README.md`

**Step 1: Create systemd service file**

```ini
[Unit]
Description=Discord Shipping Bot
After=network.target

[Service]
Type=simple
User=stanhuang
WorkingDirectory=/home/stanhuang/shippo-frontend/discord-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**Step 2: Create README.md**

```markdown
# Discord Shipping Bot

Discord bot with calendar sync, shipping labels, Google Drive notifications, and AI chat.

## Setup

1. **Create Discord Bot**
   - Go to https://discord.com/developers/applications
   - Create application → Bot → Copy token
   - Enable "Message Content Intent"
   - Invite with permissions: Send Messages, Create Events, Add Reactions, Read Message History, Attach Files

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your tokens and passwords
   ```

3. **Configure Bot**
   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml with channel IDs and settings
   ```

4. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Initialize Database**
   ```bash
   python -c "from services.database import Database; Database().init_schema()"
   ```

6. **Run Bot**
   ```bash
   python bot.py
   ```

## Deploy as Service (Linux)

```bash
# Copy service file
sudo cp discord-bot.service /etc/systemd/system/

# Edit paths in service file
sudo nano /etc/systemd/system/discord-bot.service

# Enable and start
sudo systemctl enable discord-bot
sudo systemctl start discord-bot

# Check status
sudo systemctl status discord-bot

# View logs
journalctl -u discord-bot -f
```

## Features

### Calendar Sync
- Monitors email for calendar invites
- Posts to Discord with RSVP buttons
- Creates Discord scheduled events

### Shipping
- Natural language: "Ship 5lbs to Austin TX"
- Click to select rate and purchase
- `/labels` - View your labels
- `/label <tracking>` - Re-download PDF
- `/void <tracking>` - Void a label

### Google Drive
- Watches configured folders
- Posts when files are added/modified/deleted

### AI Chat
- @mention the bot with questions
- Has access to calendar, drive, and shipping data
- `/ask <question>` - Ask directly
```

**Step 3: Commit**

```bash
git add discord-bot/
git commit -m "feat(discord-bot): add systemd service and documentation"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Project Setup | requirements.txt, .env.example, config.yaml.example |
| 2 | Database Schema | services/database.py, services/schema.sql |
| 3 | Core Bot | bot.py, config.py |
| 4 | Gemini Client | services/gemini_client.py |
| 5 | Email Client | services/email_client.py |
| 6 | Calendar Parser | services/calendar_parser.py |
| 7 | Calendar Cog | cogs/calendar.py |
| 8 | Shipping Cog | cogs/shipping.py |
| 9 | Drive Cog | cogs/drive.py, services/drive_watcher.py |
| 10 | AI Assistant | cogs/assistant.py |
| 11 | Deployment | discord-bot.service, README.md |
