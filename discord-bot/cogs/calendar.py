"""Calendar sync cog - monitors email and posts events to Discord"""

import discord
from discord.ext import commands, tasks
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
        # Track last UID per account+folder combo (e.g. "gao@x.com:INBOX")
        self.last_uids: Dict[str, int] = {}
        self.poll_folders = ["INBOX", "Sent"]

        # Initialize email clients
        for account in self.config.get("accounts", []):
            email_addr = account.get("email")
            if not email_addr:
                continue
            password = bot.config.get_email_password(account.get("password_env", ""))
            if password:
                self.email_clients[email_addr] = EmailClient(
                    email_address=email_addr,
                    password=password,
                    imap_host=account.get("imap_host", "imap.purelymail.com"),
                    smtp_host=account.get("smtp_host", "smtp.purelymail.com"),
                    imap_port=account.get("imap_port", 993),
                    smtp_port=account.get("smtp_port", 587)
                )
                for folder in self.poll_folders:
                    self.last_uids[f"{email_addr}:{folder}"] = 0
                logger.info(f"Initialized email client for {email_addr} (folders: {self.poll_folders})")

        # Initialize Gemini for plain text parsing
        if bot.config.gemini_api_key:
            try:
                self.gemini = GeminiClient(bot.config.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    async def cog_load(self):
        """Start the email polling loop"""
        if self.email_clients:
            interval = self.config.get("poll_interval_seconds", 60)
            self.poll_emails.change_interval(seconds=interval)
            self.poll_emails.start()
            logger.info(f"Calendar email polling started (interval: {interval}s)")

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
          for folder in self.poll_folders:
            uid_key = f"{email_addr}:{folder}"
            try:
                emails = client.fetch_new_emails(
                    folder=folder,
                    since_uid=self.last_uids.get(uid_key)
                )

                if not emails:
                    logger.info(f"No new emails for {email_addr}/{folder} (last_uid={self.last_uids.get(uid_key, 0)})")

                for email_dict in emails:
                    # Update last seen UID
                    uid = email_dict.get("uid", 0)
                    if uid > self.last_uids.get(uid_key, 0):
                        self.last_uids[uid_key] = uid

                    if not self.parser.is_calendar_email(email_dict):
                        continue

                    logger.info(
                        f"Calendar email detected in {folder} uid={uid} "
                        f"subject='{email_dict.get('subject', '')}'"
                    )

                    # Try to parse ICS attachment first
                    events = []
                    ics_files = client.get_ics_attachments(email_dict)
                    for ics_content in ics_files:
                        events.extend(self.parser.parse_ics(ics_content))

                    # If no ICS, try parsing email body with Gemini
                    if not events and self.gemini:
                        body = email_dict.get("body", "")
                        if body:
                            parsed = await self.gemini.parse_calendar_text(body)
                            if parsed and parsed.get("title"):
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
                logger.error(f"Error polling {email_addr}/{folder}: {e}")

    @poll_emails.before_loop
    async def before_poll(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()

    async def _post_event(self, channel, event: Dict, email_dict: Dict):
        """Post event to Discord and create scheduled event"""
        # Check if this event was already posted (by event_uid)
        event_uid = event.get("uid")
        if event_uid:
            existing = self.bot.db.get_event_by_uid(event_uid)
            if existing and existing.get("discord_message_id"):
                # Retry scheduled event creation if it failed previously
                if not existing.get("discord_event_id"):
                    await self._retry_scheduled_event(channel, event, existing["id"])
                logger.info(f"Skipping already-posted event: {event.get('title')} (uid: {event_uid})")
                return

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
            desc = event["description"]
            if len(desc) > 500:
                desc = desc[:500] + "..."
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
                end_time = event.get("end_time")
                if not end_time or not isinstance(end_time, datetime):
                    end_time = start_time + timedelta(hours=1)

                location_str = event.get("meeting_link") or event.get("location") or "TBD"

                scheduled_event = await guild.create_scheduled_event(
                    name=event.get("title", "Event")[:100],
                    start_time=start_time,
                    end_time=end_time,
                    location=location_str[:100],
                    entity_type=discord.EntityType.external,
                    privacy_level=discord.PrivacyLevel.guild_only
                )
                discord_event_id = str(scheduled_event.id)
                logger.info(f"Created Discord event: {discord_event_id}")
            except Exception as e:
                logger.warning(f"Could not create Discord scheduled event: {e}")

        # Update database with Discord IDs
        self.bot.db.update_event_discord_ids(
            event_id,
            discord_event_id or "",
            str(message.id)
        )

        logger.info(f"Posted calendar event: {event.get('title')}")

    async def _retry_scheduled_event(self, channel, event: Dict, event_id: int):
        """Retry creating a Discord scheduled event for an already-posted event"""
        start_time = event.get("start_time")
        if not start_time or not isinstance(start_time, datetime):
            return

        try:
            guild = channel.guild
            end_time = event.get("end_time")
            if not end_time or not isinstance(end_time, datetime):
                end_time = start_time + timedelta(hours=1)

            location_str = event.get("meeting_link") or event.get("location") or "TBD"

            scheduled_event = await guild.create_scheduled_event(
                name=event.get("title", "Event")[:100],
                start_time=start_time,
                end_time=end_time,
                location=location_str[:100],
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only
            )
            self.bot.db.update_event_discord_ids(event_id, str(scheduled_event.id), "")
            logger.info(f"Retried scheduled event creation: {scheduled_event.id}")
        except Exception as e:
            logger.warning(f"Retry scheduled event failed: {e}")

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
        except ValueError as e:
            logger.warning(f"Failed to parse datetime: {date_str} {time_str}: {e}")
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
        if not response:
            return

        # Look up event by message ID
        event = self.bot.db.get_event_by_message_id(str(payload.message_id))
        if not event:
            return

        # Get user info
        user = self.bot.get_user(payload.user_id)
        username = user.display_name if user else f"User {payload.user_id}"

        # Save RSVP to database
        self.bot.db.save_rsvp(event["id"], str(payload.user_id), username, response)
        logger.info(f"RSVP: {username} responded '{response}' to event '{event.get('title')}'")

        # TODO: Send RSVP email to organizer (optional, could be enabled via config)


async def setup(bot):
    await bot.add_cog(CalendarCog(bot))
