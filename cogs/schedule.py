import os
import re
import json
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from dateutil.parser import parse as datetimeParse
import pytz

from discord import Embed, Colour
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_permission
from discord_slash.model import SlashCommandPermissionType

from constants import *

from __main__ import log, cogsReady, DEBUG
if DEBUG:
    from constants.debug import *

EVENT_TIME_FORMAT = "%Y-%m-%d %I:%M %p"
EVENTS_FILE = "data/events.json"
MEMBER_TIME_ZONES_FILE = "data/memberTimeZones.json"
TIMEOUT_EMBED = Embed(title="Time ran out. Try again. :anguished:", color=Colour.red())
EVENTS_HISTORY_FILE = "data/eventsHistory.json"
WORKSHOP_TEMPLATES_FILE = "data/workshopTemplates.json"
WORKSHOP_INTEREST_FILE = "data/workshopInterest.json"

MAX_SERVER_ATTENDANCE = 50

# Training map first, then the rest in alphabetical order
MAPS = [
    "Training Map",
    "Al Salman, Iraq",
    "Altis",
    "Anizay",
    "Chernarus",
    "Desert",
    "Fapovo",
    "Hellanmaa Winter",
    "Hellanmaa",
    "Isla Abramia",
    "Kidal",
    "Kujari",
    "Kunduz",
    "Laghisola",
    "Lingor/Dingor Island",
    "Livonia",
    "Malden 2035",
    "Porto",
    "Pulau",
    "Sahrani",
    "Shapur",
    "Stratis",
    "Takistan",
    "Tanoa",
    "Utes",
    "Uzbin Valley",
    "Vinjesvingen",
    "Virolahti",
    "Zargabad",
]

UTC = pytz.utc
TIME_ZONES = {
    "UTC": "UTC",
    "Pacific American Time (LA)": "America/Los_Angeles",
    "Eastern American Time (NY)": "America/New_York",
    "British Time (London)": "Europe/London",
    "Central European Time (Brussels)": "Europe/Brussels",
    "Eastern European Time (Sofia)": "Europe/Sofia",
    "Japanese Time (Tokyo)": "Asia/Tokyo",
    "Australian Western Time (Perth)": "Australia/Perth",
    "Australian Central Western Time (Eucla)": "Australia/Eucla",
    "Australian Central Time (Adelaide)": "Australia/Adelaide",
    "Australian Eastern Time (Sydney)": "Australia/Sydney",
}

