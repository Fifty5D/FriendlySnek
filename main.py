import os, re, asyncio, discord, json, datetime
import pytz # type: ignore

from logger import Logger

import platform  # Set appropriate event loop policy to avoid runtime errors on windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from discord.ext import commands  # type: ignore

if not os.path.exists("./secret.py"):
    Logger.info("Creating a secret.py file!")
    with open("secret.py", "w") as f:
        f.write(  # Write secret.py template
            """TOKEN = ""
TOKEN_DEV = ""
DEBUG = True

MOD_UPDATE_ACTIVE = False
SME_REMINDER_ACTIVE = False
SME_BIG_BROTHER = False

SFTP = {
    "0.0.0.0": {
        "username": "",
        "password": ""
    },
}

REDDIT_ACTIVE = False
REDDIT = {
    "client_id": "",
    "client_secret": "",
    "password": ""
}

DISCORD_LOGGING = {
    "upload_mission_file": True,
    "upload_file": True
}
"""
        )
    exit()

import secret

from constants import *
if secret.DEBUG:
    from constants.debug import *

# Set up directories
def setupDirectory(dirName: str) -> None:
    if not os.path.exists(dirName):
        # Logger.info(f"Creating directory '{dirName}'")
        os.mkdir(dirName)

usedDirectories = ("data", "tmp", "tmp/missionUpload", "tmp/fileUpload")
for directory in usedDirectories:
    setupDirectory(directory)


# Set up data JSON files
def setupJSONDataFile(filename: str, dump: list | dict) -> None:
    if not os.path.exists(filename):
        # Logger.info(f"Creating data file '{filename}'")
        with open(filename, "w") as f:
            json.dump(dump, f, indent=4)

DATA_FILES = {
    EVENTS_FILE: [],
    EVENTS_HISTORY_FILE: [],
    WORKSHOP_TEMPLATES_FILE: [],
    ROLE_RESERVATION_BLACKLIST_FILE: [],
    "data/workshopTemplates.json": [],
    "data/eventTemplates.json": [],
    MEMBER_TIME_ZONES_FILE: {},
    REMINDERS_FILE: {},
    REPEATED_MSG_DATE_LOG_FILE: {},
    GENERIC_DATA_FILE: {},
    WORKSHOP_INTEREST_FILE: {},
}
for filePath, dump in DATA_FILES.items():
    setupJSONDataFile(filePath, dump)



COGS = [cog[:-3] for cog in os.listdir("cogs/") if cog.endswith(".py")]
# COGS = ["schedule"]  # DEBUG: Faster startup
cogsReady = {cog: False for cog in COGS}

INTENTS = discord.Intents.all()
UTC = pytz.utc

class FriendlySnek(commands.Bot):
    """Friendly Snek bot."""
    def __init__(self, *, intents: discord.Intents) -> None:
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            activity=discord.Activity(  # 🐍
                type=discord.ActivityType.watching,
                name="you"
            ),
            status="online"
        )

    async def setup_hook(self) -> None:
        for cog in COGS:
            await client.load_extension(f"cogs.{cog}")
        self.tree.copy_global_to(guild=GUILD)  # This copies the global commands over to your guild.
        await self.tree.sync(guild=GUILD)

client = FriendlySnek(intents=INTENTS)
client.ready = False

@client.event
async def on_ready() -> None:
    while not all(cogsReady.values()):
        await asyncio.sleep(1)
    client.ready = True

    Logger.info(f"Bot Ready! Logged in as {client.user}.")


@client.event
async def on_message(message: discord.Message) -> None:
    """On message client event."""
    if message.author.id == FRIENDLY_SNEK:  # Ignore messages from itself
        return
    if secret.DEBUG and message.author.id in FRIENDLY_SNEKS:  # Ignore messages from other Friendly Sneks if DEBUG mode
        return

    if message.guild is None or message.guild.id != GUILD_ID:  # Ignore messages that were not sent on the correct server
        return

    # Execute commands
    if message.content.startswith(COMMAND_PREFIX):
        Logger.debug(f"{message.author.display_name} ({message.author}) > {message.content}")
        message.content = message.content.lower()
        await client.process_commands(message)

    # Run message content analysis
    await analyzeChannel(client, message, COMBAT_FOOTAGE, "video")
    await analyzeChannel(client, message, PROPAGANDA, "image")


