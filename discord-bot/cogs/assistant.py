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
        self.gemini = None

        if bot.config.gemini_api_key:
            try:
                self.gemini = GeminiClient(bot.config.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Respond to @mentions in AI chat channel"""
        # Ignore all bot messages (including our own)
        if message.author.bot:
            return

        # Ignore if this is a reply to a bot message (prevents loops)
        if message.reference and message.reference.resolved:
            if hasattr(message.reference.resolved, 'author') and message.reference.resolved.author.bot:
                return

        # Check if in configured channel
        channel_id = self.config.get("channel_id")
        in_ai_channel = channel_id and str(message.channel.id) == str(channel_id)

        # Must be mentioned to trigger
        trigger = self.config.get("trigger", "mention")
        is_mentioned = self.bot.user in message.mentions

        # Only respond if: in AI channel AND mentioned, OR mentioned anywhere
        if trigger == "mention" and not is_mentioned:
            return

        if not in_ai_channel and not is_mentioned:
            return

        logger.info(f"AI chat triggered by {message.author} in channel {message.channel.id}")

        if not self.gemini:
            await message.reply("AI service not configured.")
            return

        # Remove bot mention from message
        question = message.content
        for mention in [f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"]:
            question = question.replace(mention, "")
        question = question.strip()

        if not question:
            await message.reply("How can I help you? Ask me about upcoming events, shipping labels, or files.")
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

        try:
            if "calendar" in context_sources:
                calendar_events = self.bot.db.get_upcoming_events(limit=20)

            if "drive" in context_sources:
                # Search for relevant files based on keywords in question
                keywords = [word for word in question.split() if len(word) > 2]
                for keyword in keywords[:5]:
                    try:
                        results = self.bot.db.search_drive_files(keyword, limit=5)
                        drive_files.extend(results)
                    except Exception:
                        pass

                # Also get recent files
                try:
                    recent_files = self.bot.db.get_all_drive_files(limit=10)
                    drive_files.extend(recent_files)
                except Exception:
                    pass

                # Deduplicate
                seen = set()
                unique_files = []
                for f in drive_files:
                    fid = f.get("file_id")
                    if fid and fid not in seen:
                        seen.add(fid)
                        unique_files.append(f)
                drive_files = unique_files[:20]

            if "shipping" in context_sources:
                # Get user's labels and recent labels
                user_labels = self.bot.db.get_user_labels(str(message.author.id), limit=10)
                recent_labels = self.bot.db.get_recent_labels(limit=5)

                # Combine and deduplicate
                seen = set()
                shipping_labels = []
                for l in user_labels + recent_labels:
                    tn = l.get("tracking_number")
                    if tn and tn not in seen:
                        seen.add(tn)
                        shipping_labels.append(l)
                shipping_labels = shipping_labels[:15]

        except Exception as e:
            logger.error(f"Error gathering context: {e}")

        # Get AI response
        try:
            response = await self.gemini.chat_with_context(
                question=question,
                calendar_events=calendar_events,
                drive_files=drive_files,
                shipping_labels=shipping_labels
            )
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            response = "Sorry, I encountered an error processing your question. Please try again."

        # Send response (split if too long)
        if len(response) <= 2000:
            await message.reply(response)
        else:
            # Split into chunks
            chunks = []
            current_chunk = ""
            for line in response.split("\n"):
                if len(current_chunk) + len(line) + 1 > 1900:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk += "\n" + line if current_chunk else line
            if current_chunk:
                chunks.append(current_chunk)

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

        context_sources = self.config.get("context_sources", ["calendar", "drive", "shipping"])

        # Gather context
        calendar_events = []
        drive_files = []
        shipping_labels = []

        try:
            if "calendar" in context_sources:
                calendar_events = self.bot.db.get_upcoming_events(limit=10)

            if "drive" in context_sources:
                drive_files = self.bot.db.get_all_drive_files(limit=20)

            if "shipping" in context_sources:
                shipping_labels = self.bot.db.get_user_labels(str(interaction.user.id), limit=10)
        except Exception as e:
            logger.error(f"Error gathering context for /ask: {e}")

        try:
            response = await self.gemini.chat_with_context(
                question=question,
                calendar_events=calendar_events,
                drive_files=drive_files,
                shipping_labels=shipping_labels
            )
        except Exception as e:
            logger.error(f"Gemini error in /ask: {e}")
            response = "Sorry, I encountered an error. Please try again."

        # Truncate if needed
        if len(response) > 2000:
            response = response[:1997] + "..."

        await interaction.followup.send(response)


async def setup(bot):
    await bot.add_cog(AssistantCog(bot))