class Schedule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.eventsFileLock = False
        self.memberTimeZonesFileLock = False

    @commands.Cog.listener()
    async def on_ready(self):
        if cogsReady["schedule"]:
            return
        log.debug(LOG_IS_READY.format("Schedule"), flush=True)
        cogsReady["schedule"] = True
        if not os.path.exists(EVENTS_HISTORY_FILE):
            with open(EVENTS_HISTORY_FILE, "w") as f:
                json.dump([], f, indent=4)
        if not os.path.exists(WORKSHOP_TEMPLATES_FILE):
            with open(WORKSHOP_TEMPLATES_FILE, "w") as f:
                json.dump([], f, indent=4)
        await self.updateSchedule()
        try:
            self.autoDeleteEvents.start()
        except Exception:
            log.warning(LOG_COULDNT_START.format("autoDeleteEvents scheduler"))
        try:
            self.checkAcceptedReminder.start()
        except Exception:
            log.warning(LOG_COULDNT_START.format("checkAcceptedReminder scheduler"))

    async def saveEventToHistory(self, event, autoDeleted=False):
        guild = self.bot.get_guild(SERVER)
        if event.get("type", "Operation") == "Workshop":
            if (workshopInterestName := event.get("workshopInterest")) is not None:
                with open(WORKSHOP_INTEREST_FILE) as f:
                    workshopInterest = json.load(f)
                if (workshop := workshopInterest.get(workshopInterestName)) is not None:
                    accepted = event["accepted"]
                    if event["maxPlayers"] is not None:
                        accepted = accepted[:event["maxPlayers"]]
                    updateWorkshopInterest = False
                    for memberId in accepted:
                        if memberId in workshop["members"]:
                            updateWorkshopInterest = True
                            workshop["members"].remove(memberId)
                    if updateWorkshopInterest:
                        with open(WORKSHOP_INTEREST_FILE, "w") as f:
                            json.dump(workshopInterest, f, indent=4)
                        embed = self.bot.get_cog("WorkshopInterest").getWorkshopEmbed(workshop)
                        workshopMessage = await self.bot.get_channel(WORKSHOP_INTEREST).fetch_message(workshop["messageId"])
                        await workshopMessage.edit(embed=embed)

        with open(EVENTS_HISTORY_FILE) as f:
            eventsHistory = json.load(f)
        eventCopy = deepcopy(event)
        eventCopy["autoDeleted"] = autoDeleted
        eventCopy["authorName"] = member.display_name if (member := guild.get_member(eventCopy["authorId"])) is not None else "UNKNOWN"
        eventCopy["acceptedNames"] = [member.display_name if (member := guild.get_member(memberId)) is not None else "UNKNOWN" for memberId in eventCopy["accepted"]]
        eventCopy["declinedNames"] = [member.display_name if (member := guild.get_member(memberId)) is not None else "UNKNOWN" for memberId in eventCopy["declined"]]
        eventCopy["declinedForTimingNames"] = [member.display_name if (member := guild.get_member(memberId)) is not None else "UNKNOWN" for memberId in eventCopy.get("declinedForTiming", [])]
        eventCopy["tentativeNames"] = [member.display_name if (member := guild.get_member(memberId)) is not None else "UNKNOWN" for memberId in eventCopy["tentative"]]
        eventCopy["reservableRolesNames"] = {role: ((member.display_name if (member := guild.get_member(memberId)) is not None else "UNKNOWN") if memberId is not None else "VACANT") for role, memberId in eventCopy["reservableRoles"].items()} if eventCopy["reservableRoles"] is not None else {}
        eventsHistory.append(eventCopy)
        with open(EVENTS_HISTORY_FILE, "w") as f:
            json.dump(eventsHistory, f, indent=4)

    @tasks.loop(minutes=10)
    async def autoDeleteEvents(self):
        while not self.bot.ready:
            await asyncio.sleep(1)
        log.debug(LOG_CHECKING.format("to auto delete events"))
        self.eventsFileLock = False
        try:
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            utcNow = UTC.localize(datetime.utcnow())
            deletedEvents = []
            for event in events:
                endTime = UTC.localize(datetime.strptime(event["endTime"], EVENT_TIME_FORMAT))
                if utcNow > endTime + timedelta(minutes=90):
                    log.debug(LOG_DELETE_EVENT_ACTION.format(event['title']))
                    deletedEvents.append(event)
                    eventMessage = await self.bot.get_channel(SCHEDULE).fetch_message(event["messageId"])
                    await eventMessage.delete()
                    # author = self.bot.get_guild(SERVER).get_member(event["authorId"])
                    # await self.bot.get_channel(ARMA_DISCUSSION).send(f"{author.mention} You silly goose, you forgot to delete your operation. I'm not your mother, but this time I will do it for you")
                    if event["maxPlayers"] != 0:
                        await self.saveEventToHistory(event, autoDeleted=True)
            if len(deletedEvents) == 0:
                log.debug(LOG_DELETE_EVENT_NONE)
            for event in deletedEvents:
                events.remove(event)
            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            print(e)
        finally:
            self.eventsFileLock = False

    @tasks.loop(minutes=10)
    async def checkAcceptedReminder(self):
        while not self.bot.ready:
            await asyncio.sleep(1)
        guild = self.bot.get_guild(SERVER)
        log.debug(LOG_CHECKING.format("for accepted reminders"))
        try:
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            utcNow = UTC.localize(datetime.utcnow())
            channel = self.bot.get_channel(ARMA_DISCUSSION)
            for event in events:
                if event.get("checkedAcceptedReminders", False):
                    continue
                if event.get("type", "Operation") != "Operation":
                    continue
                startTime = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))
                if utcNow > startTime + timedelta(minutes=30):
                    acceptedMembers = [guild.get_member(memberId) for memberId in event["accepted"]]
                    onlineMembers = self.bot.get_channel(COMMAND).members + self.bot.get_channel(DEPLOYED).members
                    acceptedMembersNotOnline = []
                    onlineMembersNotAccepted = []
                    for member in acceptedMembers:
                        if member not in onlineMembers and member not in acceptedMembersNotOnline:
                            acceptedMembersNotOnline.append(member)
                    for member in onlineMembers:
                        if member.id != event["authorId"] and member not in acceptedMembers and member not in onlineMembersNotAccepted:
                            onlineMembersNotAccepted.append(member)

                    event["checkedAcceptedReminders"] = True
                    with open(EVENTS_FILE, "w") as f:
                        json.dump(events, f, indent=4)
                    if len(acceptedMembersNotOnline) > 0:
                        log.debug(LOG_NOTIFICATION_ACCEPTED.format([member.display_name for member in acceptedMembersNotOnline]))
                        await channel.send(" ".join(member.mention for member in acceptedMembersNotOnline) + SCHEDULE_REMINDER_VOICE.format(COMMAND, DEPLOYED, event['type'].lower(), SCHEDULE))
                    if len(onlineMembersNotAccepted) > 0:
                        log.debug(LOG_NOTIFICATION_VC.format([member.display_name for member in onlineMembersNotAccepted]))
                        await channel.send(" ".join(member.mention for member in onlineMembersNotAccepted) + SCHEDULE_REMINDER_INGAME.format(SCHEDULE))
        except Exception as e:
            print(e)

    @cog_ext.cog_slash(name="refreshschedule",
                        description=REFRESH_SCHEDULE_COMMAND_DESCRIPTION,
                        guild_ids=[SERVER],
                        permissions={
                            SERVER: [
                                create_permission(EVERYONE, SlashCommandPermissionType.ROLE, False),
                                create_permission(UNIT_STAFF, SlashCommandPermissionType.ROLE, True),
                                create_permission(ZEUS, SlashCommandPermissionType.ROLE, True),
                                create_permission(CURATOR, SlashCommandPermissionType.ROLE, True),
                            ]
                        })
    async def refreshSchedule(self, ctx: SlashContext):
        await ctx.send(SCHEDULE_REFRESHING.format(SCHEDULE))
        await self.updateSchedule()

    async def updateSchedule(self):
        self.lastUpdate = datetime.utcnow()
        channel = self.bot.get_channel(SCHEDULE)
        await channel.purge(limit=None, check=lambda m: m.author.id in FRIENDLY_SNEKS)

        await channel.send(SCHEDULE_INTRO_MESSAGE.format(channel.guild.get_member(ADRIAN).display_name, channel.guild.get_member(FROGGI).display_name))

        if os.path.exists(EVENTS_FILE):
            try:
                self.eventsFileLock = False
                with open(EVENTS_FILE) as f:
                    events = json.load(f)
                if len(events) == 0:
                    await channel.send(SCHEDULE_EMPTY_1)
                    await channel.send(SCHEDULE_EMPTY_2)
                for event in sorted(events, key=lambda e: datetime.strptime(e["time"], EVENT_TIME_FORMAT), reverse=True):
                    embed = self.getEventEmbed(event)
                    msg = await channel.send(embed=embed)
                    if event["reservableRoles"] is not None:
                        emojis = ("✅", "⏱", "❌", "❓", "👤", "✏️", "🗑")
                    else:
                        emojis = ("✅", "⏱", "❌", "❓", "✏️", "🗑")
                    for emoji in emojis:
                        await msg.add_reaction(emoji)
                    event["messageId"] = msg.id
                with open(EVENTS_FILE, "w") as f:
                    json.dump(events, f, indent=4)
            except Exception as e:
                print(e)
            finally:
                self.eventsFileLock = False
        else:
            with open(EVENTS_FILE, "w") as f:
                json.dump([], f, indent=4)
        if not os.path.exists(MEMBER_TIME_ZONES_FILE):
            with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                json.dump({}, f, indent=4)

    def getEventEmbed(self, event):
        guild = self.bot.get_guild(SERVER)

        colors = {
            "Operation": Colour.green(),
            "Workshop": Colour.blue(),
            "Event": Colour.gold()
        }
        embed = Embed(title=event["title"], description=event["description"], color=colors[event.get("type", "Operation")])

        if event["reservableRoles"] is not None:
            embed.add_field(name="\u200B", value="\u200B", inline=False)
            embed.add_field(name=f"Reservable Roles ({len([role for role, memberId in event['reservableRoles'].items() if memberId is not None])}/{len(event['reservableRoles'])}) 👤", value="\n".join(f"{roleName} - {('*' + member.display_name + '*' if (member := guild.get_member(memberId)) is not None else '**VACANT**') if memberId is not None else '**VACANT**'}" for roleName, memberId in event["reservableRoles"].items()), inline=False)
        embed.add_field(name="\u200B", value="\u200B", inline=False)
        embed.add_field(name="Time", value=f"<t:{round(UTC.localize(datetime.strptime(event['time'], EVENT_TIME_FORMAT)).timestamp())}:F> - <t:{round(UTC.localize(datetime.strptime(event['endTime'], EVENT_TIME_FORMAT)).timestamp())}:t>", inline=False)
        embed.add_field(name="Duration", value=event['duration'], inline=False)
        embed.add_field(name="Map", value="Unspecified" if event["map"] is None else event["map"], inline=False)
        if event["externalURL"] is not None:
            embed.add_field(name="\u200B", value="\u200B", inline=False)
            embed.add_field(name="External URL", value=event["externalURL"], inline=False)
        embed.add_field(name="\u200B", value="\u200B", inline=False)

        accepted = [member.display_name for memberId in event["accepted"] if (member := guild.get_member(memberId)) is not None]
        standby = []
        if event["maxPlayers"] is not None and len(accepted) > event["maxPlayers"]:
            accepted, standby = accepted[:event["maxPlayers"]], accepted[event["maxPlayers"]:]
        declined = [member.display_name for memberId in event["declined"] if (member := guild.get_member(memberId)) is not None]
        declinedForTiming = [member.display_name for memberId in event.get("declinedForTiming", []) if (member := guild.get_member(memberId)) is not None]
        tentative = [member.display_name for memberId in event["tentative"] if (member := guild.get_member(memberId)) is not None]

        if event["maxPlayers"] != 0:
            embed.add_field(name=f"Accepted ({len(accepted)}/{event['maxPlayers']}) ✅" if event["maxPlayers"] is not None else f"Accepted ({len(accepted)}) ✅", value="\n".join(name for name in accepted) if len(accepted) > 0 else "-", inline=True)
            embed.add_field(name=f"Declined ({len(declinedForTiming)}) ⏱/❌ ({len(declined)})", value=("\n".join("⏱ " + name for name in declinedForTiming) + "\n" * (len(declinedForTiming) > 0 and len(declined) > 0) + "\n".join("❌ " + name for name in declined)) if len(declined) + len(declinedForTiming) > 0 else "-", inline=True)
            embed.add_field(name=f"Tentative ({len(tentative)}) ❓", value="\n".join(name for name in tentative) if len(tentative) > 0 else "-", inline=True)
            if len(standby) > 0:
                embed.add_field(name=f"Standby ({len(standby)}) :clock3:", value="\n".join(name for name in standby), inline=False)
        else:
            embed.add_field(name=f"Accepted ({len(accepted + standby)}) ✅", value="\u200B", inline=True)
            embed.add_field(name=f"Declined ({len(declinedForTiming)}) ⏱/❌ ({len(declined)})", value="\u200B", inline=True)
            embed.add_field(name=f"Tentative ({len(tentative)}) ❓", value="\u200B", inline=True)

        author = guild.get_member(event["authorId"])
        embed.set_footer(text=f"Created by {author.display_name}") if author else embed.set_footer(text="Created by Unknown User")
        embed.timestamp = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))

        return embed

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id != SCHEDULE:
            return
        self.eventsFileLock = False
        try:
            with open(EVENTS_FILE) as f:
                events = json.load(f)

            if any(event["messageId"] == payload.message_id for event in events) and self.bot.ready and not payload.member.bot:
                scheduleNeedsUpdate = True
                removeReaction = True
                event = [event for event in events if event["messageId"] == payload.message_id][0]
                if "declinedForTiming" not in event:
                    event["declinedForTiming"] = []
                eventMessage = await self.bot.get_channel(SCHEDULE).fetch_message(event["messageId"])
                if payload.emoji.name == "✅":
                    if payload.member.id in event["declined"]:
                        event["declined"].remove(payload.member.id)
                    if payload.member.id in event["declinedForTiming"]:
                        event["declinedForTiming"].remove(payload.member.id)
                    if payload.member.id in event["tentative"]:
                        event["tentative"].remove(payload.member.id)
                    if payload.member.id not in event["accepted"]:
                        event["accepted"].append(payload.member.id)
                elif payload.emoji.name == "❌":
                    if payload.member.id in event["accepted"]:
                        event["accepted"].remove(payload.member.id)
                    if payload.member.id in event["declinedForTiming"]:
                        event["declinedForTiming"].remove(payload.member.id)
                    if payload.member.id in event["tentative"]:
                        event["tentative"].remove(payload.member.id)
                    if payload.member.id not in event["declined"]:
                        event["declined"].append(payload.member.id)
                    if event["reservableRoles"] is not None:
                        for roleName in event["reservableRoles"]:
                            if event["reservableRoles"][roleName] == payload.member.id:
                                event["reservableRoles"][roleName] = None
                elif payload.emoji.name == "⏱":
                    if payload.member.id in event["accepted"]:
                        event["accepted"].remove(payload.member.id)
                    if payload.member.id in event["tentative"]:
                        event["tentative"].remove(payload.member.id)
                    if payload.member.id in event["declined"]:
                        event["declined"].remove(payload.member.id)
                    if payload.member.id not in event["declinedForTiming"]:
                        event["declinedForTiming"].append(payload.member.id)
                    if event["reservableRoles"] is not None:
                        for roleName in event["reservableRoles"]:
                            if event["reservableRoles"][roleName] == payload.member.id:
                                event["reservableRoles"][roleName] = None
                elif payload.emoji.name == "❓":
                    if payload.member.id in event["accepted"]:
                        event["accepted"].remove(payload.member.id)
                    if payload.member.id in event["declined"]:
                        event["declined"].remove(payload.member.id)
                    if payload.member.id in event["declinedForTiming"]:
                        event["declinedForTiming"].remove(payload.member.id)
                    if payload.member.id not in event["tentative"]:
                        event["tentative"].append(payload.member.id)
                    if event["reservableRoles"] is not None:
                        for roleName in event["reservableRoles"]:
                            if event["reservableRoles"][roleName] == payload.member.id:
                                event["reservableRoles"][roleName] = None
                elif payload.emoji.name == "👤":
                    await self.reserveRole(payload.member, event)
                elif payload.emoji.name == "✏️":
                    if payload.member.id == event["authorId"] or any(role.id == UNIT_STAFF for role in payload.member.roles):
                        reorderEvents = await self.editEvent(payload.member, event)
                        if reorderEvents:
                            with open(EVENTS_FILE, "w") as f:
                                json.dump(events, f, indent=4)
                            await self.updateSchedule()
                            return
                elif payload.emoji.name == "🗑":
                    if payload.member.id == event["authorId"] or any(role.id == UNIT_STAFF for role in payload.member.roles):
                        eventDeleted = await self.deleteEvent(payload.member, eventMessage, event)
                        if eventDeleted:
                            events.remove(event)
                            removeReaction = False
                    scheduleNeedsUpdate = False
                else:
                    scheduleNeedsUpdate = False
                if removeReaction:
                    try:
                        await eventMessage.remove_reaction(payload.emoji, payload.member)
                    except Exception:
                        pass
                if scheduleNeedsUpdate:
                    try:
                        embed = self.getEventEmbed(event)
                        await eventMessage.edit(embed=embed)
                    except Exception:
                        pass

            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            print(e)
        finally:
            self.eventsFileLock = False

    async def reserveRole(self, member, event):
        reservationTime = datetime.utcnow()
        guild = self.bot.get_guild(SERVER)

        if member.id in event["declined"]:
            event["declined"].remove(member.id)
        if member.id in event["declinedForTiming"]:
            event["declinedForTiming"].remove(member.id)
        if member.id in event["tentative"]:
            event["tentative"].remove(member.id)
        if member.id not in event["accepted"]:
            event["accepted"].append(member.id)

        if event["maxPlayers"] is not None and len(event["accepted"]) >= event["maxPlayers"] and member.id not in event["accepted"]:
            embed = Embed(title=SCHEDULE_BOP_NO_SPACE)
            try:
                await member.send(embed=embed)
            except Exception as e:
                print(member, e)
                try:
                    print(LOG_FRIEND_REQ)
                    await member.send_friend_request()
                except Exception as e:
                    print(e)
            return

        vacantRoles = [roleName for roleName, memberId in event["reservableRoles"].items() if memberId is None or guild.get_member(memberId) is None]
        currentRole = [roleName for roleName, memberId in event["reservableRoles"].items() if memberId == member.id][0] if member.id in event["reservableRoles"].values() else None

        embed = Embed(title=SCHEDULE_RESERVABLE_QUESTION, color=Colour.gold(), description=SCHEDULE_RESERVABLE_PROMPT)
        embed.add_field(name="Your current role", value=currentRole if currentRole is not None else "None", inline=False)
        embed.add_field(name="Vacant roles", value="\n".join(f"**{idx}**   {roleName}" for idx, roleName in enumerate(vacantRoles, 1)) if len(vacantRoles) > 0 else "None", inline=False)

        try:
            msg = await member.send(embed=embed)
        except Exception as e:
            print(member, e)
            try:
                print(LOG_FRIEND_REQ)
                await member.send_friend_request()
            except Exception as e:
                print(e)
            return
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=300, check=lambda msg, author=member, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
            reservedRole = response.content.strip()
            if reservedRole.isdigit() and int(reservedRole) <= len(vacantRoles) and int(reservedRole) > 0:
                reservedRole = vacantRoles[int(reservedRole) - 1]
            elif reservedRole.strip().lower() == "none":
                reservedRole = None
            else:
                embed = Embed(title=SCHEDULE_RESERVABLE_CANCELLED, color=Colour.red())
                await dmChannel.send(embed=embed)
                return
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        if reservedRole is not None:
            if event["reservableRoles"] is not None:
                for roleName in event["reservableRoles"]:
                    if event["reservableRoles"][roleName] == member.id:
                        event["reservableRoles"][roleName] = None
                if event["reservableRoles"][reservedRole] is None or guild.get_member(event["reservableRoles"][reservedRole]) is None:
                    event["reservableRoles"][reservedRole] = member.id
        else:
            if event["reservableRoles"] is not None:
                for roleName in event["reservableRoles"]:
                    if event["reservableRoles"][roleName] == member.id:
                        event["reservableRoles"][roleName] = None

        if reservationTime > self.lastUpdate:
            embed = Embed(title=SCHEDULE_RESERVABLE_COMPLETED, color=Colour.green())
            await dmChannel.send(embed=embed)
        else:
            embed = Embed(title=SCHEDULE_RESERVABLE_SCHEDULE_ERROR, color=Colour.red())
            await dmChannel.send(embed=embed)
            log.debug(LOG_SCHEDULE_UPDATE_ERROR.format(member.display_name, member.name, member.discriminator, "reserving a role"))

    async def editEvent(self, author, event):
        editingTime = datetime.utcnow()
        log.info(LOG_EDITING_EVENT.format(author.display_name, author.name, author.discriminator, "an event"))
        embed = Embed(title=SCHEDULE_EVENT_EDIT, color=Colour.gold())
        embed.add_field(name="**0** Type", value=f"```{event['type']}```", inline=False)
        embed.add_field(name="**1** Title", value=f"```{event['title']}```", inline=False)
        embed.add_field(name="**2** Description", value=f"```{event['description'] if len(event['description']) < 500 else event['description'][:500] + ' [...]'}```", inline=False)
        embed.add_field(name="**3** External URL", value=f"```{event['externalURL']}```", inline=False)
        embed.add_field(name="**4** Reservable Roles", value="```\n" + "\n".join(event["reservableRoles"].keys()) + "```" if event["reservableRoles"] is not None else "None", inline=False)
        embed.add_field(name="**5** Map", value=f"```{event['map']}```", inline=False)
        embed.add_field(name="**6** Max Players", value=f"```{event['maxPlayers']}```", inline=False)
        embed.add_field(name="**7** Time", value=f"<t:{round(UTC.localize(datetime.strptime(event['time'], EVENT_TIME_FORMAT)).timestamp())}:F>", inline=False)
        embed.add_field(name="**8** Duration", value=f"```{event['duration']}```", inline=False)
        try:
            msg = await author.send(embed=embed)
        except Exception as e:
            print(author, e)
            try:
                print(LOG_FRIEND_REQ)
                await author.send_friend_request()
            except Exception as e:
                print(e)
            return False
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=120, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
            choice = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return False
        while choice not in ("0", "1", "2", "3", "4", "5", "6", "7", "8"):
            embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_NUMBER_FROM_TO.format(0, 8))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=120, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                choice = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return False

        reorderEvents = False

        match choice:
            case "0":
                eventTypeNum = None
                while eventTypeNum not in ("1", "2", "3"):
                    embed = Embed(title=SCHEDULE_EVENT_TYPE, description=SCHEDULE_NUMBER_FROM_TO.format(1, 3), color=Colour.gold())
                    embed.add_field(name="Type", value="**1** 🟩 Operation\n**2** 🟦 Workshop\n**3** 🟨 Event")
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=60, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        eventTypeNum = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                event["type"] = {"1": "Operation", "2": "Workshop", "3": "Event"}.get(eventTypeNum, "Operation")

            case "1":
                embed = Embed(title=SCHEDULE_EVENT_TITLE.format(event.get('type', 'Operation').lower()), color=Colour.gold())
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    title = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                event["title"] = title

            case "2":
                embed = Embed(title=SCHEDULE_EVENT_DESCRIPTION_QUESTION, description=SCHEDULE_EVENT_DESCRIPTION.format(event["description"]), color=Colour.gold())
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=1800, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    description = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                event["description"] = description

            case "3":
                embed = Embed(title=SCHEDULE_EVENT_URL_TITLE, description=SCHEDULE_EVENT_URL_DESCRIPTION, color=Colour.gold())
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    externalURL = response.content.strip()
                    if externalURL.strip().lower() == "none":
                        externalURL = None
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                event["externalURL"] = externalURL

            case "4":
                embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_PROMPT)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    reservableRolesPresent = response.content.strip().lower() in ("yes", "y")
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                if reservableRolesPresent:
                    embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_LIST_TITLE, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_LIST_DESCRIPTION)
                    embed.add_field(name=SCHEDULE_EVENT_RESERVABLE_LIST_CURRENT, value=("```\n" + "\n".join(event["reservableRoles"].keys()) + "```") if event["reservableRoles"] is not None else "None")
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        reservableRoles = {role.strip(): event["reservableRoles"][role.strip()] if event["reservableRoles"] is not None and role.strip() in event["reservableRoles"] else None for role in response.content.split("\n") if len(role.strip()) > 0}
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                else:
                    reservableRoles = None
                event["reservableRoles"] = reservableRoles
                reorderEvents = True

            case "5":
                mapOK = False
                color = Colour.gold()
                while not mapOK:
                    embed = Embed(title=SCHEDULE_EVENT_MAP_PROMPT, color=color, description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(MAPS)))
                    color = Colour.red()
                    embed.add_field(name="Map", value="\n".join(f"**{idx}**   {mapName}" for idx, mapName in enumerate(MAPS, 1)))
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        eventMap = response.content.strip()
                        mapOK = True
                        if eventMap.isdigit() and int(eventMap) <= len(MAPS) and int(eventMap) > 0:
                            eventMap = MAPS[int(eventMap) - 1]
                        elif eventMap.strip().lower() == "none":
                            eventMap = None
                        else:
                            mapOK = False
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                event["map"] = eventMap

            case "6":
                embed = Embed(title=SCHEDULE_EVENT_MAX_PLAYERS, color=Colour.gold(), description=SCHEDULE_NUMBER_NON_NEGATIVE_OR_NONE)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    maxPlayers = response.content.strip()
                    if maxPlayers.isdigit() and int(maxPlayers) <= MAX_SERVER_ATTENDANCE:
                        maxPlayers = int(maxPlayers)
                    else:
                        maxPlayers = None
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                event["maxPlayers"] = maxPlayers

            case "7":
                with open(MEMBER_TIME_ZONES_FILE) as f:
                    memberTimeZones = json.load(f)

                if str(author.id) in memberTimeZones:
                    try:
                        timeZone = pytz.timezone(memberTimeZones[str(author.id)])
                    except pytz.exceptions.UnknownTimeZoneError:
                        timeZone = UTC
                else:
                    embed = Embed(title=SCHEDULE_EVENT_TIME_ZONE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TIME_ZONE_PROMPT)
                    embed.add_field(name="Time Zone", value="\n".join(f"**{idx}**   {tz}" for idx, tz in enumerate(TIME_ZONES, 1)))
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        timeZone = response.content.strip()
                        saveTimeZonepreference = True
                        if timeZone.isdigit() and int(timeZone) <= len(TIME_ZONES) and int(timeZone) > 0:
                            timeZone = pytz.timezone(list(TIME_ZONES.values())[int(timeZone) - 1])
                        else:
                            try:
                                timeZone = pytz.timezone(timeZone)
                            except pytz.exceptions.UnknownTimeZoneError:
                                timeZone = UTC
                                saveTimeZonepreference = False
                        if saveTimeZonepreference:
                            memberTimeZones[str(author.id)] = timeZone.zone
                            with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                                json.dump(memberTimeZones, f, indent=4)
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False

                startTimeOk = False
                while not startTimeOk:
                    embed = Embed(title=SCHEDULE_EVENT_TIME.format("event"), color=Colour.gold(), description=SCHEDULE_EVENT_SELECTED_TIME_ZONE.format(timeZone.zone))
                    embed.add_field(name="Current Value", value=UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT)).astimezone(timeZone).strftime(EVENT_TIME_FORMAT))
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        startTime = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                    try:
                        startTime = datetimeParse(startTime)
                        isFormatCorrect = True
                    except ValueError:
                        isFormatCorrect = False
                    while not isFormatCorrect:
                        embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_TIME_FORMAT)
                        await dmChannel.send(embed=embed)
                        try:
                            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                            startTime = response.content.strip()
                        except asyncio.TimeoutError:
                            await dmChannel.send(embed=TIMEOUT_EMBED)
                            return False
                        try:
                            startTime = datetimeParse(startTime)
                            isFormatCorrect = True
                        except ValueError:
                            isFormatCorrect = False
                    startTime = timeZone.localize(startTime).astimezone(UTC)
                    utcNow = editingTime
                    if startTime < UTC.localize(utcNow):
                        if (delta := UTC.localize(utcNow) - startTime) > timedelta(hours=1) and delta < timedelta(days=1):
                            newStartTime = startTime + timedelta(days=1)
                            embed = Embed(title=SCHEDULE_EVENT_TIME_TOMORROW, description=SCHEDULE_EVENT_TIME_TOMORROW_PREVIEW.format(round(startTime.timestamp()), round(newStartTime.timestamp())))
                            await dmChannel.send(embed=embed)
                            startTime = newStartTime
                            startTimeOk = True
                        else:
                            embed = Embed(title=SCHEDULE_EVENT_TIME_PAST_QUESTION, description=SCHEDULE_EVENT_TIME_PAST_PROMPT)
                            await dmChannel.send(embed=embed)
                            try:
                                response = await self.bot.wait_for("message", timeout=60, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                                keepStartTime = response.content.strip()
                            except asyncio.TimeoutError:
                                await dmChannel.send(embed=TIMEOUT_EMBED)
                                return False
                            if keepStartTime.lower() in ("yes", "y"):
                                startTimeOk = True
                    else:
                        startTimeOk = True

                duration = event["duration"]
                d = timedelta(
                    hours=int(duration.split("h")[0].strip()) if "h" in duration else 0,
                    minutes=int(duration.split("h")[-1].replace("m", "").strip()) if duration.strip()[-1] != "h" else 0
                )
                endTime = startTime + d
                oldStartTime = event["time"]
                event["time"] = startTime.strftime(EVENT_TIME_FORMAT)
                event["endTime"] = endTime.strftime(EVENT_TIME_FORMAT)
                reorderEvents = True
                guild = self.bot.get_guild(SERVER)
                embed = Embed(title=SCHEDULE_EVENT_START_TIME_CHANGE_TITLE.format(event["title"]), description=SCHEDULE_EVENT_START_TIME_CHANGE_DESCRIPTION.format(round(UTC.localize(datetime.strptime(oldStartTime, EVENT_TIME_FORMAT)).timestamp()), round(UTC.localize(datetime.strptime(event['time'], EVENT_TIME_FORMAT)).timestamp())))
                for memberId in event["accepted"] + event.get("declinedForTiming", []) + event["tentative"]:
                    member = guild.get_member(memberId)
                    if member is not None:
                        try:
                            await member.send(embed=embed)
                        except Exception as e:
                            print(member, e)
                            try:
                                print(LOG_FRIEND_REQ)
                                await member.send_friend_request()
                            except Exception as e:
                                print(e)

            case "8":
                embed = Embed(title=SCHEDULE_EVENT_DURATION_QUESTION.format("event"), color=Colour.gold(), description=SCHEDULE_EVENT_DURATION_PROMPT)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                    duration = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return False
                while not re.match(SCHEDULE_EVENT_DURATION_REGEX, duration):
                    embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_DURATION_PROMPT)
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, author=author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        duration = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                startTime = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))
                d = timedelta(
                    hours=int(duration.split("h")[0].strip()) if "h" in duration else 0,
                    minutes=int(duration.split("h")[-1].replace("m", "").strip()) if duration.strip()[-1] != "h" else 0
                )
                endTime = startTime + d
                event["duration"] = duration
                event["endTime"] = endTime.strftime(EVENT_TIME_FORMAT)

        if editingTime > self.lastUpdate:
            embed = Embed(title=SCHEDULE_EVENT_EDITED.format(event["type"]), color=Colour.green())
            await dmChannel.send(embed=embed)
            log.info(LOG_EDITED_EVENT.format(author.display_name, author.name, author.discriminator, "an event"))
            return reorderEvents
        else:
            embed = Embed(title=SCHEDULE_EVENT_EDIT_ERROR, color=Colour.red())
            await dmChannel.send(embed=embed)
            log.info(LOG_SCHEDULE_UPDATE_ERROR.format(author.display_name, author.name, author.discriminator, "editing an event"))
            return False

    async def deleteEvent(self, author, message, event):
        try:
            msg = await author.send(SCHEDULE_EVENT_CONFIRM_DELETE)
        except Exception as e:
            print(author, e)
            try:
                print(LOG_FRIEND_REQ)
                await author.send_friend_request()
            except Exception as e:
                print(e)
            return False
        await msg.add_reaction("🗑")
        try:
            _ = await self.bot.wait_for("reaction_add", timeout=60, check=lambda reaction, user, author=author: reaction.emoji == "🗑" and user == author)
        except asyncio.TimeoutError:
            await author.send(embed=TIMEOUT_EMBED)
            return False
        await message.delete()
        try:
            embed = Embed(title=SCHEDULE_EVENT_DELETED.format(event["type"]), color=Colour.green())
            await author.send(embed=embed)

            utcNow = UTC.localize(datetime.utcnow())
            startTime = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))
            if event["maxPlayers"] != 0 and utcNow > startTime + timedelta(minutes=30):
                await self.saveEventToHistory(event)
            else:
                guild = self.bot.get_guild(SERVER)
                for memberId in event["accepted"] + event.get("declinedForTiming", []) + event["tentative"]:
                    member = guild.get_member(memberId)
                    if member is not None:
                        embed = Embed(title=SCHEDULE_EVENT_DELETED_TITLE.format(event.get("type", "Operation"), event["title"]), description=SCHEDULE_EVENT_DELETED_DESCRIPTION.format(event.get("type", "Operation").lower(), event["title"], round(UTC.localize(datetime.strptime(event['time'], EVENT_TIME_FORMAT)).timestamp())))
                        try:
                            await member.send(embed=embed)
                        except Exception as e:
                            print(member, e)
                            try:
                                print(LOG_FRIEND_REQ)
                                await member.send_friend_request()
                            except Exception as e:
                                print(e)
        except Exception as e:
            print(e)
        return True

    @cog_ext.cog_slash(name="bop", description=SCHEDULE_COMMAND_DESCRIPTION.format("an operation"), guild_ids=[SERVER])
    async def bop(self, ctx: SlashContext):
        await self.scheduleOperation(ctx)

    @cog_ext.cog_slash(name="operation", description=SCHEDULE_COMMAND_DESCRIPTION.format("an operation"), guild_ids=[SERVER])
    async def operation(self, ctx: SlashContext):
        await self.scheduleOperation(ctx)

    async def scheduleOperation(self, ctx):
        await ctx.send(SCHEDULE_EVENT_MESSAGE_PROGRESS.format(":b:op."))
        log.info(LOG_CREATING_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "an operation"))

        utcNow = UTC.localize(datetime.utcnow())
        authorId = ctx.author.id

        embed = Embed(title=SCHEDULE_EVENT_TITLE.format("operation"), description=SCHEDULE_EVENT_TITLE_OPERATION_REMINDER, color=Colour.gold())
        try:
            msg = await ctx.author.send(embed=embed)
        except Exception as e:
            print(ctx.author, e)
            try:
                print(LOG_FRIEND_REQ)
                await ctx.author.send_friend_request()
            except Exception as e:
                print(e)
            return
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            title = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_DESCRIPTION_QUESTION, color=Colour.gold())
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=1800, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            description = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_URL_TITLE, description=SCHEDULE_EVENT_URL_DESCRIPTION, color=Colour.gold())
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            externalURL = response.content.strip()
            if externalURL.strip().lower() == "none":
                externalURL = None
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_PROMPT)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            reservableRolesPresent = response.content.strip().lower() in ("yes", "y")
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        if reservableRolesPresent:
            embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_LIST_TITLE, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_LIST_DESCRIPTION)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                reservableRoles = {role.strip(): None for role in response.content.split("\n") if len(role.strip()) > 0}
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            reservableRoles = None

        mapOK = False
        color = Colour.gold()
        while not mapOK:
            embed = Embed(title=SCHEDULE_EVENT_MAP_PROMPT, color=color, description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(MAPS)))
            color = Colour.red()
            embed.add_field(name="Map", value="\n".join(f"**{idx}**   {mapName}" for idx, mapName in enumerate(MAPS, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                eventMap = response.content.strip()
                mapOK = True
                if eventMap.isdigit() and int(eventMap) <= len(MAPS) and int(eventMap) > 0:
                    eventMap = MAPS[int(eventMap) - 1]
                elif eventMap.strip().lower() == "none":
                    eventMap = None
                else:
                    mapOK = False
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        embed = Embed(title=SCHEDULE_EVENT_MAX_PLAYERS, color=Colour.gold(), description=SCHEDULE_NUMBER_NON_NEGATIVE_OR_NONE)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            maxPlayers = response.content.strip()
            if maxPlayers.isdigit() and int(maxPlayers) <= MAX_SERVER_ATTENDANCE:
                maxPlayers = int(maxPlayers)
            else:
                maxPlayers = None
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_DURATION_QUESTION.format("operation"), color=Colour.gold(), description=SCHEDULE_EVENT_DURATION_PROMPT)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            duration = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        while not re.match(SCHEDULE_EVENT_DURATION_REGEX, duration):
            embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_DURATION_PROMPT)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                duration = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        d = timedelta(
            hours=int(duration.split("h")[0].strip()) if "h" in duration else 0,
            minutes=int(duration.split("h")[-1].replace("m", "").strip()) if duration.strip()[-1] != "h" else 0
        )

        with open(MEMBER_TIME_ZONES_FILE) as f:
            memberTimeZones = json.load(f)

        if str(ctx.author.id) in memberTimeZones:
            try:
                timeZone = pytz.timezone(memberTimeZones[str(ctx.author.id)])
            except pytz.exceptions.UnknownTimeZoneError:
                timeZone = UTC
        else:
            embed = Embed(title=SCHEDULE_EVENT_TIME_ZONE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TIME_ZONE_PROMPT)
            embed.add_field(name="Time Zone", value="\n".join(f"**{idx}**   {tz}" for idx, tz in enumerate(TIME_ZONES, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                timeZone = response.content.strip()
                saveTimeZonepreference = True
                if timeZone.isdigit() and int(timeZone) <= len(TIME_ZONES) and int(timeZone) > 0:
                    timeZone = pytz.timezone(list(TIME_ZONES.values())[int(timeZone) - 1])
                else:
                    try:
                        timeZone = pytz.timezone(timeZone)
                    except pytz.exceptions.UnknownTimeZoneError:
                        timeZone = UTC
                        saveTimeZonepreference = False
                if saveTimeZonepreference:
                    memberTimeZones[str(ctx.author.id)] = timeZone.zone
                    with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                        json.dump(memberTimeZones, f, indent=4)
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        eventCollision = True

        while eventCollision:
            eventCollision = False

            startTimeOk = False
            while not startTimeOk:
                embed = Embed(title=SCHEDULE_EVENT_TIME.format("operation"), color=Colour.gold(), description=SCHEDULE_EVENT_SELECTED_TIME_ZONE.format(timeZone.zone))
                utcNow = datetime.utcnow()
                nextHalfHour = utcNow + (datetime.min - utcNow) % timedelta(minutes=30)
                embed.add_field(name="Example", value=UTC.localize(nextHalfHour).astimezone(timeZone).strftime(EVENT_TIME_FORMAT))
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    startTime = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
                try:
                    startTime = datetimeParse(startTime)
                    isFormatCorrect = True
                except ValueError:
                    isFormatCorrect = False
                while not isFormatCorrect:
                    embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_TIME_FORMAT)
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                        startTime = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return
                    try:
                        startTime = datetimeParse(startTime)
                        isFormatCorrect = True
                    except ValueError:
                        isFormatCorrect = False
                startTime = timeZone.localize(startTime).astimezone(UTC)
                if startTime < UTC.localize(utcNow):
                    if (delta := UTC.localize(utcNow) - startTime) > timedelta(hours=1) and delta < timedelta(days=1):
                        newStartTime = startTime + timedelta(days=1)
                        embed = Embed(title=SCHEDULE_EVENT_TIME_TOMORROW, description=SCHEDULE_EVENT_TIME_TOMORROW_PREVIEW.format(round(startTime.timestamp()), round(newStartTime.timestamp())))
                        await dmChannel.send(embed=embed)
                        startTime = newStartTime
                        startTimeOk = True
                    else:
                        embed = Embed(title=SCHEDULE_EVENT_TIME_PAST_QUESTION, description=SCHEDULE_EVENT_TIME_PAST_PROMPT)
                        await dmChannel.send(embed=embed)
                        try:
                            response = await self.bot.wait_for("message", timeout=60, check=lambda msg, author=ctx.author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                            keepStartTime = response.content.strip()
                        except asyncio.TimeoutError:
                            await dmChannel.send(embed=TIMEOUT_EMBED)
                            return False
                        if keepStartTime.lower() in ("yes", "y"):
                            startTimeOk = True
                else:
                    startTimeOk = True
            endTime = startTime + d

            with open(EVENTS_FILE) as f:
                events = json.load(f)

            for event in events:
                if event.get("type", "Operation") == "Event":
                    continue
                eventStartTime = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))
                eventEndTime = UTC.localize(datetime.strptime(event["endTime"], EVENT_TIME_FORMAT))
                if (eventStartTime <= startTime < eventEndTime) or (eventStartTime <= endTime < eventEndTime) or (startTime <= eventStartTime < endTime):
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_COLLISION, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break
                elif eventEndTime < startTime and eventEndTime + timedelta(hours=1) > startTime:
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_PADDING_EARLY, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break
                elif endTime < eventStartTime and endTime + timedelta(hours=1) > eventStartTime:
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_PADDING_LATE, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break

        self.eventsFileLock = False
        try:
            if os.path.exists(EVENTS_FILE):
                with open(EVENTS_FILE) as f:
                    events = json.load(f)
            else:
                events = []
            newEvent = {
                "authorId": authorId,
                "title": title,
                "description": description,
                "externalURL": externalURL,
                "reservableRoles": reservableRoles,
                "maxPlayers": maxPlayers,
                "map": eventMap,
                "time": startTime.strftime(EVENT_TIME_FORMAT),
                "endTime": endTime.strftime(EVENT_TIME_FORMAT),
                "duration": duration,
                "messageId": None,
                "accepted": [],
                "declined": [],
                "tentative": [],
                "type": "Operation"  # Operation, Workshop, Event
            }
            events.append(newEvent)
            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            print(e)
            newEvent = None
        finally:
            self.eventsFileLock = False

        embed = Embed(title=SCHEDULE_EVENT_CREATED.format("Operation"), color=Colour.green())
        await dmChannel.send(embed=embed)
        log.info(LOG_CREATED_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "an operation"))

        await self.updateSchedule()

        if newEvent is not None:
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            await ctx.send(SCHEDULE_EVENT_MESSAGE_DONE.format(":b:op", SERVER, SCHEDULE, events[-1]["messageId"]))

    @cog_ext.cog_slash(name="ws", description=SCHEDULE_COMMAND_DESCRIPTION.format("a workshop"), guild_ids=[SERVER])
    async def ws(self, ctx: SlashContext):
        await self.scheduleWorkshop(ctx)

    @cog_ext.cog_slash(name="workshop", description=SCHEDULE_COMMAND_DESCRIPTION.format("a workshop"), guild_ids=[SERVER])
    async def workshop(self, ctx: SlashContext):
        await self.scheduleWorkshop(ctx)

    async def scheduleWorkshop(self, ctx):
        await ctx.send(SCHEDULE_EVENT_MESSAGE_PROGRESS.format("workshop"))
        log.info(LOG_CREATING_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "a workshop"))

        utcNow = UTC.localize(datetime.utcnow())
        authorId = ctx.author.id
        with open(WORKSHOP_TEMPLATES_FILE) as f:
            workshopTemplates = json.load(f)

        embed = Embed(title=SCHEDULE_EVENT_TEMPLATE_TITLE, description=SCHEDULE_EVENT_TEMPLATE_DESCRIPTION, color=Colour.gold())
        embed.add_field(name="Template", value="\n".join(f"**{idx}**   {template['name']}" for idx, template in enumerate(workshopTemplates, 1)) if len(workshopTemplates) > 0 else "-")
        try:
            msg = await ctx.author.send(embed=embed)
        except Exception as e:
            print(ctx.author, e)
            try:
                print(LOG_FRIEND_REQ)
                await ctx.author.send_friend_request()
            except Exception as e:
                print(e)
            return
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            templateNum = response.content.strip()
            templateOk = True
            if templateNum.isdigit() and int(templateNum) <= len(workshopTemplates) and int(templateNum) > 0:
                template = workshopTemplates[int(templateNum) - 1]
            elif templateNum.strip().lower() == "none":
                template = None
            else:
                templateOk = False
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        while not templateOk:
            embed = Embed(title=SCHEDULE_INPUT_ERROR, color=Colour.red(), description=SCHEDULE_EVENT_TEMPLATE_DESCRIPTION)
            embed.add_field(name="Template", value="\n".join(f"**{idx}**   {template['name']}" for idx, template in enumerate(workshopTemplates, 1)) if len(workshopTemplates) > 0 else "-")
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                templateNum = response.content.strip()
                templateOk = True
                if templateNum.isdigit() and int(templateNum) <= len(workshopTemplates) and int(templateNum) > 0:
                    template = workshopTemplates[int(templateNum) - 1]
                elif templateNum.strip().lower() == "none":
                    template = None
                else:
                    templateOk = False
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_TITLE.format("workshop"), color=Colour.gold())
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                title = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            title = template["title"]

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_DESCRIPTION_QUESTION, color=Colour.gold())
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=1800, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                description = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            description = template["description"]

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_URL_TITLE, description=SCHEDULE_EVENT_URL_DESCRIPTION, color=Colour.gold())
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                externalURL = response.content.strip()
                if externalURL.strip().lower() == "none":
                    externalURL = None
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            externalURL = template["externalURL"]

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_PROMPT)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                reservableRolesPresent = response.content.strip().lower() in ("yes", "y")
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            if reservableRolesPresent:
                embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_LIST_TITLE, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_LIST_DESCRIPTION)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    reservableRoles = {role.strip(): None for role in response.content.strip().split("\n") if len(role.strip()) > 0}
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
            else:
                reservableRoles = None
        else:
            reservableRoles = template["reservableRoles"]

        color=Colour.gold()
        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_MAP_PROMPT, color=color, description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(MAPS)))
            color=Colour.red()
            embed.add_field(name="Map", value="\n".join(f"**{idx}**   {mapName}" for idx, mapName in enumerate(MAPS, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                eventMap = response.content.strip()
                mapOK = True
                if eventMap.isdigit() and int(eventMap) <= len(MAPS) and int(eventMap) > 0:
                    eventMap = MAPS[int(eventMap) - 1]
                elif eventMap.strip().lower() == "none":
                    eventMap = None
                else:
                    mapOK = False
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            while not mapOK:
                embed = Embed(title=SCHEDULE_INPUT_ERROR, color=Colour.red(), description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(MAPS)))
                embed.add_field(name="Map", value="\n".join(f"**{idx}**   {mapName}" for idx, mapName in enumerate(MAPS, 1)))
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    eventMap = response.content.strip()
                    mapOK = True
                    if eventMap.isdigit() and int(eventMap) <= len(MAPS) and int(eventMap) > 0:
                        eventMap = MAPS[int(eventMap) - 1]
                    elif eventMap.strip().lower() == "none":
                        eventMap = None
                    else:
                        mapOK = False
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
        else:
            eventMap = template["map"]

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_MAX_PLAYERS, color=Colour.gold(), description=SCHEDULE_NUMBER_NON_NEGATIVE_OR_NONE)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                maxPlayers = response.content.strip()
                if maxPlayers.isdigit() and int(maxPlayers) <= MAX_SERVER_ATTENDANCE:
                    maxPlayers = int(maxPlayers)
                else:
                    maxPlayers = None
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            maxPlayers = template["maxPlayers"]

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_DURATION_QUESTION.format("workshop"), color=Colour.gold(), description=SCHEDULE_EVENT_DURATION_PROMPT)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                duration = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            while not re.match(SCHEDULE_EVENT_DURATION_REGEX, duration):
                embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_DURATION_PROMPT)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    duration = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
        else:
            duration = template["duration"]

        d = timedelta(
            hours=int(duration.split("h")[0].strip()) if "h" in duration else 0,
            minutes=int(duration.split("h")[-1].replace("m", "").strip()) if duration.strip()[-1] != "h" else 0
        )

        if template is None:
            with open(WORKSHOP_INTEREST_FILE) as f:
                workshopInterestOptions = [{"name": name, "title": wsInterest["title"]} for name, wsInterest in json.load(f).items()]
            embed = Embed(title=SCHEDULE_EVENT_WAITING_LIST, color=Colour.gold(), description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(workshopInterestOptions)))
            embed.add_field(name="Workshop Lists", value="\n".join(f"**{idx}**   {wsInterest['title']}" for idx, wsInterest in enumerate(workshopInterestOptions, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                workshopInterest = response.content.strip()
                workshopInterestOk = True
                if workshopInterest.isdigit() and int(workshopInterest) <= len(workshopInterestOptions) and int(workshopInterest) > 0:
                    workshopInterest = workshopInterestOptions[int(workshopInterest) - 1]["name"]
                elif workshopInterest.strip().lower() == "none":
                    workshopInterest = None
                else:
                    workshopInterestOk = False
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            while not workshopInterestOk:
                embed = Embed(title=SCHEDULE_INPUT_ERROR, color=Colour.red(), description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(workshopInterestOptions)))
                embed.add_field(name="Workshop Lists", value="\n".join(f"**{idx}**   {wsInterest['title']}" for idx, wsInterest in enumerate(workshopInterestOptions, 1)))
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    workshopInterest = response.content.strip()
                    workshopInterestOk = True
                    if workshopInterest.isdigit() and int(workshopInterest) <= len(workshopInterestOptions) and int(workshopInterest) > 0:
                        workshopInterest = workshopInterestOptions[int(workshopInterest) - 1]
                    elif workshopInterest.strip().lower() == "none":
                        workshopInterest = None
                    else:
                        workshopInterestOk = False
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
        else:
            workshopInterest = template.get("workshopInterest")

        with open(MEMBER_TIME_ZONES_FILE) as f:
            memberTimeZones = json.load(f)

        if str(ctx.author.id) in memberTimeZones:
            try:
                timeZone = pytz.timezone(memberTimeZones[str(ctx.author.id)])
            except pytz.exceptions.UnknownTimeZoneError:
                timeZone = UTC
        else:
            embed = Embed(title=SCHEDULE_EVENT_TIME_ZONE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TIME_ZONE_PROMPT)
            embed.add_field(name="Time Zone", value="\n".join(f"**{idx}**   {tz}" for idx, tz in enumerate(TIME_ZONES, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                timeZone = response.content.strip()
                saveTimeZonepreference = True
                if timeZone.isdigit() and int(timeZone) <= len(TIME_ZONES) and int(timeZone) > 0:
                    timeZone = pytz.timezone(list(TIME_ZONES.values())[int(timeZone) - 1])
                else:
                    try:
                        timeZone = pytz.timezone(timeZone)
                    except pytz.exceptions.UnknownTimeZoneError:
                        timeZone = UTC
                        saveTimeZonepreference = False
                if saveTimeZonepreference:
                    memberTimeZones[str(ctx.author.id)] = timeZone.zone
                    with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                        json.dump(memberTimeZones, f, indent=4)
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        eventCollision = True
        while eventCollision:
            eventCollision = False

            startTimeOk = False
            while not startTimeOk:
                embed = Embed(title=SCHEDULE_EVENT_TIME.format("workshop"), color=Colour.gold(), description=SCHEDULE_EVENT_SELECTED_TIME_ZONE.format(timeZone.zone))
                utcNow = datetime.utcnow()
                nextHalfHour = utcNow + (datetime.min - utcNow) % timedelta(minutes=30)
                embed.add_field(name="Example", value=UTC.localize(nextHalfHour).astimezone(timeZone).strftime(EVENT_TIME_FORMAT))
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    startTime = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
                try:
                    startTime = datetimeParse(startTime)
                    isFormatCorrect = True
                except ValueError:
                    isFormatCorrect = False
                while not isFormatCorrect:
                    embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_TIME_FORMAT)
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                        startTime = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return
                    try:
                        startTime = datetimeParse(startTime)
                        isFormatCorrect = True
                    except ValueError:
                        isFormatCorrect = False
                startTime = timeZone.localize(startTime).astimezone(UTC)
                if startTime < UTC.localize(utcNow):
                    if (delta := UTC.localize(utcNow) - startTime) > timedelta(hours=1) and delta < timedelta(days=1):
                        newStartTime = startTime + timedelta(days=1)
                        embed = Embed(title=SCHEDULE_EVENT_TIME_TOMORROW, description=SCHEDULE_EVENT_TIME_TOMORROW_PREVIEW.format(round(startTime.timestamp()), round(newStartTime.timestamp())))
                        await dmChannel.send(embed=embed)
                        startTime = newStartTime
                        startTimeOk = True
                    else:
                        embed = Embed(title=SCHEDULE_EVENT_TIME_PAST_QUESTION, description=SCHEDULE_EVENT_TIME_PAST_PROMPT)
                        await dmChannel.send(embed=embed)
                        try:
                            response = await self.bot.wait_for("message", timeout=60, check=lambda msg, author=ctx.author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                            keepStartTime = response.content.strip()
                        except asyncio.TimeoutError:
                            await dmChannel.send(embed=TIMEOUT_EMBED)
                            return False
                        if keepStartTime.lower() in ("yes", "y"):
                            startTimeOk = True
                else:
                    startTimeOk = True
            endTime = startTime + d

            with open(EVENTS_FILE) as f:
                events = json.load(f)

            for event in events:
                if event.get("type", "Operation") != "Operation":
                    continue
                eventStartTime = UTC.localize(datetime.strptime(event["time"], EVENT_TIME_FORMAT))
                eventEndTime = UTC.localize(datetime.strptime(event["endTime"], EVENT_TIME_FORMAT))
                if (eventStartTime <= startTime < eventEndTime) or (eventStartTime <= endTime < eventEndTime) or (startTime <= eventStartTime < endTime):
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_COLLISION, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break
                elif eventEndTime < startTime and eventEndTime + timedelta(hours=1) > startTime:
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_PADDING_EARLY, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break
                elif endTime < eventStartTime and endTime + timedelta(hours=1) > eventStartTime:
                    eventCollision = True
                    embed = Embed(title=SCHEDULE_EVENT_ERROR_PADDING_LATE, colour=Colour.red(), description=SCHEDULE_EVENT_ERROR_DESCRIPTION)
                    await dmChannel.send(embed=embed)
                    break

        if template is None:
            embed = Embed(title=SCHEDULE_EVENT_TEMPLATE_SAVE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TEMPLATE_SAVE_PROMPT)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                saveTemplate = response.content.strip().lower() in ("yes", "y")
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            if saveTemplate:
                embed = Embed(title=SCHEDULE_EVENT_TEMPLATE_SAVE_NAME_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TEMPLATE_SAVE_NAME_PROMPT)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    templateName = response.content.strip()
                    if templateName.lower() == "none":
                        templateName = title
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
                newTemplate = {
                    "name": templateName,
                    "title": title,
                    "description": description,
                    "externalURL": externalURL,
                    "reservableRoles": reservableRoles,
                    "maxPlayers": maxPlayers,
                    "map": eventMap,
                    "duration": duration,
                    "workshopInterest": workshopInterest
                }
                with open(WORKSHOP_TEMPLATES_FILE) as f:
                    workshopTemplates = json.load(f)
                workshopTemplates.append(newTemplate)
                with open(WORKSHOP_TEMPLATES_FILE, "w") as f:
                    json.dump(workshopTemplates, f, indent=4)
                embed = Embed(title=SCHEDULE_TEMPLATE_SAVED, color=Colour.green())
                await dmChannel.send(embed=embed)
            else:
                embed = Embed(title=SCHEDULE_TEMPLATE_DISCARD, color=Colour.gold())
                await dmChannel.send(embed=embed)

        self.eventsFileLock = False
        try:
            if os.path.exists(EVENTS_FILE):
                with open(EVENTS_FILE) as f:
                    events = json.load(f)
            else:
                events = []
            newEvent = {
                "authorId": authorId,
                "title": title,
                "description": description,
                "externalURL": externalURL,
                "reservableRoles": reservableRoles,
                "maxPlayers": maxPlayers,
                "map": eventMap,
                "time": startTime.strftime(EVENT_TIME_FORMAT),
                "endTime": endTime.strftime(EVENT_TIME_FORMAT),
                "duration": duration,
                "messageId": None,
                "accepted": [],
                "declined": [],
                "tentative": [],
                "workshopInterest": workshopInterest,
                "type": "Workshop"  # Operation, Workshop, Event
            }
            events.append(newEvent)
            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            print(e)
            newEvent = None
        finally:
            self.eventsFileLock = False

        embed = Embed(title=SCHEDULE_EVENT_CREATED.format("Workshop"), color=Colour.green())
        await dmChannel.send(embed=embed)
        log.info(LOG_CREATED_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "a workshop"))

        await self.updateSchedule()

        if newEvent is not None:
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            await ctx.send(SCHEDULE_EVENT_MESSAGE_DONE.format("Workshop", SERVER, SCHEDULE, events[-1]['messageId']))

    @cog_ext.cog_slash(name="event", description=SCHEDULE_COMMAND_DESCRIPTION.format("a generic event"), guild_ids=[SERVER])
    async def event(self, ctx: SlashContext):
        await self.scheduleEvent(ctx)

    async def scheduleEvent(self, ctx):
        await ctx.send(SCHEDULE_EVENT_MESSAGE_PROGRESS.format("generic event"))
        log.info(LOG_CREATING_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "an event"))
        authorId = ctx.author.id
        embed = Embed(title=SCHEDULE_EVENT_TITLE.format("event"), color=Colour.gold())
        try:
            msg = await ctx.author.send(embed=embed)
        except Exception as e:
            print(ctx.author, e)
            try:
                print(LOG_FRIEND_REQ)
                await ctx.author.send_friend_request()
            except Exception as e:
                print(e)
            return
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            title = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_DESCRIPTION_QUESTION, color=Colour.gold())
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=1800, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            description = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_URL_TITLE, description=SCHEDULE_EVENT_URL_DESCRIPTION, color=Colour.gold())
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            externalURL = response.content.strip()
            if externalURL.strip().lower() == "none":
                externalURL = None
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_PROMPT)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            reservableRolesPresent = response.content.strip().lower() in ("yes", "y")
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        if reservableRolesPresent:
            embed = Embed(title=SCHEDULE_EVENT_RESERVABLE_LIST_TITLE, color=Colour.gold(), description=SCHEDULE_EVENT_RESERVABLE_LIST_DESCRIPTION)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                reservableRoles = {role.strip(): None for role in response.content.split("\n") if len(role.strip()) > 0}
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
        else:
            reservableRoles = None

        mapOK = False
        color=Colour.gold()
        while not mapOK:
            embed = Embed(title=SCHEDULE_EVENT_MAP_PROMPT, color=color, description=SCHEDULE_NUMBER_FROM_TO_OR_NONE.format(1, len(MAPS)))
            color=Colour.red()
            embed.add_field(name="Map", value="\n".join(f"**{idx}**   {mapName}" for idx, mapName in enumerate(MAPS, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                eventMap = response.content.strip()
                mapOK = True
                if eventMap.isdigit() and int(eventMap) <= len(MAPS) and int(eventMap) > 0:
                    eventMap = MAPS[int(eventMap) - 1]
                elif eventMap.strip().lower() == "none":
                    eventMap = None
                else:
                    mapOK = False
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        embed = Embed(title=SCHEDULE_EVENT_MAX_PLAYERS, color=Colour.gold(), description=SCHEDULE_NUMBER_NON_NEGATIVE_OR_NONE)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            maxPlayers = response.content.strip()
            if maxPlayers.isdigit() and int(maxPlayers) <= MAX_SERVER_ATTENDANCE:
                maxPlayers = int(maxPlayers)
            else:
                maxPlayers = None
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return

        embed = Embed(title=SCHEDULE_EVENT_DURATION_QUESTION.format("event"), color=Colour.gold(), description=SCHEDULE_EVENT_DURATION_PROMPT)
        await dmChannel.send(embed=embed)
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            duration = response.content.strip()
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        while not re.match(SCHEDULE_EVENT_DURATION_REGEX, duration):
            embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_DURATION_PROMPT)
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                duration = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        d = timedelta(
            hours=int(duration.split("h")[0].strip()) if "h" in duration else 0,
            minutes=int(duration.split("h")[-1].replace("m", "").strip()) if duration.strip()[-1] != "h" else 0
        )

        with open(MEMBER_TIME_ZONES_FILE) as f:
            memberTimeZones = json.load(f)

        if str(ctx.author.id) in memberTimeZones:
            try:
                timeZone = pytz.timezone(memberTimeZones[str(ctx.author.id)])
            except pytz.exceptions.UnknownTimeZoneError:
                timeZone = UTC
        else:
            embed = Embed(title=SCHEDULE_EVENT_TIME_ZONE_QUESTION, color=Colour.gold(), description=SCHEDULE_EVENT_TIME_ZONE_PROMPT)
            embed.add_field(name="Time Zone", value="\n".join(f"**{idx}**   {tz}" for idx, tz in enumerate(TIME_ZONES, 1)))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                timeZone = response.content.strip()
                saveTimeZonepreference = True
                if timeZone.isdigit() and int(timeZone) <= len(TIME_ZONES) and int(timeZone) > 0:
                    timeZone = pytz.timezone(list(TIME_ZONES.values())[int(timeZone) - 1])
                else:
                    try:
                        timeZone = pytz.timezone(timeZone)
                    except pytz.exceptions.UnknownTimeZoneError:
                        timeZone = UTC
                        saveTimeZonepreference = False
                if saveTimeZonepreference:
                    memberTimeZones[str(ctx.author.id)] = timeZone.zone
                    with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                        json.dump(memberTimeZones, f, indent=4)
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return

        startTimeOk = False
        while not startTimeOk:
            embed = Embed(title=SCHEDULE_EVENT_TIME.format("event"), color=Colour.gold(), description=SCHEDULE_EVENT_SELECTED_TIME_ZONE.format(timeZone.zone))
            utcNow = datetime.utcnow()
            nextHalfHour = utcNow + (datetime.min - utcNow) % timedelta(minutes=30)
            embed.add_field(name="Example", value=UTC.localize(nextHalfHour).astimezone(timeZone).strftime(EVENT_TIME_FORMAT))
            await dmChannel.send(embed=embed)
            try:
                response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                startTime = response.content.strip()
            except asyncio.TimeoutError:
                await dmChannel.send(embed=TIMEOUT_EMBED)
                return
            try:
                startTime = datetimeParse(startTime)
                isFormatCorrect = True
            except ValueError:
                isFormatCorrect = False
            while not isFormatCorrect:
                embed = Embed(title=SCHEDULE_INPUT_ERROR, colour=Colour.red(), description=SCHEDULE_EVENT_TIME_FORMAT)
                await dmChannel.send(embed=embed)
                try:
                    response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
                    startTime = response.content.strip()
                except asyncio.TimeoutError:
                    await dmChannel.send(embed=TIMEOUT_EMBED)
                    return
                try:
                    startTime = datetimeParse(startTime)
                    isFormatCorrect = True
                except ValueError:
                    isFormatCorrect = False
            startTime = timeZone.localize(startTime).astimezone(UTC)
            if startTime < UTC.localize(utcNow):
                if (delta := UTC.localize(utcNow) - startTime) > timedelta(hours=1) and delta < timedelta(days=1):
                    newStartTime = startTime + timedelta(days=1)
                    embed = Embed(title=SCHEDULE_EVENT_TIME_TOMORROW, description=SCHEDULE_EVENT_TIME_TOMORROW_PREVIEW.format(round(startTime.timestamp()), round(newStartTime.timestamp())))
                    await dmChannel.send(embed=embed)
                    startTime = newStartTime
                    startTimeOk = True
                else:
                    embed = Embed(title=SCHEDULE_EVENT_TIME_PAST_QUESTION, description=SCHEDULE_EVENT_TIME_PAST_PROMPT)
                    await dmChannel.send(embed=embed)
                    try:
                        response = await self.bot.wait_for("message", timeout=60, check=lambda msg, author=ctx.author, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == author)
                        keepStartTime = response.content.strip()
                    except asyncio.TimeoutError:
                        await dmChannel.send(embed=TIMEOUT_EMBED)
                        return False
                    if keepStartTime.lower() in ("yes", "y"):
                        startTimeOk = True
            else:
                startTimeOk = True
        endTime = startTime + d

        self.eventsFileLock = False
        try:
            if os.path.exists(EVENTS_FILE):
                with open(EVENTS_FILE) as f:
                    events = json.load(f)
            else:
                events = []
            newEvent = {
                "authorId": authorId,
                "title": title,
                "description": description,
                "externalURL": externalURL,
                "reservableRoles": reservableRoles,
                "maxPlayers": maxPlayers,
                "map": eventMap,
                "time": startTime.strftime(EVENT_TIME_FORMAT),
                "endTime": endTime.strftime(EVENT_TIME_FORMAT),
                "duration": duration,
                "messageId": None,
                "accepted": [],
                "declined": [],
                "tentative": [],
                "type": "Event"  # Operation, Workshop, Event
            }
            events.append(newEvent)
            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            print(e)
            newEvent = None
        finally:
            self.eventsFileLock = False

        embed = Embed(title=SCHEDULE_EVENT_CREATED.format("Event"), color=Colour.green())
        await dmChannel.send(embed=embed)
        log.info(LOG_CREATED_EVENT.format(ctx.author.display_name, ctx.author.name, ctx.author.discriminator, "an event"))

        await self.updateSchedule()

        if newEvent is not None:
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            await ctx.send(SCHEDULE_EVENT_MESSAGE_DONE.format("Event", SERVER, SCHEDULE, events[-1]['messageId']))

    @cog_ext.cog_slash(name="changetimezone", description=CHANGE_TIME_ZONE_COMMAND_DESCRIPTION, guild_ids=[SERVER])
    async def changeTimeZone(self, ctx: SlashContext):
        await ctx.send(SCHEDULE_TIME_ZONE_CHANGING)

        with open(MEMBER_TIME_ZONES_FILE) as f:
            memberTimeZones = json.load(f)

        embed = Embed(title=SCHEDULE_TIME_ZONE_QUESTION, color=Colour.gold(), description=(SCHEDULE_EVENT_SELECTED_TIME_ZONE.format(memberTimeZones[str(ctx.author.id)]) if str(ctx.author.id) in memberTimeZones else SCHEDULE_TIME_ZONE_UNSET) + SCHEDULE_TIME_ZONE_INFORMATION)
        embed.add_field(name="Time Zone", value="\n".join(f"**{idx}**   {tz}" for idx, tz in enumerate(TIME_ZONES, 1)))
        embed.set_footer(text=SCHEDULE_CANCEL)
        try:
            msg = await ctx.author.send(embed=embed)
        except Exception as e:
            print(ctx.author, e)
            try:
                print(LOG_FRIEND_REQ)
                await ctx.author.send_friend_request()
            except Exception as e:
                print(e)
            return
        dmChannel = msg.channel
        try:
            response = await self.bot.wait_for("message", timeout=600, check=lambda msg, ctx=ctx, dmChannel=dmChannel: msg.channel == dmChannel and msg.author == ctx.author)
            timeZone = response.content.strip()
            if self.memberTimeZonesFileLock:
                embed = Embed(title=SCHEDULE_TIME_ZONE_FILE_OCCUPIED)
                await ctx.author.send(embed=embed)
                while self.memberTimeZonesFileLock:
                    while self.memberTimeZonesFileLock:
                        await asyncio.sleep(0.5)
                    await asyncio.sleep(0.5)
            self.memberTimeZonesFileLock = True
            with open(MEMBER_TIME_ZONES_FILE) as f:
                memberTimeZones = json.load(f)
            if timeZone.strip().lower() == "cancel":
                return
            if timeZone.isdigit() and int(timeZone) <= len(TIME_ZONES) and int(timeZone) > 0:
                timeZone = pytz.timezone(list(TIME_ZONES.values())[int(timeZone) - 1])
                memberTimeZones[str(ctx.author.id)] = timeZone.zone
            else:
                try:
                    timeZone = pytz.timezone(timeZone)
                    memberTimeZones[str(ctx.author.id)] = timeZone.zone
                except pytz.exceptions.UnknownTimeZoneError:
                    if str(ctx.author.id) in memberTimeZones:
                        del memberTimeZones[str(ctx.author.id)]
            with open(MEMBER_TIME_ZONES_FILE, "w") as f:
                json.dump(memberTimeZones, f, indent=4)
            embed = Embed(title=SCHEDULE_TIME_ZONE_DONE, color=Colour.green())
            await dmChannel.send(embed=embed)
        except asyncio.TimeoutError:
            await dmChannel.send(embed=TIMEOUT_EMBED)
            return
        self.memberTimeZonesFileLock = False

def setup(bot):
    bot.add_cog(Schedule(bot))
