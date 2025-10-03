import discord
from discord import app_commands
from discord.ext import commands
import json
from datetime import datetime, timedelta
from pathlib import Path

from utils.storage_utils import Storage
from utils import excel_utils

storage = Storage("data/users.json")


class SetupCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        with open("config.json", "r") as f:
            self.config = json.load(f)

        self.guild_id = int(self.config["GUILD_ID"])
        self.role_id = int(self.config["TRACKED_ROLE_ID"])
        self.category_id = int(self.config["CATEGORY_ID"])
        self.admin_channel_id = int(self.config["ADMIN_CHANNEL_ID"])
        self.admin_role_id = int(self.config["ADMIN_ROLE_ID"])

    async def create_user_channel(self, member: discord.Member):
        category = member.guild.get_channel(self.category_id)
        if not category:
            raise RuntimeError("Category not found")

        overwrites = {
            member.guild.default_role:
            discord.PermissionOverwrite(view_channel=False),
            member:
            discord.PermissionOverwrite(view_channel=True,
                                        send_messages=True,
                                        read_message_history=True),
            member.guild.me:
            discord.PermissionOverwrite(view_channel=True, send_messages=True),
            member.guild.get_role(self.admin_role_id):
            discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        return await category.create_text_channel(
            name=f"{member.name}-replies", overwrites=overwrites)

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return

        role = guild.get_role(self.role_id)
        if not role:
            return

        for member in role.members:
            user_data = storage.get_user(str(member.id))
            existing_channel = discord.utils.get(guild.text_channels,
                                                 name=f"{member.name}-replies")

            if user_data and existing_channel and str(
                    user_data.get("channel_id")) == str(existing_channel.id):
                continue  # Already set up

            if existing_channel:
                storage.add_user(str(member.id),
                                 str(existing_channel.id),
                                 member.display_name,
                                 0,
                                 status="pending")
                await existing_channel.send(
                    f"👋 Hi {member.mention}, we detected you already had this channel.\n"
                    f"Please provide: `username, targetReplies, YYYY-MM-DD`\n"
                    f"Example: `elonmusk, 5, 2025-06-08`\n"
                    f"drop your links immediately")
                continue

            channel = await self.create_user_channel(member)
            storage.add_user(str(member.id),
                             str(channel.id),
                             member.display_name,
                             0,
                             status="pending")
            await channel.send(
                f"👋 Hi {member.mention}, we set you up automatically.\n"
                f"Please provide: `username, targetReplies, YYYY-MM-DD`\n"
                f"Example: `elonmusk, 5, 2025-06-08`\n"
                f"drop your links immediately")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        role = after.guild.get_role(self.role_id)
        if role not in before.roles and role in after.roles:
            channel = await self.create_user_channel(after)
            storage.add_user(str(after.id),
                             str(channel.id),
                             after.display_name,
                             0,
                             status="pending")
            await channel.send(
                f"👋 Hi {after.mention}, welcome!\n"
                f"Please set up your tracking with the following format:\n"
                f"`username, targetReplies, YYYY-MM-DD`\n"
                f"Example: `elonmusk, 5, 2025-06-08`\n"
                f"drop your links immediately")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        known_channels = [ch for _, ch, *_ in storage.list_users()]
        if str(message.channel.id) not in [str(c) for c in known_channels]:
            return

        user_id = str(message.author.id)
        user_data = storage.get_user(user_id)

        if user_data and user_data.get("status") == "active":
            return  # Already set up

        try:
            parts = [p.strip() for p in message.content.split(",")]
            username, target, start_date = parts[0], int(parts[1]), parts[2]
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = start_date + timedelta(days=60)

            storage.set_user(discord_id=user_id,
                             channel_id=str(message.channel.id),
                             username=username,
                             replies_per_day=int(target),
                             status="active",
                             start_date=start_date.isoformat())

            excel_utils.create_user_excel(user_id, username, start_date,
                                          end_date, int(target))
            await message.channel.send(
                f"✅ Setup complete for **{username}**.\n"
                f"Tracking from **{start_date} → {end_date}** with **{target} replies/day**."
            )

        except Exception:
            await message.channel.send(
                "⚠️ Invalid format! Please use: `username, targetReplies, YYYY-MM-DD`"
            )

    @app_commands.command(
        name="setupuser",
        description="Admin: manually set up a user if the bot missed them")
    @app_commands.guilds(discord.Object(id=1418568586741551187))
    @app_commands.checks.has_permissions(administrator=True)
    async def setupuser(self,
                        interaction: discord.Interaction,
                        member: discord.Member,
                        target: int = 5):
        role = interaction.guild.get_role(self.role_id)
        if role not in member.roles:
            return await interaction.response.send_message(
                "⚠️ That user doesn’t have the tracked role.", ephemeral=True)

        existing_channel = discord.utils.get(interaction.guild.text_channels,
                                             name=f"{member.name}-replies")
        if existing_channel:
            ch = existing_channel
        else:
            ch = await self.create_user_channel(member)

        start_date = datetime.utcnow().date()
        end_date = start_date + timedelta(days=60)

        storage.add_user(str(member.id),
                         str(ch.id),
                         member.display_name,
                         int(target),
                         status="active",
                         start_date=start_date.isoformat())

        excel_utils.create_user_excel(str(member.id), member.display_name,
                                      start_date, end_date, int(target))

        await ch.send(
            f"👋 Hi {member.mention}, you’ve been manually set up by an admin.\n"
            f"Please provide: `username, targetReplies, YYYY-MM-DD` if you want a different username/start date."
        )
        await interaction.response.send_message(
            f"✅ Channel created for {member.mention} → {ch.mention}",
            ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
