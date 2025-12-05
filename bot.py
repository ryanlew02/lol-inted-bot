import os
import re
import discord
from discord.ext import commands
from dotenv import load_dotenv
import requests
from urllib.parse import quote


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

if RIOT_API_KEY is None:
    raise ValueError("RIOT_API_KEY environment variable not set.")

if DISCORD_TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="?", intents=intents)

def get_puuid(summoner_name: str, tag_line: str, platform: str) -> str:

    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch summoner data: {response.status_code} - {response.text}")

    return response.json()["puuid"]


def get_recent_match_ids_for_riot_id(riot_id: str, count: int = 5) -> list:
    match = re.match(r"^(.+?)#(.+)$", riot_id)
    if not match:
        raise ValueError("Riot ID must be in the format Name#TagLine")

    summoner_name, tag_line = match.groups()

    puuid = get_puuid(summoner_name, tag_line, platform="na1")
    match_ids = get_match_ids(puuid, count=count)
    return match_ids


def get_player_stats_from_match(puuid: str, match_id: str) -> dict:
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch match data: {resp.status_code} - {resp.text}")

    data = resp.json()
    info = data["info"]
    participants = info["participants"]

    # Find this player in the match
    for p in participants:
        if p["puuid"] == puuid:
            # Return only what you care about
            return {
                "match_id": match_id,
                "champion": p["championName"],
                "kills": p["kills"],
                "deaths": p["deaths"],
                "win": p["win"],
            }

    # If you somehow don't find the puuid
    raise Exception(f"PUUID {puuid} not found in match {match_id}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

def get_match_ids(puuid: str, count: int) -> list:
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    params = {
        "start": 0,
        "count": count,
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch match IDs: {response.status_code} - {response.text}")

    return response.json()

@bot.command()
async def inted(ctx, summoner_name_with_tag: str):

    match = re.match(r"^(.+?)#(.+)$", summoner_name_with_tag)
    if not match:
        await ctx.send("Please provide the summoner name in the format SummonerName#TagLine.")
        return

    summoner_name, tag_line = match.groups()

    await ctx.send(f"Alright, checking recent games for summoner: {summoner_name}...")

    try:
        puuid = get_puuid(summoner_name, tag_line, platform="na1")
    except Exception as e:
        await ctx.send(f"Error fetching summoner data: {e}")
        return
    
    match_ids = get_match_ids(puuid, count=5)

    if not match_ids:
        await ctx.send("No recent matches found for that summoner.")
        return

    lines = []
    for i, match_id in enumerate(match_ids, start=1):
        stats = get_player_stats_from_match(puuid, match_id)
        result = "Win." if stats["win"] else "Loss."
        line = f"{i}. {stats['champion']} {stats['kills']} / {stats['deaths']} {result}"
        lines.append(line)

    formatted = "\n".join(lines)
    await ctx.send(f"Recent matches for {summoner_name}:\n{formatted}\nWhat game would you like to pick? [1, 2, 3, 4, 5]")

bot.run(DISCORD_TOKEN)