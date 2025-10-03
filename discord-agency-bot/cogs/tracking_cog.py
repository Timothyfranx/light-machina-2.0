import discord
from discord.ext import commands
import re
from datetime import datetime, timedelta
import json
from pathlib import Path

from utils.storage_utils import Storage
from utils import excel_utils
from utils.excel_utils import _sanitize_filename  # ✅ use for consistent file names

X_LINK_REGEX = r"(https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status/[0-9]+)"

storage = Storage("data/users.json")


class TrackingCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        with open("config.json", "r") as f:
            self.config = json.load(f)

        self.admin_channel_id = int(self.config.get("ADMIN_CHANNEL_ID", 0))
        self.guild_id = int(self.config.get("GUILD_ID"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        user_id = str(message.author.id)
        user_data = storage.get_user(user_id)

        # Only track if user is registered + active
        if not user_data or user_data.get("status") != "active":
            return

        if str(message.channel.id) != str(user_data.get("channel_id")):
            return  # Ignore messages in unrelated channels

        # Track links
        links = re.findall(X_LINK_REGEX, message.content)
        if not links:
            return

        links = links[:50]  # safety cap
        today = datetime.utcnow().date()
        admin_channel = self.bot.get_channel(
            self.admin_channel_id) if self.admin_channel_id else None

        try:
            username = user_data.get("username") or f"user_{user_id}"
            safe_username = _sanitize_filename(username)  # ✅ always sanitize
            excel_path = Path(f"data/reports/{safe_username}.xlsx")

            # Auto-create excel if missing
            if not excel_path.exists():
                start_date = datetime.utcnow().date()
                end_date = start_date + timedelta(days=60)
                excel_utils.create_user_excel(
                    user_id, safe_username, start_date, end_date,
                    int(user_data.get("replies_per_day", 5)))

            excel_utils.record_links(safe_username, today,
                                     links)  # ✅ use safe_username
            await message.add_reaction("✅")

            if admin_channel:
                await admin_channel.send(
                    f"📝 {message.author.mention} logged **{len(links)}** link(s) on {today}."
                )

        except Exception as e:
            try:
                await message.add_reaction("⚠️")
            except Exception:
                pass
            if admin_channel:
                await admin_channel.send(
                    f"⚠️ Error recording links for {message.author.mention}: {e}"
                )
            print(f"⚠️ TrackingCog error: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
