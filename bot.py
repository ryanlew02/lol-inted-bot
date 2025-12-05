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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

def get_match_ids(puuid, count):
    raise NotImplementedError

@bot.command()
async def inted(ctx, summoner_name: str):
    await ctx.send(f"Alright, checking recent games for summoner: {summoner_name}...")

    try:
        puuid = get_puuid(summoner_name, platform="na1")
    except Exception as e:
        await ctx.send(f"Error fetching summoner data: {e}")
        return
    
    match_ids = get_match_ids(puuid, count=5)

    if not match_ids:
        await ctx.send("No recent matches found for that summoner.")
        return
    
    formatted = "\n".join([f"- {match_id}" for match_id in match_ids])
    await ctx.send(f"Recent matches for {summoner_name}:\n{formatted}")





def get_puuid(ctx, *, summoner_name: str, platform: str) -> str:

    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{quote(summoner_name)}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch summoner data: {response.status_code} - {response.text}")

    data = response.json()
    return data["puuid"]

bot.run(DISCORD_TOKEN)