import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path
import shutil
import traceback
import json
from datetime import datetime

from utils.storage_utils import Storage
from utils.excel_utils import get_user_excel_path

# --- Persistent storage ---
storage = Storage("data/users.json")

# --- Load config ---
with open("config.json", "r") as f:
    CONFIG = json.load(f)

GUILD_ID = int(CONFIG.get("GUILD_ID"))
ADMIN_LOG_CHANNEL_ID = int(
    CONFIG.get("ADMIN_CHANNEL_ID") or CONFIG.get("admin_log_channel_id") or 0)

# --- Paths ---
REPORTS_DIR = Path("data/reports")
ARCHIVE_DIR = Path("data/archive")
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


class UserCommandsCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild = discord.Object(id=GUILD_ID)

    # ---------- Utility helpers ----------
    def _user_row(self, discord_id: str):
        """
        Return tuple (user_id, channel_id, username, replies_per_day, start_date, status)
        or None if not present.
        """
        return storage.get_user_by_discord_id(str(discord_id))

    async def _send_admin_log(self, message: str, file_path: Path = None):
        try:
            ch = self.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
            if ch:
                await ch.send(message)
                if file_path and file_path.exists():
                    await ch.send(file=discord.File(file_path))
        except Exception:
            print("⚠️ Failed to send admin log:")
            traceback.print_exc()

    # ---------- /myreport ----------
    @app_commands.command(
        name="myreport",
        description="Download your current tracking Excel file")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def myreport(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        row = self._user_row(str(interaction.user.id))
        if not row:
            return await interaction.followup.send(
                "⚠️ You are not set up for tracking.", ephemeral=True)

        # Unpack safely (should be 6 items)
        try:
            _, _, username, _, _, _ = row
        except Exception:
            return await interaction.followup.send(
                "⚠️ Internal error: user data malformed.", ephemeral=True)

        path = get_user_excel_path(username) if username else None
        if not path or not path.exists():
            return await interaction.followup.send(
                "⚠️ Your Excel file was not found.", ephemeral=True)

        try:
            await interaction.followup.send(file=discord.File(str(path)),
                                            ephemeral=True)
            await self._send_admin_log(
                f"📥 {interaction.user.mention} requested their report ({username})."
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Failed to send file: {e}",
                                            ephemeral=True)
            await self._send_admin_log(
                f"⚠️ Failed to send Excel to {interaction.user.mention}: {e}")

    # ---------- /pause ----------
    @app_commands.command(name="pause",
                          description="Pause your tracking (vacation mode)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def pause(self, interaction: discord.Interaction):
        row = self._user_row(str(interaction.user.id))
        if not row:
            return await interaction.response.send_message(
                "⚠️ You are not set up for tracking.", ephemeral=True)

        user_id, channel_id, username, replies_per_day, start_date, _ = row
        storage.set_user(discord_id=str(user_id),
                         channel_id=str(channel_id),
                         username=username,
                         replies_per_day=replies_per_day,
                         start_date=start_date,
                         status="paused")
        await interaction.response.send_message(
            "⏸️ Your tracking has been paused. Use `/resume` to continue.",
            ephemeral=True)
        await self._send_admin_log(
            f"⏸️ {interaction.user.mention} paused tracking for `{username}`.")

    # ---------- /resume ----------
    @app_commands.command(name="resume", description="Resume your tracking")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def resume(self, interaction: discord.Interaction):
        row = self._user_row(str(interaction.user.id))
        if not row:
            return await interaction.response.send_message(
                "⚠️ You are not set up for tracking.", ephemeral=True)

        user_id, channel_id, username, replies_per_day, start_date, _ = row
        storage.set_user(discord_id=str(user_id),
                         channel_id=str(channel_id),
                         username=username,
                         replies_per_day=replies_per_day,
                         start_date=start_date,
                         status="active")
        await interaction.response.send_message(
            "▶️ Your tracking has been resumed.", ephemeral=True)
        await self._send_admin_log(
            f"▶️ {interaction.user.mention} resumed tracking for `{username}`."
        )

    # ---------- /settarget ----------
    @app_commands.command(name="settarget",
                          description="Change your daily replies target")
    @app_commands.describe(replies_per_day="New replies per day (must be > 0)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def settarget(self, interaction: discord.Interaction,
                        replies_per_day: int):
        if replies_per_day <= 0:
            return await interaction.response.send_message(
                "Replies per day must be a positive integer.", ephemeral=True)

        row = self._user_row(str(interaction.user.id))
        if not row:
            return await interaction.response.send_message(
                "⚠️ You are not set up for tracking.", ephemeral=True)

        user_id, _, username, old_replies, _, _ = row
        storage.update_replies_per_day(str(user_id), int(replies_per_day))

        await interaction.response.send_message(
            f"✅ Your target is now set to **{replies_per_day}** replies/day.",
            ephemeral=True)
        await self._send_admin_log(
            f"🔁 {interaction.user.mention} changed target for `{username}`: {old_replies} -> {replies_per_day}"
        )

    # ---------- /stop ----------
    @app_commands.command(
        name="stop",
        description=
        "Stop tracking permanently (archive your Excel & remove mapping)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def stop(self, interaction: discord.Interaction):
        row = self._user_row(str(interaction.user.id))
        if not row:
            return await interaction.response.send_message(
                "⚠️ You are not set up for tracking.", ephemeral=True)

        user_id, _, username, _, _, _ = row

        archived_path = None
        try:
            path = get_user_excel_path(username) if username else None
            if path and path.exists():
                stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                dest = ARCHIVE_DIR / f"{username}-{stamp}.xlsx"
                shutil.move(str(path), str(dest))
                archived_path = dest
        except Exception as e:
            await self._send_admin_log(
                f"⚠️ Failed to archive Excel for {interaction.user.mention} ({username}): {e}"
            )

        storage.remove_user(str(user_id))

        await interaction.response.send_message(
            "🛑 You have been removed from tracking. Your final report has been archived.",
            ephemeral=True)

        msg = f"🛑 {interaction.user.mention} stopped tracking for `{username}`."
        if archived_path:
            msg += " Final report attached."
        await self._send_admin_log(msg, file_path=archived_path)

    # ---------- /whoami_tracking ----------
    @app_commands.command(
        name="whoami_tracking",
        description="[admin] Show tracking mapping for a user")
    @app_commands.describe(target="Target user (mention)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def whoami_tracking(self,
                              interaction: discord.Interaction,
                              target: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.",
                                                           ephemeral=True)

        if target:
            row = storage.get_user_by_discord_id(str(target.id))
            if not row:
                return await interaction.response.send_message(
                    f"No mapping for {target.mention}", ephemeral=True)
            user_id, ch_id, username, replies_per_day, start_date, status = row
            return await interaction.response.send_message(
                f"User {target.mention}: username={username}, channel_id={ch_id}, replies/day={replies_per_day}, start_date={start_date}, status={status}",
                ephemeral=True)
        else:
            users = storage.list_users()
            return await interaction.response.send_message(
                f"Total tracked users: {len(users)} (use target to query one).",
                ephemeral=True)


async def setup(bot: commands.Bot):
    cog = UserCommandsCog(bot)
    await bot.add_cog(cog)
