import asyncio
import os
import re
import discord
from discord.ext import commands
from dotenv import load_dotenv
import requests
from urllib.parse import quote
from openai import OpenAI



load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

if OPENAI_API_KEY is None:
    raise ValueError("OPENAI_API_KEY environment variable not set.")

if RIOT_API_KEY is None:
    raise ValueError("RIOT_API_KEY environment variable not set.")

if DISCORD_TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="?", intents=intents)

#using the ai model to generate a response
def generate_inted_response(stats: dict, summoner_name: str) -> str:

    game_description = (
        f"Player: {summoner_name}\n"
        f"Champion: {stats['champion']}\n"
        f"Kills: {stats['kills']}\n"
        f"Deaths: {stats['deaths']}\n"
        f"Assists: {stats.get('assists', 0)}\n"
        f"Result: {'Win' if stats['win'] else 'Loss'}\n"
    )
    if "teammate_champion" in stats:
        game_description += (
            "\nTeammate most likely to have inted:\n"
            f"Teammate Champion: {stats['teammate_champion']}\n"
            f"Teammate Kills: {stats['teammate_kills']}\n"
            f"Teammate Deaths: {stats['teammate_deaths']}\n"
            f"Teammate Assists: {stats.get('teammate_assists', 0)}\n"
        )

    instructions = """
        You are a playful, slightly sarcastic League of Legends analyst.
        Given a single game's stats, decide who inted.

        Rules:
        - Keep it SHORT: 1–2 sentences max.
        - You can roast the player.
        - Be witty, fun, sarcastic, unhinged gamer energy.
        - Use champ abilities / lore for jokes.
        - You MUST pick *one* of these outcomes:
            1) PLAYER inted harder
            2) TEAM inted harder
        - Use this logic:
            - If the player's deaths are the highest on the team OR their KDA is clearly the worst → PLAYER inted.
            - If someone else has significantly worse stats → THAT teammate inted harder.
            - If the player is mid-pack, mildly bad, or the whole team ran it → TEAM inted.
        - Make the verdict bold (**PLAYER inted** or **TEAM inted**).
        - Do not default to blaming the team every time.
        """

    response = client.responses.create(
        model="gpt-4.1", 
        instructions=instructions,
        input=f"Here are the stats:\n{game_description}\nNow give your verdict:"
    )

    return response.output_text.strip()

# get puuid from summoner name and tag line
def get_puuid(summoner_name: str, tag_line: str, platform: str) -> str:

    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch summoner data: {response.status_code} - {response.text}")

    return response.json()["puuid"]

# get recent match IDs for a given riot ID
def get_recent_match_ids_for_riot_id(riot_id: str, count: int = 5) -> list:
    match = re.match(r"^(.+?)#(.+)$", riot_id)
    if not match:
        raise ValueError("Riot ID must be in the format Name#TagLine")

    summoner_name, tag_line = match.groups()

    puuid = get_puuid(summoner_name, tag_line, platform="na1")
    match_ids = get_match_ids(puuid, count=count)
    return match_ids

# get player stats from a match
def get_player_stats_from_match(puuid: str, match_id: str) -> dict:
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch match data: {resp.status_code} - {resp.text}")

    data = resp.json()
    info = data["info"]
    participants = info["participants"]

    player = None
    for p in participants:
        if p["puuid"] == puuid:
            player = p
            break

    if player is None:
        raise Exception(f"PUUID {puuid} not found in match {match_id}")

    team_id = player["teamId"]

    same_team = [p for p in participants if p["teamId"] == team_id]

    teammates = [p for p in same_team if p["puuid"] != puuid]

    worst_teammate = None
    if teammates:
        def score(t):
            return (t["deaths"], -(t["kills"] + t.get("assists", 0)))

        worst_teammate = max(teammates, key=score)

    result = {
        "match_id": match_id,
        "champion": player["championName"],
        "kills": player["kills"],
        "deaths": player["deaths"],
        "assists": player.get("assists", 0),
        "win": player["win"],
    }

    if worst_teammate is not None:
        result.update({
            "teammate_champion": worst_teammate["championName"],
            "teammate_kills": worst_teammate["kills"],
            "teammate_deaths": worst_teammate["deaths"],
            "teammate_assists": worst_teammate.get("assists", 0),
        })

    return result

# Discord bot events and commands
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

# Command to check if a summoner has inted recently
@bot.command()
async def inted(ctx, *, summoner_name_with_tag: str):

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
    games = []  
    for i, match_id in enumerate(match_ids, start=1):
        stats = get_player_stats_from_match(puuid, match_id)
        games.append(stats) 

        result = "Win." if stats["win"] else "Loss."
        line = f"{i}. {stats['champion']} {stats['kills']} / {stats['deaths']} {result}"
        lines.append(line)

    formatted = "\n".join(lines)
    await ctx.send(
        f"Recent matches for {summoner_name}:\n{formatted}\n"
        f"What game would you like to pick? [1-{len(games)}]"
    )

    def check(message: discord.Message):
        return (
            message.author == ctx.author
            and message.channel == ctx.channel
        )

    try:
        reply = await bot.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond, try `?inted` again.")
        return

    try:
        choice = int(reply.content)
    except ValueError:
        await ctx.send(f"Please pick a number between 1 and {len(games)}.")
        return

    if not (1 <= choice <= len(games)):
        await ctx.send(f"Please pick a number between 1 and {len(games)}.")
        return

    chosen = games[choice - 1]
 
    result = "Win" if chosen["win"] else "Loss"
    await ctx.send(
        f"You picked game {choice}: {chosen['champion']} "
        f"{chosen['kills']} / {chosen['deaths']} ({result}).\n"
        f"Consulting the Review Board...\n"
        f"--------Please Wait----------"

    )

    try:
        verdict = generate_inted_response(chosen, summoner_name)
    except Exception as e:
        await ctx.send(f"Couldn't get a verdict from the AI: {e}")
        return

    await ctx.send(verdict)

bot.run(DISCORD_TOKEN)