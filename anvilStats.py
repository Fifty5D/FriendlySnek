import os
import json
import anvil.server

import secret

EVENTS_HISTORY_FILE = "data/eventsHistory.json"
FULL_ACTIVITY_FILE = "data/fullActivityLog.json"
ACTIVITY_FILE = "data/activityLog.json"
MEMBERS_FILE = "data/members.json"

if __name__ == '__main__':
    anvil.server.connect(secret.anvilStatsUplinkKey)

@anvil.server.callable
def getStats():
    with open(EVENTS_HISTORY_FILE) as f:
        eventsHistory = json.load(f)
    stats = {}
    for event in eventsHistory:
      if event.get("type", "Operation") not in stats:
        stats[event.get("type", "Operation")] = []
      stats[event.get("type", "Operation")].append({
        "accepted": min(event["maxPlayers"], len("accepted")) if event["maxPlayers"] is not None else len(event["accepted"]),
        "standby": max(0, len("accepted") - event["maxPlayers"]) if event["maxPlayers"] is not None else 0,
        "declined": len(event["declined"]),
        "tentative": len(event["tentative"]),
        "maxPlayers": event["maxPlayers"],
        "reservableRoles": len(event["reservableRoles"]) if event["reservableRoles"] is not None else 0,
        "reservedRoles": len([role for role, member in event["reservableRoles"].items() if member is not None]) if event["reservableRoles"] is not None else 0,
        "map": event["map"],
        "time": event["time"],
        "duration": event["duration"],
        "autoDeleted": event["autoDeleted"]
      })
    return stats

@anvil.server.callable
def getEventsHistory():
    with open(EVENTS_HISTORY_FILE) as f:
        eventsHistory = json.load(f)
    return eventsHistory

@anvil.server.callable
def getDiscordActivity():
    with open(ACTIVITY_FILE) as f:
        activity = json.load(f)
    return activity

@anvil.server.callable
def getDiscordMembers():
    with open(MEMBERS_FILE) as f:
        members = json.load(f)
    return members

@anvil.server.callable
def getFullDiscordActivity():
    with open(FULL_ACTIVITY_FILE) as f:
        fullActivity = json.load(f)
    return fullActivity

if __name__ == '__main__':
    anvil.server.wait_forever()