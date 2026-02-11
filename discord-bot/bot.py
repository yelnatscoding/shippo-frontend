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
