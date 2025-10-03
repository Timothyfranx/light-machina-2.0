import discord
from discord.ext import commands
import traceback
import json
from typing import Optional


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Load config once
        with open("config.json", "r") as f:
            cfg = json.load(f)
        self.admin_channel_id: Optional[int] = cfg.get("ADMIN_CHANNEL_ID")

    # Utility: resolve admin channel
    async def _get_admin_channel(self) -> Optional[discord.TextChannel]:
        if not self.admin_channel_id:
            return None
        ch = self.bot.get_channel(self.admin_channel_id)
        if ch:
            return ch
        try:
            return await self.bot.fetch_channel(self.admin_channel_id)
        except Exception:
            return None

    # ---------------------------
    # Prefix command errors
    # ---------------------------
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return  # ignore typos

        try:
            await ctx.send("⚠️ An error occurred. The admin has been notified.")
        except Exception:
            pass  # ignore send fails

        admin_channel = await self._get_admin_channel()
        if not admin_channel:
            return

        err_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        embed = discord.Embed(
            title="⚠️ Command Error",
            description=f"```py\n{err_text[:1900]}\n```",
            color=discord.Color.red()
        )
        embed.add_field(name="User", value=ctx.author.mention, inline=True)
        embed.add_field(name="Command", value=str(ctx.command), inline=True)

        try:
            await admin_channel.send(embed=embed)
        except Exception:
            traceback.print_exc()

    # ---------------------------
    # Slash command errors
    # ---------------------------
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        # User-facing message
        if interaction.response.is_done():
            await interaction.followup.send("⚠️ Something went wrong. The admin has been notified.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Something went wrong. The admin has been notified.", ephemeral=True)

        admin_channel = await self._get_admin_channel()
        if not admin_channel:
            return

        err_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        embed = discord.Embed(
            title="⚠️ Slash Command Error",
            description=f"```py\n{err_text[:1900]}\n```",
            color=discord.Color.red()
        )
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.add_field(name="Command", value=str(interaction.command), inline=True)

        try:
            await admin_channel.send(embed=embed)
        except Exception:
            traceback.print_exc()

    # ---------------------------
    # Global errors (events, tasks, etc.)
    # ---------------------------
    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        admin_channel = await self._get_admin_channel()
        if not admin_channel:
            return

        err_text = traceback.format_exc()
        embed = discord.Embed(
            title="🔥 Global Error",
            description=f"Event: `{event}`\n```py\n{err_text[:1900]}\n```",
            color=discord.Color.red()
        )

        try:
            await admin_channel.send(embed=embed)
        except Exception:
            traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))