"""Google Drive notifications cog"""

import discord
from discord.ext import commands, tasks
import logging

from services.drive_watcher import DriveWatcher

logger = logging.getLogger(__name__)


class DriveCog(commands.Cog):
    """Google Drive change notifications"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.drive
        self.watcher = None

        try:
            self.watcher = DriveWatcher()
        except Exception as e:
            logger.warning(f"Could not initialize Drive watcher: {e}")

    async def cog_load(self):
        """Start the Drive polling loop"""
        if self.watcher and self.config.get("watched_folders"):
            # Seed cache from database to avoid duplicate notifications on restart
            try:
                db_files = self.bot.db.get_all_drive_files(limit=10000)
                self.watcher.seed_cache_from_db(db_files)
            except Exception as e:
                logger.warning(f"Could not seed drive cache from database: {e}")

            interval = self.config.get("poll_interval_seconds", 300)
            self.poll_drive.change_interval(seconds=interval)
            self.poll_drive.start()
            logger.info(f"Drive polling started (interval: {interval}s)")

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
            folder_id = folder_config.get("folder_id")
            if not folder_id:
                continue

            try:
                changes = self.watcher.check_for_changes(
                    folder_id=folder_id,
                    folder_name=folder_config.get("name", "Unknown"),
                    notify_on=folder_config.get("notify_on", ["created", "modified", "deleted"]),
                    file_types=folder_config.get("file_types")
                )

                # Save initial files to DB on first scan so restarts have a baseline
                initial_files = changes.pop("_initial_files", None)
                if initial_files:
                    for file in initial_files:
                        try:
                            self.bot.db.save_drive_file(file)
                        except Exception as e:
                            logger.warning(f"Could not save initial drive file to db: {e}")
                    logger.info(f"Saved {len(initial_files)} initial files to DB for {folder_config.get('name')}")

                # Check if there are any changes
                if not any(changes.values()):
                    continue

                # Build embed
                embed = discord.Embed(
                    title=f"Drive Update: {folder_config.get('name', 'Folder')}",
                    color=discord.Color.orange()
                )

                for change_type, files in changes.items():
                    if not files:
                        continue

                    emoji = {"created": "+", "modified": "*", "deleted": "-"}.get(change_type, "-")

                    file_lines = []
                    for f in files[:10]:
                        link = f.get('webViewLink', '')
                        name = f.get('name', 'Unknown')
                        if link:
                            file_lines.append(f"{emoji} [{name}]({link})")
                        else:
                            file_lines.append(f"{emoji} {name}")

                    file_list = "\n".join(file_lines)

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
                            try:
                                self.bot.db.save_drive_file(file)
                            except Exception as e:
                                logger.warning(f"Could not save drive file to db: {e}")

                await channel.send(embed=embed)
                logger.info(f"Posted drive changes for {folder_config.get('name')}")

            except Exception as e:
                logger.error(f"Error checking folder {folder_id}: {e}")

    @poll_drive.before_loop
    async def before_poll(self):
        """Wait for bot to be ready"""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DriveCog(bot))
