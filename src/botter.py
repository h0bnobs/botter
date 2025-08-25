import discord
import logging
import psutil
import random
import requests
import subprocess
import time
from datetime import datetime
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

dotenv.load_dotenv()
DISCORD_TOKEN = dotenv.get_key('.env', 'DISCORD_TOKEN')
GUILD_ID = dotenv.get_key('.env', 'GUILD_ID')
CHAPPY = dotenv.get_key('.env', 'USER_ID_CHAPPY')
JOSH = dotenv.get_key('.env', 'USER_ID_JOSH')
MAX = dotenv.get_key('.env', 'USER_ID_MAX')

intents = discord.Intents.default()
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f'Logged in as {bot.user.name} - {bot.user.id}')


def filter_disallowed_users(func):
    """
    Filter out disallowed users based on their IDs.
    """

    def wrapper(*args, **kwargs):
        if not commands.check(lambda ctx: ctx.author.id == JOSH):
            func(*args, **kwargs)

    return wrapper


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.id == JOSH:
        await message.add_reaction("🇬")
        await message.add_reaction('0️⃣')
        await message.add_reaction('🇴')
        await message.add_reaction('🇳')

    if 'tuah' in message.content.lower() or 'hawk' in message.content.lower() or 'the thing' in message.content.lower():
        await message.channel.send(
            'https://tenor.com/view/marvel-fan4stic-fantastic-four-the-thing-say-that-again-gif-9345984830195785978')

    if message.author.id == MAX:
        if random.randint(1, 100) == 1:
            await message.channel.send('wowee 1 in 100!')

    await bot.process_commands(message)


@filter_disallowed_users
@bot.tree.command(name="portscan", description="Scan the local network for devices and open ports",
                  guild=discord.Object(id=GUILD_ID))
async def portscan(interaction: discord.Interaction):
    await interaction.response.send_message('grabbing ips...')
    out = subprocess.run(
        "nmap -sn -T5 -PE -PP -PM -PR 192.168.5.0/24 192.168.1.0/24 | grep '^Nmap scan' | awk '{print $5}'", shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if out.stdout:
        await interaction.followup.send(out.stdout)
        for ip in out.stdout.splitlines():
            nmap_command = f"nmap -F -T5 {ip} | awk '/Nmap scan report for/ {{ip=$NF}} /^[0-9]+\\/tcp\\s+open/ {{print ip, $1}}'"
            out = subprocess.run(nmap_command, shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
            if out.stdout:
                await interaction.followup.send(out.stdout)
    else:
        await interaction.followup.send("couldnt get any ips")


@filter_disallowed_users
@bot.tree.command(name="bangers", description="Print the message that this command is replying to",
                  guild=discord.Object(id=GUILD_ID))
async def bangers(interaction: discord.Interaction):
    if interaction.channel and interaction.message.reference:  # Check if the command is a reply
        referenced_message = await interaction.channel.fetch_message(interaction.message.reference.message_id)
        message_link = f"https://discord.com/channels/{interaction.guild.id}/{interaction.channel.id}/{referenced_message.id}"
        await interaction.response.send_message(message_link)


@filter_disallowed_users
@bot.tree.command(name="cpu", description="Show current CPU usage", guild=discord.Object(id=GUILD_ID))
async def cpu(interaction: discord.Interaction):
    cpu_usage = psutil.cpu_percent(interval=1)
    await interaction.response.send_message(f"{cpu_usage}%")


@filter_disallowed_users
@bot.tree.command(name="ip", description="Get the public and private IP address", guild=discord.Object(id=GUILD_ID))
async def ip(interaction: discord.Interaction):
    if interaction.user.id != MAX:
        await interaction.response.send_message("no")
        return
    try:
        public_ip = requests.get("https://api.ipify.org").text
        private_ip = subprocess.run("hostname -I", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True).stdout
        await interaction.response.send_message(f'Public: {public_ip}\nPrivate: {private_ip}')
    except Exception as e:
        await interaction.followup.send(f"{e}")


@filter_disallowed_users
@bot.tree.command(name="scan", description="Basic ping scan for known ranges", guild=discord.Object(id=GUILD_ID))
async def scan(interaction: discord.Interaction):
    await interaction.response.send_message('scanning...')
    out = subprocess.run(
        "nmap -sn -T5 -PE -PP -PM -PR 192.168.5.0/24 192.168.1.0/24 | grep '^Nmap scan' | awk '{print $5}'", shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if out.stdout:
        await interaction.followup.send(out.stdout)


@filter_disallowed_users
@bot.tree.command(name="tuah", description="Reveal the tuah image", guild=discord.Object(id=GUILD_ID))
async def tuah(interaction: discord.Interaction):
    await interaction.response.send_message(
        "https://media.discordapp.net/attachments/625765035754651673/1367451011186429992/IMG_0140.png"
    )


@filter_disallowed_users
@bot.tree.command(name="robots", description="Get robots.txt of a website", guild=discord.Object(id=GUILD_ID))
async def robots(interaction: discord.Interaction, url: str):
    target = url.replace("https://", "").rstrip("/")
    curl_command = f"curl -Ls {target}/robots.txt"
    try:
        out = subprocess.run(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             timeout=10)
        if out.stdout:
            for i in range(0, len(out.stdout), 2000):
                await interaction.response.send_message(out.stdout[i:i + 2000])
        else:
            await interaction.response.send_message(f"error with {curl_command}")
    except Exception as e:
        await interaction.response.send_message(f"error: {str(e)}")


bot.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.DEBUG)
