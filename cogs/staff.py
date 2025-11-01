import re, json, os, discord, logging

from datetime import datetime, timezone
from discord.ext import commands  # type: ignore
from unidecode import unidecode
from textwrap import wrap

from utils import Utils
from secret import DEBUG
from constants import *
if DEBUG:
    from constants.debug import *

log = logging.getLogger("FriendlySnek")

class Staff(commands.Cog):
    """Staff Cog."""
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.debug(LOG_COG_READY.format("Staff"))
        self.bot.cogsReady["staff"] = True

    @staticmethod
    def _getMember(searchTerm: str, guild: discord.Guild) -> discord.Member | None:
        """Searches for a discord.Member - supports a lot of different serach terms.

        Parameters:
        searchTerm (str): Search query for a discord.Member.

        Returns:
        discord.Member | None: Returns a discord.Member if found, otherwise None.
        """
        member = None
        for member_ in guild.members:
            if searchTerm.replace("<", "").replace("@", "").replace("!", "").replace(">", "").isdigit() and int(searchTerm.replace("<", "").replace("@", "").replace("!", "").replace(">", "")) == member_.id:
                """ Mentions, IDs """
                member = member_
                break
            elif (searchTerm == member_.display_name.lower()) or (isinstance(member_.global_name, str) and searchTerm == member_.global_name.lower()) or (searchTerm == member_.name.lower()) or (searchTerm == member_.mention.lower()) or (searchTerm == member_.name.lower() + "#" + member_.discriminator) or (searchTerm == member_.mention.lower().replace("<@", "<@!")) or (searchTerm == member_.mention.lower().replace("<@!", "<@")) or (searchTerm.isdigit() and int(searchTerm) == member_.discriminator):
                """ Display names, name, raw name """
                member = member_
                break
            elif (searchTerm in member_.display_name.lower()) or (searchTerm in member_.name.lower()) or (searchTerm in member_.mention.lower()) or (searchTerm in member_.mention.lower().replace("<@", "<@!")) or (searchTerm in member_.mention.lower().replace("<@!", "<@")):
                """ Parts of name """
                member = member_
        return member

    @commands.command(name="getmember")
    async def getMember(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Get detailed information about a guild member."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff getmember: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            await ctx.send(f"No member found for search term: `{member}`")
            return

        embed = discord.Embed(description=targetMember.mention, color=targetMember.color)
        avatar = targetMember.avatar if targetMember.avatar else targetMember.display_avatar
        embed.set_author(icon_url=targetMember.display_avatar, name=targetMember)
        embed.set_thumbnail(url=avatar)
        embed.add_field(name="Joined", value="`Unknown`" if targetMember.joined_at is None else discord.utils.format_dt(targetMember.joined_at, style="f"), inline=True)
        embed.add_field(name="Registered", value=discord.utils.format_dt(targetMember.created_at, style="f"), inline=True)

        roles = [role.mention for role in targetMember.roles]  # Fetch all member roles
        roles.pop(0)  # Remove @everyone role
        roles = roles[::-1]  # Reverse the list
        embed.add_field(name=f"Roles [{len(targetMember.roles) - 1}]", value=" ".join(roles) if len(roles) > 0 else "None", inline=False)

        KEY_PERMISSIONS = {
            "Administrator": targetMember.guild_permissions.administrator,
            "Manage Server": targetMember.guild_permissions.manage_guild,
            "Manage Roles": targetMember.guild_permissions.manage_roles,
            "Manage Channels": targetMember.guild_permissions.manage_channels,
            "Manage Messages": targetMember.guild_permissions.manage_messages,
            "Manage Webhooks": targetMember.guild_permissions.manage_webhooks,
            "Manage Nicknames": targetMember.guild_permissions.manage_nicknames,
            "Manage Emojis": targetMember.guild_permissions.manage_emojis,
            "Kick Members": targetMember.guild_permissions.kick_members,
            "Ban Members": targetMember.guild_permissions.ban_members,
            "Mention Everyone": targetMember.guild_permissions.mention_everyone
        }

        PERMISSIONS = [name for name, perm in KEY_PERMISSIONS.items() if perm]
        if len(PERMISSIONS) > 0:
            embed.add_field(name="Key Permissions", value=", ".join(PERMISSIONS), inline=False)

        if targetMember.id == targetMember.guild.owner_id:
            embed.add_field(name="Acknowledgements", value="Server Owner", inline=False)

        embed.set_footer(text=f"ID: {targetMember.id}")
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

    @commands.command(name="purge")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def purgeMessagesFromMember(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Purges all messages from a specific member."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff purgeMessagesFromMember: ctx.guild not discord.Guild")
            return
        tagetMember = Staff._getMember(member, ctx.guild)
        if tagetMember is None:
            log.warning(f"{ctx.author.id} [{ctx.author.display_name}] No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff purgeMessagesFromMember: guild is None")
            return

        log.info(f"\n---------\n{ctx.author.id} [{ctx.author.display_name}] Is purging all messages from '{member}' {tagetMember.display_name} [{tagetMember}]\n---------")
        embed = discord.Embed(title="Purging messages", description=f"Member: {tagetMember.mention}\nThis may take a while!", color=discord.Color.orange())
        embed.set_footer(text=f"ID: {tagetMember.id}")
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

        for channel in guild.text_channels:
            log.debug(f"Purging {tagetMember.id} [{tagetMember.display_name}] messages in {channel.mention}")
            try:
                await channel.purge(limit=None, check=lambda m: m.author.id == tagetMember.id)
            except (discord.Forbidden, discord.HTTPException):
                log.warning(f"Failed to purge {tagetMember.id} [{tagetMember.display_name}] messages from {channel.mention}")
        log.info(f"Done purging messages from {tagetMember.id} [{tagetMember.display_name}]")
        embed = discord.Embed(title="✅ Messages purged", description=f"Member: {tagetMember.mention}", color=discord.Color.green())
        embed.set_footer(text=f"ID: {tagetMember.id}")
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

    @commands.command(name="lastactivity")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def lastActivity(self, ctx: commands.Context, pingStaff: str = commands.parameter(default="yes", description="If staff is pinged when finished")) -> None:
        """Get last activity (message) for all members."""
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff lastactivity: guild is None")
            return

        log.info(f"{ctx.author.id} [{ctx.author.display_name}] Fetches last activity for all members")
        embed = discord.Embed(title="Analyzing members' last activity", color=discord.Color.orange())
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

        lastMessagePerMember = {member: None for member in guild.members}
        embed = discord.Embed(title="Channel checking", color=discord.Color.orange())
        embed.add_field(name="Channel", value="Loading...", inline=True)
        embed.add_field(name="Progress", value="0 / 0", inline=True)
        embed.set_footer(text=f"Run by: {ctx.author}")
        msg = await ctx.send(embed=embed)
        textChannels = len(guild.text_channels)
        for i, channel in enumerate(guild.text_channels, 1):
            embed.set_field_at(0, name="Channel", value=f"{channel.mention}", inline=True)
            embed.set_field_at(1, name="Progress", value=f"{i} / {textChannels}", inline=True)
            await msg.edit(embed=embed)
            membersNotChecked = set(channel.members)
            async for message in channel.history(limit=None):
                for member in set(membersNotChecked):
                    if member.bot:
                        membersNotChecked.discard(member)
                        continue
                    if lastMessagePerMember[member] is not None and lastMessagePerMember[member].created_at > message.created_at:
                        membersNotChecked.discard(member)
                if message.author in membersNotChecked:
                    membersNotChecked.discard(message.author)
                    if lastMessagePerMember[message.author] is None or message.created_at > lastMessagePerMember[message.author].created_at:
                        lastMessagePerMember[message.author] = message
                if len(membersNotChecked) == 0:
                    break

        embed = discord.Embed(title="✅ Channel checking", color=discord.Color.green())
        embed.set_footer(text=f"Run by: {ctx.author}")
        embed.timestamp = datetime.now()
        await msg.edit(embed=embed)
        lastActivityPerMember = [(f"{member.display_name} ({member})", f"{member.mention}\n{discord.utils.format_dt(lastMessage.created_at, style='F')}\n[Last Message]({lastMessage.jump_url})" if lastMessage is not None else f"{member.mention}\nNot Found!")
        for member, lastMessage in sorted(lastMessagePerMember.items(), key=lambda x: x[1].created_at if x[1] is not None else datetime(1970, 1, 1, tzinfo=timezone.utc))]
        for i in range(0, len(lastActivityPerMember), 25):
            embed = discord.Embed(title=f"Last activity per member ({i + 1} - {min(i + 25, len(lastActivityPerMember))} / {len(lastActivityPerMember)})", color=discord.Color.dark_green())
            for j in range(i, min(i + 25, len(lastActivityPerMember))):
                embed.add_field(name=lastActivityPerMember[j][0], value=lastActivityPerMember[j][1], inline=False)
            await ctx.send(embed=embed)
        if pingStaff.lower() in ("y", "ye", "yes", "ping"):
            roleUnitStaff = guild.get_role(UNIT_STAFF)
            await ctx.send(f"{'' if roleUnitStaff is None else roleUnitStaff.mention} Last activity analysis has finished!")

    @commands.command(name="lastactivitymember")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def lastActivityForMember(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Get last activity (message) for a specific member."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff lastactivitymember: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            log.warning(f"{ctx.author.id} [{ctx.author.display_name}] No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff lastactivitymember: guild is None")
            return

        log.info(f"{ctx.author.id} [{ctx.author.display_name}] Fetches last activity for {targetMember.id} [{targetMember.display_name}]")
        lastMessage = None
        for channel in guild.text_channels:
            try:
                lastMessageInChannel = await channel.history(limit=None).find(lambda m: m.author.id == targetMember.id)
                if lastMessageInChannel is None:
                    continue
                if lastMessage is None or lastMessageInChannel.created_at > lastMessage.created_at:
                    lastMessage = lastMessageInChannel
            except Exception:
                log.warning(f"Staff lastactivitymember: Failed to search messages from channel #{channel.name}")

        if lastMessage is None:
            embed = discord.Embed(title="❌ Last activity", description=f"Activity not found!\nMember: {targetMember.mention}", color=discord.Color.red())
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="✅ Last activity", description=f"Activity found: {discord.utils.format_dt(lastMessage.created_at.timestamp(), style='F')}!\nMember: {targetMember.mention}", color=discord.Color.green())
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)

    @commands.command(name="promote")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def promote(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Promote a member to the next rank."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff promote: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            log.warning(f"Staff promote: No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff promote: guild is None")
            return

        for role in targetMember.roles:
            if role.id in PROMOTIONS:
                newRole = guild.get_role(PROMOTIONS[role.id])
                if newRole is None:
                    log.exception("Staff promote: newRole is None")
                    return

                log.info(f"{ctx.author.id} [{ctx.author.display_name}] Promotes {targetMember.id} [{targetMember.display_name}] from '{role}' to '{newRole}'")
                await targetMember.remove_roles(role)
                await targetMember.add_roles(newRole)
                embed = discord.Embed(title="✅ Member promoted", description=f"{targetMember.mention} promoted from {role.mention} to {newRole.mention}!", color=discord.Color.green())
                embed.set_footer(text=f"ID: {targetMember.id}")
                embed.timestamp = datetime.now()
                await ctx.send(embed=embed)
                break

        else:
            log.warning(f"{ctx.author.id} [{ctx.author.display_name}] No promotion possible for {targetMember.id} [{targetMember.display_name}]")
            embed = discord.Embed(title="❌ No possible promotion", description=f"Member: {targetMember.mention}", color=discord.Color.red())
            embed.set_footer(text=f"ID: {targetMember.id}")
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)

    @commands.command(name="demote")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def demote(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Demote a member to the previous rank."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff demote: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            log.warning(f"{ctx.author.id} [{ctx.author.display_name}] No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff promote: guild is None")
            return

        for role in targetMember.roles:
            if role.id in DEMOTIONS:
                newRole = guild.get_role(DEMOTIONS[role.id])
                if newRole is None:
                    log.exception("Staff promote: newRole is None")
                    return

                log.info(f"{ctx.author.id} [{ctx.author.display_name}] Demoting {targetMember.id} [{targetMember.display_name}] from '{role}' to '{newRole}'")
                await targetMember.remove_roles(role)
                await targetMember.add_roles(newRole)
                embed = discord.Embed(title="✅ Member demoted", description=f"{targetMember.mention} demoted from {role.mention} to {newRole.mention}!", color=discord.Color.green())
                embed.set_footer(text=f"ID: {targetMember.id}")
                embed.timestamp = datetime.now()
                await ctx.send(embed=embed)
                break

        else:
            log.warning(f"{ctx.author.id} [{ctx.author.display_name}] No demotion possible for {targetMember.id} [{targetMember.display_name}]")
            embed = discord.Embed(title="❌ No possible demotion", description=f"Member: {targetMember.mention}", color=discord.Color.red())
            embed.set_footer(text=f"ID: {targetMember.id}")
            embed.timestamp = datetime.now()
            await ctx.send(embed=embed)

    @staticmethod
    def _match_member_reference(message_content: str, targetMember: discord.Member) -> str | None:
        """
        Returns a string if the message_content contains a reference to targetMember.
        The string is the search term that matched.
        Returns None if no match.

        The following types of references are checked:
        display_name (case-insensitive, word-boundary)
        exact name (case-insensitive, word-boundary)
        mention (<@id>, boundary-checked)
        mention variant (<@!id>, boundary-checked)
        alternate mention variant (<@id> from <@!id>), boundary-checked
        raw id anywhere in content
        """
        s = message_content
        s_lower = s.lower()
        display = targetMember.display_name.lower()
        name = targetMember.name.lower()
        mention = targetMember.mention
        mention_alt1 = mention.replace("<@", "<@!")
        mention_alt2 = mention.replace("<@!", "<@")
        id_str = str(targetMember.id)

        def boundary_ok(text: str, start: int, end: int) -> bool:
            # ensure char before/after are not word chars (if present)
            if start > 0 and re.match(r"\w", text[start - 1]):
                return False
            if end < len(text) and re.match(r"\w", text[end]):
                return False
            return True

        # display_name (case-insensitive)
        idx = s_lower.find(display)
        if idx != -1 and boundary_ok(s_lower, idx, idx + len(display)):
            return display

        # exact name (case-insensitive)
        idx = s_lower.find(name)
        if idx != -1 and boundary_ok(s_lower, idx, idx + len(name)):
            return name

        # mentions / variants (check raw message, not lowered)
        idx = s.find(mention)
        if idx != -1 and boundary_ok(s, idx, idx + len(mention)):
            return mention

        idx = s.find(mention_alt1)
        if idx != -1 and boundary_ok(s, idx, idx + len(mention_alt1)):
            return mention_alt1

        idx = s.find(mention_alt2)
        if idx != -1 and boundary_ok(s, idx, idx + len(mention_alt2)):
            return mention_alt2

        # raw id anywhere
        if id_str in s:
            return id_str

        return None

    @staticmethod
    def _getModLogContext(message: discord.Message, search_term: str) -> str:
        """Gets the context of a moderation log message for a specific search term.

        Parameters:
        message (discord.Message): The moderation log message.
        search_term (str): The search term that matched the message.

        Returns:
        str: The context of the moderation log message ("Reporter", "Subject", "Handler", or "Mentioned").
        """
        preSearch = message.content[:message.content.lower().index(search_term)-2].split("\n")[-1].lstrip("*").strip()
        if preSearch.startswith("Reporter"):
            return "Reporter"
        if preSearch.startswith("Subject"):
            return "Subject"
        if preSearch.startswith("Handler"):
            return "Handler"
        return "Mentioned"

    @commands.command(name="searchmodlogs")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def searchModLogs(self, ctx: commands.Context, *, search_term: str = commands.parameter(description="Search term for a user/member. Surround in quotes for raw search")) -> None:
        """Fetch all occurrencesances in the moderation log related to a member."""
        # TODO
        # When seraching for a found target member, also search for display name (str)
        #
        # Implement filtering by context. E.g. only show logs where user was Reporter
        channelModerationLog = self.bot.get_channel(MODERATION_LOG)
        if not isinstance(channelModerationLog, discord.TextChannel):
            log.exception("Staff searchmodlogs: channelModerationLog not discord.TextChannel")
            return

        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff searchmodlogs: ctx.guild not discord.Guild")
            return


        log.info(f"{ctx.author.id} [{ctx.author.display_name}] Searching moderation logs for '{search_term}'")

        # Force no member search if surrounded by quotes
        forceRawSearch = False
        if (search_term.startswith('"') and search_term.endswith('"')) or (search_term.startswith("'") and search_term.endswith("'")):
            forceRawSearch = True
            search_term = search_term[1:-1]

        # Check if search term matches a member
        resultsMember = []
        targetMember = Staff._getMember(search_term, ctx.guild)
        if targetMember and not forceRawSearch:
            log.debug(f"Serach mod logs, found member '{targetMember.id} [{targetMember.display_name}]'")
            await ctx.send(f"Searching moderation logs for `{targetMember.display_name}` (`{targetMember}`)...")

            async for message in channelModerationLog.history(limit=None, oldest_first=False):
                memberReference = Staff._match_member_reference(message.content, targetMember)
                if not memberReference:
                    continue

                context = Staff._getModLogContext(message, memberReference)
                resultsMember.append({
                    "id": message.id,
                    "url": message.jump_url,
                    "context": context
                })

        # Raw string serach: serach_term
        resultsRawString = []
        if not targetMember:
            await ctx.send(f"Searching moderation logs for `{search_term}`...")

        async for message in channelModerationLog.history(limit=None, oldest_first=False):
            if search_term not in message.content.lower():
                continue

            context = Staff._getModLogContext(message, search_term)
            resultsRawString.append({
                "id": message.id,
                "url": message.jump_url,
                "context": context
            })

        # Filter out raw string results that are already in member results
        if resultsMember:
            memberResultIds = {msg["id"] for msg in resultsMember}
            resultsRawString = [msg for msg in resultsRawString if msg["id"] not in memberResultIds]


        # Nothing found
        if not resultsMember and not resultsRawString:
            await ctx.send(f"No moderation logs related to search term: `{search_term}`")
            return

        # Combine results, member results first
        genEnumList = lambda msgLinksList : [f"{i+1}. {msg['url']}: `{msg['context']}`" for i, msg in enumerate(msgLinksList[::-1])]
        results = ""
        if resultsMember:
            results += f"**Member `{targetMember.display_name}`**\n"
            results += "\n".join(genEnumList(resultsMember))

        if resultsMember and resultsRawString:
            results += "\n\n"

        if resultsRawString:
            results += f"**Raw string `{search_term}`**\n"
            results += "\n".join(genEnumList(resultsRawString))

        await ctx.send(results[:2000]) # Discord message limit

    @commands.command(name="disablerolereservation")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def disableRoleReservation(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Disable role reservation for specified member."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff disablerolereservation: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            log.info(f"{ctx.author.id} [{ctx.author.display_name}] No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff disableRoleReservation: guild is None")
            return

        log.info(f"{ctx.author.id} [{ctx.author.display_name}] Added {targetMember.id} [{targetMember.display_name}] to role reservation blacklist")

        with open(ROLE_RESERVATION_BLACKLIST_FILE) as f:
            blacklist = json.load(f)
        if all(member["id"] != targetMember.id for member in blacklist):
            blacklist.append({"id": targetMember.id, "name": targetMember.display_name, "timestamp": datetime.now().timestamp(), "staffId": ctx.author.id, "staffName": ctx.author.display_name})
            with open(ROLE_RESERVATION_BLACKLIST_FILE, "w") as f:
                json.dump(blacklist, f, indent=4)
            with open(EVENTS_FILE) as f:
                events = json.load(f)
            for event in events:
                for reservableRole in event["reservableRoles"]:
                    if event["reservableRoles"][reservableRole] == targetMember.id:
                        event["reservableRoles"][reservableRole] = None
            with open(EVENTS_FILE, "w") as f:
                json.dump(events, f, indent=4)
            await self.bot.get_cog("Schedule").updateSchedule(guild)

        embed = discord.Embed(title="✅ Member blacklisted", description=f"{targetMember.mention} is no longer allowed to reserve roles!", color=discord.Color.green())
        embed.set_footer(text=f"ID: {targetMember.id}")
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

    @commands.command(name="enablerolereservation")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def enableRoleReservation(self, ctx: commands.Context, *, member: str = commands.parameter(description="Target member")) -> None:
        """Enable role reservation for specified member."""
        if not isinstance(ctx.guild, discord.Guild):
            log.exception("Staff enablerolereservation: ctx.guild not discord.Guild")
            return
        targetMember = Staff._getMember(member, ctx.guild)
        if targetMember is None:
            log.info(f"{ctx.author.id} [{ctx.author.display_name}] No member found for search term '{member}'")
            await ctx.send(embed=discord.Embed(title="❌ No member found", description=f"Searched for: `{member}`", color=discord.Color.red()))
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff enableRoleReservation: guild is None")
            return

        log.info(f"{ctx.author.id} [{ctx.author.display_name}] Removed {targetMember.id} [{targetMember.display_name}] from role reservation blacklist")

        with open(ROLE_RESERVATION_BLACKLIST_FILE) as f:
            blacklist = json.load(f)
        removedMembers = [member for member in blacklist if member["id"] == targetMember.id]
        for member in removedMembers:
            blacklist.remove(member)
        if removedMembers:
            with open(ROLE_RESERVATION_BLACKLIST_FILE, "w") as f:
                json.dump(blacklist, f, indent=4)

        embed = discord.Embed(title="✅ Member removed from blacklist", description=f"{targetMember.mention} is now allowed to reserve roles!", color=discord.Color.green())
        embed.set_footer(text=f"ID: {targetMember.id}")
        embed.timestamp = datetime.now()
        await ctx.send(embed=embed)

    @commands.command(name="smebigbrother")
    @commands.has_any_role(*CMD_LIMIT_STAFF)
    async def smeBigBrother(self, ctx: commands.Context) -> None:
        """Summarize each SMEs activity last 6 months for Unit Staff."""
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff smeBigBrother: guild is None")
            return

        from cogs.botTasks import BotTasks
        await BotTasks.smeBigBrother(guild, True)


    # Recruitment Team command
    @discord.app_commands.command(name="recruitment-interview")
    @discord.app_commands.describe(member = "Target prospect member.")
    @discord.app_commands.guilds(GUILD)
    @discord.app_commands.checks.has_any_role(*CMD_LIMIT_INTERVIEW)
    async def interview(self, interaction: discord.Interaction, member: discord.Member) -> None:
        """Helps HR interview a prospect member and decide to verify or deny."""

        await interaction.response.defer(ephemeral=True, thinking=True)  # Ensure message history doesnt expire interaction deadline

        channelRecruitmentAndHR = interaction.guild.get_channel(RECRUITMENT_AND_HR)
        if not isinstance(channelRecruitmentAndHR, discord.TextChannel):
            log.exception("Staff interview: channelRecruitmentAndHR not discord.TextChannel")
            return

        async for message in channelRecruitmentAndHR.history(limit=1000):
            if message.embeds and message.embeds[0].title == "❌ Prospect denied" and message.embeds[0].footer.text and message.embeds[0].footer.text.startswith(f"Prospect ID: {member.id}"):
                isAuthorStaff = [True for role in member.roles if role.id == UNIT_STAFF]
                if isAuthorStaff:
                    embed = discord.Embed(title="⚠️ Prospect denied", description=f"Prospect ({member.mention}) has been denied before. Since you're Unit Staff, you may still continue and override the decision!", color=discord.Color.yellow())
                    embed.set_footer(text=f"Prospect ID: {member.id}")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    embed = discord.Embed(title="❌ Prospect denied", description=f"Prospect ({member.mention}) has already been denied. Only Unit Staff may interview denied prospects!", color=discord.Color.red())
                    embed.set_footer(text=f"Prospect ID: {member.id}")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return


        view = discord.ui.View(timeout=None)
        view.add_item(StaffButton(style=discord.ButtonStyle.green, label="Verify", custom_id=f"staff_button_interview_verify_{member.id}"))
        view.add_item(StaffButton(style=discord.ButtonStyle.red, label="Deny", custom_id=f"staff_button_interview_deny_{member.id}"))

        interviewQuestions = f"""- Be enthusiastic about sigma and the interview, your energy will set the stage for how our unit operates, if it sounds like you dont care or are disinterested it will affect the quality of the unit in the eyes of the interviewee.
- Be informative to the point and honest, don't sugar-coat things, be straight forward.

1. What year were you born in? (min. ~{datetime.now(timezone.utc).year - 17})
2. Do you have any previous experience with Arma 3 or any milsim game?
 a. Have you been in any other units? What kind of units were they?
3. Have you used Arma 3 mods before?
 b. Please ensure they know how to use the HTML download, and have mods downloaded before newcomer
4. Have you used Teamspeak before?
 c. Help install teamspeak client, and have connected/bookmarked SSG teamspeak server
5. How did you find out about us?
6. Is there a specific role or playstyle you are looking to do with us?
7. Any questions?"""

        embed = discord.Embed(title="Interview Structure", description=interviewQuestions, color=discord.Color.gold())
        embed.set_footer(text=f"Prospect member id: {member.id}")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # Hampter command
    @commands.command(name="gibcmdline")
    @commands.has_any_role(*CMD_LIMIT_DATACENTER)
    async def gibcmdline(self, ctx: commands.Context) -> None:
        """Generates commandline from attached HTML modpack file."""

        # No modpack / no HTML
        if len(ctx.message.attachments) == 0 or ctx.message.attachments[0].content_type is None or not ctx.message.attachments[0].content_type.startswith("text/html"):
            await ctx.send(":moyai: I need a modpack file to generate the cmdline :moyai:")
            return

        # Modpack provided
        msg = await ctx.send("https://tenor.com/view/rat-rodent-vermintide-vermintide2-skaven-gif-20147931")
        attachmentInBytes = await ctx.message.attachments[0].read()  # Returns bytes
        html = attachmentInBytes.decode("utf-8")  # Convert to str

        mods = re.findall(r'(?<=<td data-type="DisplayName">).+(?=<\/td>)', html)

        alphanumerics = re.compile(r"[\W_]+", re.UNICODE)
        cmdline = ";".join(sorted(["@" + re.sub(alphanumerics, "", mod) for mod in mods], key=str.casefold))  # Casefold = caseinsensitive
        cmdline = wrap(unidecode(cmdline), 1990)  # Max content len == 2000

        for index, chunk in enumerate(cmdline):
            if index == 0:
                await msg.edit(content=f"```{chunk}```")
                continue
            await ctx.send(f"```{chunk}```")

    @discord.app_commands.command(name="updatemodpack")
    @discord.app_commands.guilds(GUILD)
    @discord.app_commands.checks.has_any_role(*CMD_LIMIT_DATACENTER)
    @discord.app_commands.describe(modpack = "Updated modpack.", sendtoserverinfo = "Optional boolean if sending modpack to #server-info.")
    async def updatemodpack(self, interaction: discord.Interaction, modpack: discord.Attachment, sendtoserverinfo: bool = False) -> None:
        """Update snek mod list, for which mods to check on updates."""

        log.info(f"{interaction.user.id} [{interaction.user.display_name}] Updating modpack id listing")
        # Parse modpack
        html = (await modpack.read()).decode("utf-8")
        modpackIds = [int(id) for id in re.findall(r"(?<=\"https:\/\/steamcommunity\.com\/sharedfiles\/filedetails\/\?id=)\d+", html)]

        # Save output
        with open(GENERIC_DATA_FILE) as f:
            genericData = json.load(f)
        genericData["modpackIds"] = modpackIds
        with open(GENERIC_DATA_FILE, "w") as f:
            json.dump(genericData, f, indent=4)

        # Optionally send
        if sendtoserverinfo:
            guild = self.bot.get_guild(GUILD_ID)
            if guild is None:
                log.exception("Staff updatemodpack: guild is None")
                return
            channelServerInfo = guild.get_channel(SERVER_INFO)
            if not isinstance(channelServerInfo, discord.TextChannel):
                log.exception("Staff updatemodpack: channelServerInfo not discord.TextChannel")
                return

            await channelServerInfo.send(os.path.splitext(modpack.filename)[0], file=await modpack.to_file())


        mapsDefault = "\n".join(genericData["modpackMaps"]) if "modpackMaps" in genericData else None

        modal = StaffModal(self, f"Modpack updated! Now optionally change maps", f"staff_modal_maps")
        modal.add_item(discord.ui.TextInput(label="Maps (Click \"Cancel\" to not change anything!)", style=discord.TextStyle.long, placeholder="Training Map\nAltis\nVirolahti", default=mapsDefault, required=True))
        await interaction.response.send_modal(modal)
        await interaction.followup.send("Modpack updated!", ephemeral=True)

    # Snek Lord command
    @commands.command(name="sneklord")
    @commands.has_any_role(SNEK_LORD)
    async def sneklord(self, ctx: commands.Context) -> None:
        """Snek lord prod test command."""
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            log.exception("Staff sneklord: guild is None")
            return
        for role in guild.roles:
            log.debug(f"ROLE: {role.name} - {hex(role.color.value)}")


class StaffButton(discord.ui.Button):
    """Handling all staff buttons."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        customId = interaction.data["custom_id"]

        # Verify prospect from interview
        if customId.startswith("staff_button_interview_verify_"):
            memberId = int(customId.split("_")[-1])

            if not isinstance(interaction.guild, discord.Guild):
                log.exception("StaffButton callback: interaction.guild is not discord.Guild")
                return

            member = interaction.guild.get_member(memberId)
            if not isinstance(member, discord.Member):
                log.exception(f"StaffButton callback: member not discord.Member, id '{memberId}'")
                return

            embed = discord.Embed(title="✅ Member verified", description=f"{member.mention} verified!", color=discord.Color.green())
            embed.set_footer(text=f"Verified member id: {member.id}")
            embed.timestamp = datetime.now()
            await interaction.response.send_message(embed=embed, ephemeral=True)

            roleProspect = interaction.guild.get_role(PROSPECT)
            roleVerified = interaction.guild.get_role(VERIFIED)
            roleMember = interaction.guild.get_role(MEMBER)
            if roleProspect is None or roleVerified is None or roleMember is None:
                log.exception("StaffButton callback: roleProspect, roleVerified, roleMember is None")
                return

            reason = "User verified"
            if roleProspect in member.roles:
                await member.remove_roles(roleProspect, reason=reason)
                await member.add_roles(roleVerified, reason=reason)

            await member.add_roles(roleMember, reason=reason)


            # Logging
            channelAuditLogs = interaction.guild.get_channel(AUDIT_LOGS)
            if not isinstance(channelAuditLogs, discord.TextChannel):
                log.exception("StaffButton callback: channelAuditLogs not discord.TextChannel")
                return
            embed = discord.Embed(title="Member verified", description=f"Verified: {member.mention}\nInterviewer: {interaction.user.mention}", color=discord.Color.blue())
            embed.set_footer(text=f"Verified ID: {member.id} | Interviewer ID: {interaction.user.id}")
            embed.timestamp = datetime.now()
            await channelAuditLogs.send(embed=embed)

        # Deny prospect from interview
        if customId.startswith("staff_button_interview_deny_"):
            memberId = int(customId.split("_")[-1])

            member = interaction.guild.get_member(memberId)
            if not isinstance(member, discord.Member):
                log.exception(f"StaffButton callback: member not discord.Member, id '{memberId}'")
                return

            embed = discord.Embed(title="❌ Prospect denied", description=f"{member.mention} denied", color=discord.Color.red())
            embed.set_footer(text=f"Member id: {member.id}")
            embed.timestamp = datetime.now()
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Notify Recruitment-Coordinator
            if not isinstance(interaction.guild, discord.Guild):
                log.exception("StaffButton callback: interaction.guild is not discord.Guild")
                return

            channelRecruitmentAndHR = interaction.guild.get_channel(RECRUITMENT_AND_HR)
            if not isinstance(channelRecruitmentAndHR, discord.TextChannel):
                log.exception("StaffButton callback: channelRecruitmentAndHR not discord.TextChannel")
                return

            roleRecruitmentCoordinator = interaction.guild.get_role(RECRUITMENT_COORDINATOR)
            if roleRecruitmentCoordinator is None:
                log.exception("StaffButton callback: roleRecruitmentCoordinator is None")
                return

            embed = discord.Embed(title="❌ Prospect denied", description=f"{member.mention} has been denied in interview.\nInterviewer: {interaction.user.mention}", color=discord.Color.red())
            embed.set_footer(text=f"Prospect ID: {member.id} | Interviewer ID: {interaction.user.id}")
            embed.timestamp = datetime.now()

            await channelRecruitmentAndHR.send(roleRecruitmentCoordinator.mention, embed=embed)


class StaffModal(discord.ui.Modal):
    """Handling all staff modals."""
    def __init__(self, instance, title: str, customId: str) -> None:
        super().__init__(title=title, custom_id=customId)
        self.instance = instance

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            log.exception("StaffModal on_submit: interaction.user not discord.Member")
            return

        if interaction.data["custom_id"] != "staff_modal_maps":
            log.exception("StaffModal on_submit: modal custom_id != staff_modal_maps")
            return

        log.info(f"{interaction.user.id} [{interaction.user.display_name}] Updating modpack maps listing")
        value: str = self.children[0].value.strip().split("\n")

        with open(GENERIC_DATA_FILE) as f:
            genericData = json.load(f)
        genericData["modpackMaps"] = value
        with open(GENERIC_DATA_FILE, "w") as f:
            json.dump(genericData, f, indent=4)

        await interaction.response.send_message(f"Maps updated!", ephemeral=True, delete_after=30.0)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception(error)


async def setup(bot: commands.Bot) -> None:
    Staff.interview.error(Utils.onSlashError)
    Staff.updatemodpack.error(Utils.onSlashError)
    await bot.add_cog(Staff(bot))
