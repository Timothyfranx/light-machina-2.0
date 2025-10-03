"""
Cleanup Cog (scheduled)

Every CLEANUP_HOURS (config) this cog:
- Reads tracked users from storage
- For each user, checks whether they still have the configured ROLE in the configured GUILD
- If user no longer has role or has left: archives their Excel to admin log channel,
  deletes their private channel if it exists, and removes them from storage

Also exposes an admin-only text command `!cleanup_now` for manual runs.
"""

import discord
from discord.ext import commands, tasks
from pathlib import Path
import json
import shutil
from datetime import datetime
import traceback

from utils.storage_utils import Storage
from utils.excel_utils import get_user_excel_path

storage = Storage("data/users.json")

with open("config.json", "r") as f:
    CFG = json.load(f)

GUILD_ID = int(CFG.get("GUILD_ID") or CFG.get("guild_id"))
ROLE_ID = int(CFG.get("TRACKED_ROLE_ID") or CFG.get("role_id") or CFG.get("ROLE") or CFG.get("reply_guy_role_id") or CFG.get("ROLE_ID"))
CATEGORY_ID = int(CFG.get("CATEGORY_ID") or CFG.get("category_id") or CFG.get("CATEGORY"))
ADMIN_LOG_CHANNEL = int(CFG.get("ADMIN_CHANNEL_ID") or CFG.get("admin_log_channel") or CFG.get("admin_log_channel_id") or CFG.get("ADMIN_LOG_CHANNEL_ID"))
CLEANUP_HOURS = int(CFG.get("CLEANUP_HOURS") or CFG.get("cleanup_hours") or 6)

ARCHIVE_DIR = Path("data/archive")
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


class CleanupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # start the periodic loop
        self.cleanup_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()

    async def archive_and_notify(self, guild: discord.Guild, user_id: str, username: str, channel_id: str):
        """
        Archive user's Excel and notify admin channel.
        Returns True if archived successfully.
        """
        try:
            p = get_user_excel_path(username) if username else None
            if p and p.exists():
                stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                dest = ARCHIVE_DIR / f"{username}-{stamp}.xlsx"
                shutil.copy2(p, dest)
                # send to admin log channel
                ch = guild.get_channel(ADMIN_LOG_CHANNEL)
                if ch:
                    await ch.send(f"📤 Archived final report for <@{user_id}> (user lost role / left).", file=discord.File(dest))
                return True
        except Exception as e:
            # log but continue
            try:
                if hasattr(self.bot, "log_event"):
                    await self.bot.log_event(f"⚠️ Failed to archive Excel for user {user_id}: {e}")
            except Exception:
                pass
        return False

    @tasks.loop(hours=CLEANUP_HOURS)
    async def cleanup_loop(self):
        # wait until ready
        await self.bot.wait_until_ready()
        try:
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                if hasattr(self.bot, "log_event"):
                    await self.bot.log_event("⚠️ Cleanup: configured guild not found")
                return

            role = guild.get_role(ROLE_ID)
            users = storage.list_users()
            to_remove = []

            for (user_id, ch_id, username, replies_per_day, start_date, status) in users:
                member = guild.get_member(int(user_id))
                has_role = False
                if member and role:
                    has_role = role in member.roles

                if not member or not has_role:
                    # Archive Excel & notify admin
                    await self.archive_and_notify(guild, user_id, username, ch_id)

                    # Delete channel if exists
                    try:
                        ch_obj = guild.get_channel(int(ch_id))
                        if ch_obj:
                            await ch_obj.delete(reason="User lost role or left server - cleanup")
                    except Exception:
                        pass

                    to_remove.append(user_id)

            # remove entries from storage
            if to_remove:
                for uid in to_remove:
                    storage.remove_user(uid)
                if hasattr(self.bot, "log_event"):
                    await self.bot.log_event(f"🧹 Cleanup removed {len(to_remove)} user(s).")
        except Exception as ex:
            # global error logging
            tb = traceback.format_exc()
            try:
                if hasattr(self.bot, "log_event"):
                    await self.bot.log_event(f"🔥 Cleanup error: {tb}")
            except Exception:
                pass

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    # Manual trigger (admin-only command)
    @commands.command(name="cleanup_now")
    @commands.has_permissions(administrator=True)
    async def cleanup_now(self, ctx):
        """Run cleanup immediately (admin-only)."""
        await ctx.send("🧹 Running cleanup now...")
        await self.cleanup_loop.coro()
        await ctx.send("✅ Cleanup complete.")


async def setup(bot):
    await bot.add_cog(CleanupCog(bot))