import discord
GUILD_ID = 864441968776052747
GUILD = discord.Object(id=GUILD_ID)


####################
# PEOPLE
####################

EVERYONE = 864441968776052747


####################
# BTR CHANNELS
####################

# Official
CHANGELOG = 976951910571589692

# Doormat
WELCOME = 865515335867301908

# Knowledgebase
SERVER_INFO = 1283518545795481691

# Command
STAFF_CHAT = 864442610613485590
MODERATION_LOG = 866938361628852224
BOT = 865511340911493131

# Scheduling
SCHEDULE = 864487380366000178
WORKSHOP_INTEREST = 893876429098475581

# Community
GENERAL = 864441969286578178
ARMA_DISCUSSION = 864487446611623986
COMBAT_FOOTAGE = 895606965525442600
PROPAGANDA = 968823323993726996
SME_CORNER = 976953022934552616

# Smoke Pit
SMOKE_PIT = 976953342666367057  # Category

# Custom Channels
CUSTOM_CHANNELS = 1289482845634695198  # Category
CREATE_CHANNEL = 1282336034012794880  # Voice

# Operations
OPERATION_ANNOUNCEMENTS = 1287777745413345362
COMMENDATIONS = 1274979300386275328
COMMAND = 864487652124131349  # Voice
DEPLOYED = 864487710545674320  # Voice


####################
# BTR RANKS
####################

PROSPECT = 977544142341165106
MEMBER = 977542795881504769

VERIFIED = 864443957625618463
CANDIDATE = 1248923418372341770
ASSOCIATE = 864443914668474399
CONTRACTOR = 864443893852667932
MERCENARY = 1248923647003983905
OPERATOR = 864443872003620874
TACTICIAN = 864443849342189577
STRATEGIST = 864443819571019776
ADVISOR = 864443725248462848


PROMOTIONS = {
    PROSPECT: VERIFIED,
    VERIFIED: CANDIDATE,
    CANDIDATE: ASSOCIATE,
    ASSOCIATE: CONTRACTOR,
    CONTRACTOR: MERCENARY,
    MERCENARY: OPERATOR,
    OPERATOR: ADVISOR,
    TACTICIAN: STRATEGIST,
    STRATEGIST: ADVISOR
}
DEMOTIONS = {
    ADVISOR: OPERATOR,
    OPERATOR: MERCENARY,
    MERCENARY: CONTRACTOR,
    STRATEGIST: TACTICIAN,
    TACTICIAN: CONTRACTOR,
    CONTRACTOR: ASSOCIATE,
    ASSOCIATE: CANDIDATE,
    CANDIDATE: VERIFIED,
    VERIFIED: PROSPECT
}


####################
# BTR SPECIAL ROLES
####################

SNEK_LORD = 1264200306485362710
UNIT_STAFF = 864443672032706560
SERVER_HAMSTER = 977542488661323846
GUINEA_PIG = 1108496330176856125
CURATOR = 977543359432380456
MISSION_BUILDER = 977543401895522377
ZEUS = 977543532904583199
ZEUS_IN_TRAINING = 1133852373836640306
RECRUITER = 1281943837354360882
OPERATION_PINGS = 1287521007556497478


####################
# BTR SMES
####################

SME_RW_PILOT = 864443977658925107
SME_FW_PILOT = 970078666862235698
SME_JTAC = 970078704527114270
SME_MEDIC = 970078742552645714
SME_HEAVY_WEAPONS = 970078799200935956
SME_MARKSMAN = 970078835984973834
SME_MECHANISED = 970078944277717053
SME_ARTILLERY = 970078977542725632
SME_NAVAL = 1279951044389896263

SME_ROLES = (SME_RW_PILOT, SME_FW_PILOT, SME_JTAC, SME_MEDIC, SME_HEAVY_WEAPONS, SME_MARKSMAN, SME_MECHANISED, SME_NAVAL)


####################
# BTR EMOJIS
####################

GREEN = 874935884192043009
RED = 874935884208820224
YELLOW = 874935884187836447
BLUE = 877938186238701598

PEEPO_POP = "<:PeepoPop:1279898084180230174>"


####################
# COMMAND ROLE LIMITATIONS
####################

CMD_UPLOADMISSION_LIMIT = (UNIT_STAFF, SERVER_HAMSTER, MISSION_BUILDER, CURATOR, SNEK_LORD)
CMD_REFRESHSCHEDULE_LIMIT = (UNIT_STAFF, SERVER_HAMSTER, CURATOR, SNEK_LORD)
CMD_AAR_LIMIT = (UNIT_STAFF, CURATOR, ZEUS, ZEUS_IN_TRAINING, SNEK_LORD)
CMD_STAFF_LIMIT = (UNIT_STAFF, SNEK_LORD)
CMD_VERIFY_LIMIT = (UNIT_STAFF, SERVER_HAMSTER, ADVISOR, RECRUITER, SNEK_LORD)
CMD_DATACENTER_LIMIT = (UNIT_STAFF, SERVER_HAMSTER, GUINEA_PIG, SNEK_LORD)
CMD_CLEANWSINTEREST_LIMIT = (UNIT_STAFF, SNEK_LORD, SME_RW_PILOT, SME_FW_PILOT, SME_JTAC, SME_MEDIC, SME_HEAVY_WEAPONS, SME_MARKSMAN, SME_MECHANISED, SME_ARTILLERY)
