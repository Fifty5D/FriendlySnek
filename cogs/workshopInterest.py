import os
import json

from discord import Embed
from discord.ext import commands

from constants import *

from __main__ import log, cogsReady, DEBUG
if DEBUG:
    from constants.debug import *

WORKSHOP_INTEREST_FILE = "data/workshopInterest.json"

DEFAULT_WORKSHOP_INTEREST_LISTS = (
    (
        "Newcomer",
        "Newcomer 🐣",
        None,
        NEWCOMER_DESC
    ),
    (
        "Rotary Wing",
        "Rotary Wing 🚁",
        SME_RW_PILOT,
        RW_DESC
    ),
    (
        "Fixed Wing",
        "Fixed Wing ✈️",
        SME_FW_PILOT,
        FW_DESC
    ),
    (
        "JTAC",
        "JTAC 📡",
        SME_JTAC,
        JTAC_DESC
    ),
    (
        "Medic",
        "Medic 💉",
        SME_MEDIC,
        MEDIC_DESC
    ),
    (
        "Heavy Weapons",
        "Heavy Weapons 💣",
        SME_HEAVY_WEAPONS,
        HW_DESC
    ),
    (
        "Marksman",
        "Marksman 🎯",
        SME_MARKSMAN,
        MARKSMAN_DESC
    ),
    (
        "Breacher",
        "Breacher 🚪",
        SME_BREACHER,
        BREACHER_DESC
    ),
    (
        "Mechanised",
        "Mechanised 🛡️​",
        SME_MECHANISED,
        MECHANISED_DESC
    ),
    (
        "RPV-SO",
        "RPV-SO 🛩️​",
        SME_RPV_SO,
        RPVSO_DESC
    ),
    (
        "Team Leading",
        "Team Leading 👨‍🏫",
        None,
        TL_DESC
    )
)

class WorkshopInterest(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.debug(LOG_COG_READY.format("WorkshopInterest"), flush=True)
        cogsReady["workshopInterest"] = True

        if not os.path.exists(WORKSHOP_INTEREST_FILE):
            workshopInterest = {}
            for name, title, sme, description in DEFAULT_WORKSHOP_INTEREST_LISTS:
                workshopInterest[name] = {
                    "title": title,
                    "sme": sme,
                    "description": description,
                    "members": [],
                    "messageId": None
                }
            with open(WORKSHOP_INTEREST_FILE, "w") as f:
                json.dump(workshopInterest, f, indent=4)
        else:
            with open(WORKSHOP_INTEREST_FILE) as f:
                workshopInterest = json.load(f)
            for name, title, sme, description in DEFAULT_WORKSHOP_INTEREST_LISTS:
                workshopInterest[name]["title"] = title
                workshopInterest[name]["sme"] = sme
                workshopInterest[name]["description"] = description
            with open(WORKSHOP_INTEREST_FILE, "w") as f:
                json.dump(workshopInterest, f, indent=4)
        await self.updateChannel()

    def getWorkshopEmbed(self, workshop) -> Embed:
        guild = self.bot.get_guild(SERVER)
        embed = Embed(title=workshop["title"], description=workshop["description"])
        idsToMembers = lambda ids : [member.display_name for memberId in ids if (member := guild.get_member(memberId)) is not None]
        interestedList = idsToMembers(workshop["members"])
        interestedStr = "\n".join(interestedList)

        if interestedStr == "":
            interestedStr = "-"
        embed.add_field(name=WORKSHOPINTEREST_INTERESTED_PEOPLE.format(len(interestedList)), value=interestedStr)
        if workshop["sme"]:
            smes = [sme.display_name for sme in guild.get_role(workshop["sme"]).members]
            if smes:
                embed.set_footer(text=f"SME{'s' * (len(smes) > 1)}: {', '.join(smes)}")
        return embed

    async def updateChannel(self) -> None:
        channel = self.bot.get_channel(WORKSHOP_INTEREST)
        await channel.purge(limit=None, check=lambda message: message.author.id in FRIENDLY_SNEKS)
        await channel.send(WORKSHOPINTEREST_INTRO)

        with open(WORKSHOP_INTEREST_FILE) as f:
            workshopInterest = json.load(f)
        for workshop in workshopInterest.values():
            embed = self.getWorkshopEmbed(workshop)
            msg = await channel.send(embed=embed)
            workshop["messageId"] = msg.id
            for emoji in ("✅", "❌"):
                await msg.add_reaction(emoji)
        with open(WORKSHOP_INTEREST_FILE, "w") as f:
            json.dump(workshopInterest, f, indent=4)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload) -> None:
        if payload.channel_id != WORKSHOP_INTEREST:
            return
        try:
            with open(WORKSHOP_INTEREST_FILE) as f:
                workshopInterest = json.load(f)

            if any(workshop["messageId"] == payload.message_id for workshop in workshopInterest.values()) and self.bot.ready and not payload.member.bot:
                channelNeedsUpdate = True
                workshop = [workshop for workshop in workshopInterest.values() if workshop["messageId"] == payload.message_id][0]
                workshopMessage = await self.bot.get_channel(WORKSHOP_INTEREST).fetch_message(workshop["messageId"])
                if payload.emoji.name == "✅":
                    if payload.member.id not in workshop["members"]:
                        workshop["members"].append(payload.member.id)
                elif payload.emoji.name == "❌":
                    if payload.member.id in workshop["members"]:
                        workshop["members"].remove(payload.member.id)
                else:
                    channelNeedsUpdate = False

                try:
                    await workshopMessage.remove_reaction(payload.emoji, payload.member)
                except Exception:
                    pass

                if channelNeedsUpdate:
                    try:
                        embed = self.getWorkshopEmbed(workshop)
                        await workshopMessage.edit(embed=embed)
                    except Exception:
                        pass

            with open(WORKSHOP_INTEREST_FILE, "w") as f:
                json.dump(workshopInterest, f, indent=4)
        except Exception as e:
            print(e)

def setup(bot) -> None:
    bot.add_cog(WorkshopInterest(bot))