async def analyzeChannel(client, message: discord.Message, channelID: int, attachmentContentType: str) -> None:
    """Will analyze the discord.Message contents and see if it meets the channel purpose.

    Parameters:
    message (discord.Message): The Discord message.
    channelID (int): The target channel ID.
    attachmentContentType (str): A string to determine the allowed discord.Message attachment, either "video" or "image".

    Returns:
    None.
    """
    if message.channel.id != channelID:
        return

    if any(role.id == UNIT_STAFF for role in (message.author.roles if isinstance(message.author, discord.Member) else [])):
        return

    if any(attachment.content_type.startswith(f"{attachmentContentType}/") for attachment in message.attachments if attachment.content_type is not None):
        return

    if attachmentContentType == "video" and re.search(r"https?:\/\/((www)?(clips)?\.)?(youtu(be)?|twitch|streamable|medal)\.(com|be|tv).+", message.content):
        return

    try:
        await message.delete()
    except Exception as e:
        Logger.exception(f"{message.author} | {e}")

    try:
        Logger.info(f"Removed message in #{client.get_channel(channelID)} from {message.author.display_name} ({message.author}). Message content: {message.content}")
        DEVS = ", ".join([f"**{message.guild.get_member(name)}**" for name in DEVELOPERS if message.guild is not None and message.guild.get_member(name) is not None])

        await message.author.send(embed=discord.Embed(title="❌ Message removed", description=f"The message you just posted in <#{channelID}> was deleted because no {attachmentContentType} was detected in it.\n\nIf this is an error, then please ask **staff** to post the {attachmentContentType} for you, and inform: {DEVS}", color=discord.Color.red()))
    except Exception as e:
        Logger.exception(f"{message.author} | {e}")


@client.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel) -> None:
    if not secret.DISCORD_LOGGING.get("channel_create", False):
        return
    channelAuditLogs = channel.guild.get_channel(AUDIT_LOGS)
    if not isinstance(channelAuditLogs, discord.TextChannel):
        Logger.exception("on_guild_channel_create: channelAuditLogs not discord.TextChannel")
        return
    embed = discord.Embed(title="Channel Created", description=f"`{channel.name}`", color=discord.Color.green())
    embed.set_footer(text=f"Channel ID: {channel.id}")
    embed.timestamp = datetime.datetime.now()
    await channelAuditLogs.send(embed=embed)

@client.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
    if not secret.DISCORD_LOGGING.get("channel_delete", False):
        return
    channelAuditLogs = channel.guild.get_channel(AUDIT_LOGS)
    if not isinstance(channelAuditLogs, discord.TextChannel):
        Logger.exception("on_guild_channel_delete: channelAuditLogs not discord.TextChannel")
        return
    embed = discord.Embed(title="Channel Deleted", description=f"`{channel.name}`", color=discord.Color.red())
    embed.set_footer(text=f"Channel ID: {channel.id}")
    embed.timestamp = datetime.datetime.now()
    await channelAuditLogs.send(embed=embed)


@client.event
async def on_error(event, *args, **kwargs) -> None:
    """  """
    Logger.exception(f"An error occured! {event}")


@client.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """  """
    errorType = type(error)
    if errorType is commands.errors.MissingRequiredArgument:
        await ctx.send_help(ctx.command)
    elif not errorType is commands.CommandNotFound:
        Logger.exception(f"{ctx.author} | {error}")


@client.command()
@commands.has_any_role(SNEK_LORD)
async def reload(ctx: commands.Context) -> None:
    """Reload bot cogs."""
    Logger.info(f"{ctx.author.display_name} ({ctx.author}) Reloading bot cogs...")
    for cog in COGS:
        await client.reload_extension(f"cogs.{cog}")
    await client.tree.sync(guild=GUILD)
    await ctx.send("Cogs reloaded!")


@client.command()
@commands.has_any_role(SNEK_LORD)
async def stop(ctx: commands.Context) -> None:
    """Stops bot."""
    await client.close()


if __name__ == "__main__":
    try:
        client.run(secret.TOKEN_DEV if secret.DEBUG else secret.TOKEN)
        Logger.info("Bot stopped!")
    except Exception as e:
        Logger.exception(e)
