from constants import *

from __main__ import log, DEBUG

if DEBUG:
    from constants.debug import *

staffPings = {}

async def runMessageAnalysis(bot, message):
    # await staffPingAnalysis(bot, message)
    await analyzeCombatFootage(bot, message)
    await analyzePropaganda(bot, message)

async def staffPingAnalysis(bot, message):
    staffRoles = STAFF_ROLES

    # Handle staff ping replies
    if message.reference is not None and message.reference.message_id in staffPings:
        unitStaffRole = message.guild.get_role(UNIT_STAFF)
        if unitStaffRole in message.author.roles:
            pingMessage, botMessage = staffPings[message.reference.message_id]
            log.debug(f"Staff replied to ping in message: {pingMessage.jump_url}")
            await botMessage.edit(content=f"{' '.join(role.mention for role in pingMessage.role_mentions if role.id in staffRoles)}: {pingMessage.jump_url}\nReplied by {message.author.display_name}: {message.jump_url}")
            del staffPings[message.reference.message_id]

    # Handle staff pings
    if any(role.id in staffRoles for role in message.role_mentions):
        log.debug(f"Staff Pinged\nMessage Link: {message.jump_url}\nMessage Author: {message.author.display_name}({message.author.name}#{message.author.discriminator})")
        botMessage = await bot.get_channel(STAFF_CHAT).send(f"{' '.join(role.mention for role in message.role_mentions if role.id in staffRoles)}: {message.jump_url}")
        staffPings[message.id] = (message, botMessage)

async def analyzeCombatFootage(bot, message):
    if message.channel.id != COMBAT_FOOTAGE:
        return
    if any(role.id == UNIT_STAFF for role in message.author.roles):
        return
    if any(attachment.content_type.startswith("video/") for attachment in message.attachments):
        return
    if any(videoUrl in message.content for videoUrl in ("://www.youtube.com", "://youtu.be", "://clips.twitch.tv", "://www.twitch.tv", "://streamable.com")):
        return
    await message.delete()
    try:
        await message.author.send(f"The message you just posted in <#{COMBAT_FOOTAGE}> was deleted because no video was detected in it. If this is an error, then please ask staff to post the video for you and inform {message.guild.get_member(ADRIAN).display_name} about the issue.")
    except Exception as e:
        print(message.author, e)
        try:
            print("Sending friend request...")
            await message.author.send_friend_request()
        except Exception as e:
            print(e)
    return

async def analyzePropaganda(bot, message):
    if message.channel.id != PROPAGANDA:
        return
    if any(role.id == UNIT_STAFF for role in message.author.roles):
        return
    if any(attachment.content_type.startswith("image/") for attachment in message.attachments):
        return
    await message.delete()
    try:
        await message.author.send(f"The message you just posted in <#{PROPAGANDA}> was deleted because no image was detected in it. If this is an error, then please ask staff to post the image for you and inform {message.guild.get_member(ADRIAN).display_name} about the issue.")
    except Exception as e:
        print(message.author, e)
        try:
            print("Sending friend request...")
            await message.author.send_friend_request()
        except Exception as e:
            print(e)
    return
