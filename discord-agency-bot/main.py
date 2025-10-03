import os
import json
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("replyguy")

# -------------------------
# Load config.json
# -------------------------
CFG_PATH = Path("config.json")
if not CFG_PATH.exists():
    log.error("config.json not found!")
    raise SystemExit(1)

with open(CFG_PATH, "r") as f:
    CFG = json.load(f)

try:
    GUILD_ID = int(CFG["GUILD_ID"])
    ROLE_ID = int(CFG["TRACKED_ROLE_ID"])
    CATEGORY_ID = int(CFG["CATEGORY_ID"])
    ADMIN_LOG_CHANNEL = int(CFG["ADMIN_CHANNEL_ID"])
    APPLICATION_ID = int(CFG["APPLICATION_ID"])
except KeyError as e:
    log.error("Missing config key: %s", e)
    raise SystemExit(1)

# -------------------------
# Intents
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True

# -------------------------
# Bot
# -------------------------
bot = commands.Bot(command_prefix="!",
                   intents=intents)  # prefix kept only for legacy
_synced = False  # flag so we don't resync on reconnect


# -------------------------
# Cog Loader
# -------------------------
async def load_cogs():
    for file in os.listdir("./cogs"):
        if file.endswith(".py"):
            module = f"cogs.{file[:-3]}"
            try:
                await bot.load_extension(module)
                log.info("✅ Loaded cog: %s", module)
            except Exception as e:
                log.exception("❌ Failed to load %s: %s", module, e)


# -------------------------
# Events
# -------------------------
@bot.event
async def on_ready():
    global _synced
    log.info("🤖 Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Connected to %d guild(s).", len(bot.guilds))

    if not _synced:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        log.info("✅ Synced %d commands to guild %s", len(synced), GUILD_ID)
        _synced = True

    admin_log = bot.get_channel(ADMIN_LOG_CHANNEL)
    if admin_log:
        await admin_log.send(f"✅ Bot online as **{bot.user}**")


# -------------------------
# Slash Command: /resync
# -------------------------
@bot.tree.command(name="resync",
                  description="(Admin) Force re-sync of slash commands")
@app_commands.checks.has_permissions(administrator=True)
async def resync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    synced = await bot.tree.sync(guild=guild)
    await interaction.followup.send(
        f"✅ Resynced {len(synced)} commands to guild {GUILD_ID}.",
        ephemeral=True)


# -------------------------
# Slash Command Error Handler
# -------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError):
    log.exception("Slash command error: %s", error)
    admin_log = bot.get_channel(ADMIN_LOG_CHANNEL)
    if admin_log:
        await admin_log.send(
            f"⚠️ Error: `{error}` from {interaction.user.mention}")
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "⚠️ Internal error. Admins notified.", ephemeral=True)


# -------------------------
# Entrypoint
# -------------------------
async def main():
    async with bot:
        await load_cogs()
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("❌ DISCORD_TOKEN not found in environment!")
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Shutting down gracefully.")
        