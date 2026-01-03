import logging
import os
import random
import re
import subprocess

import discord
import dotenv
import psutil
import requests
from discord import app_commands
from discord.ext import commands

import nmap as nm

# Load environment variables
dotenv.load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))
USER_ID_CHAPPY = int(os.getenv("USER_ID_CHAPPY", 0))
USER_ID_JOSH = int(os.getenv("USER_ID_JOSH", 0))
USER_ID_MAX = int(os.getenv("USER_ID_MAX", 0))

ALLOWED_USERS = {USER_ID_CHAPPY, USER_ID_MAX}
BLOCKED_USERS = {USER_ID_JOSH}
NETWORK_RANGES = ["192.168.5.0/24", "192.168.1.0/24"]

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="/", intents=intents)
guild_object = discord.Object(id=GUILD_ID)

# Logging
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")


def is_allowed_user():
    """Check decorator to restrict commands - blocks specific users."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLOCKED_USERS:
            await interaction.response.send_message("https://tenor.com/view/no-i-dont-think-i-will-captain-america-old-capt-gif-17162888", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


@bot.event
async def on_ready():
    await bot.tree.sync(guild=guild_object)
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # React to Josh's messages
    if message.author.id == USER_ID_JOSH:
        for emoji in ["🇬", "0️⃣", "🇴", "🇳"]:
            await message.add_reaction(emoji)

    # Convert x.com links to fixupx.com
    if "x.com/" in message.content:
        x_links = re.findall(r"https?://(?:www\.)?x\.com/\S+", message.content)
        if x_links:
            # Replace x.com with fixupx.com in the message content
            new_content = re.sub(r"https?://(?:www\.)?x\.com/", "https://fixupx.com/", message.content)

            # Remove ?s= parameter and everything after it
            new_content = re.sub(r"\?s=[^\s]*", "", new_content)

            # Build the new message with author mention
            final_message = f"{message.author.mention}: {new_content}"

            # Collect any attachments
            files = [await attachment.to_file() for attachment in message.attachments]

            # Delete the original message
            try:
                await message.delete()
            except discord.errors.Forbidden:
                pass  # Bot lacks permission to delete

            # Send the new message with fixed links and attachments
            await message.channel.send(final_message, files=files if files else None)

    # Respond to trigger words
    trigger_words = ["tuah", "hawk", "the thing"]
    if any(word in message.content.lower() for word in trigger_words):
        await message.channel.send(
            "https://tenor.com/view/marvel-fan4stic-fantastic-four-the-thing-say-that-again-gif-9345984830195785978"
        )

    # 1 in 100 chance response to Max
    if message.author.id == USER_ID_MAX and random.randint(1, 100) == 1:
        await message.channel.send("wowee 1 in 100!")

    await bot.process_commands(message)


@bot.tree.command(name="cpu", description="Show current CPU usage", guild=guild_object)
@is_allowed_user()
async def cpu(interaction: discord.Interaction):
    cpu_usage = psutil.cpu_percent(interval=1)
    await interaction.response.send_message(f"{cpu_usage}%")


@bot.tree.command(name="ip", description="Get public and private IP addresses", guild=guild_object)
@is_allowed_user()
async def ip(interaction: discord.Interaction):
    if interaction.user.id != USER_ID_MAX:
        await interaction.response.send_message("Access denied.", ephemeral=True)
        return

    try:
        public_ip = requests.get("https://api.ipify.org", timeout=10).text
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5)
        private_ip = result.stdout.strip()
        await interaction.response.send_message(f"**Public:** {public_ip}\n**Private:** {private_ip}")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")


@bot.tree.command(name="scan", description="Ping scan for known network ranges", guild=guild_object)
@is_allowed_user()
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        hosts = nm.discover_hosts(NETWORK_RANGES)
        if hosts:
            await interaction.followup.send(f"```\n{chr(10).join(hosts)}```")
        else:
            await interaction.followup.send("No hosts found.")
    except RuntimeError as e:
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="portscan", description="Scan local network for devices and open ports", guild=guild_object)
@is_allowed_user()
async def portscan(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        await interaction.followup.send("Discovering hosts...")
        hosts = nm.discover_hosts(NETWORK_RANGES)

        if not hosts:
            await interaction.followup.send("No hosts found.")
            return

        await interaction.followup.send(f"Found {len(hosts)} hosts. Scanning ports...")
        port_results = nm.scan_ports(hosts)

        for host, ports in port_results.items():
            if ports:
                await interaction.followup.send(f"```\n{host}:\n  {chr(10) + '  '.join(ports)}```")

    except RuntimeError as e:
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="robots", description="Fetch robots.txt from a website", guild=guild_object)
@is_allowed_user()
async def robots(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    # Sanitise and normalise URL
    target = url.replace("https://", "").replace("http://", "").rstrip("/")

    try:
        response = requests.get(f"https://{target}/robots.txt", timeout=10)
        content = response.text

        if not content:
            await interaction.followup.send("Empty or no robots.txt found.")
            return

        # Split into chunks for Discord's 2000 char limit
        chunks = [content[i : i + 1990] for i in range(0, len(content), 1990)]
        for chunk in chunks:
            await interaction.followup.send(f"```\n{chunk}```")

    except requests.RequestException as e:
        await interaction.followup.send(f"Error fetching robots.txt: {e}")


@bot.tree.command(name="tuah", description="Reveal the tuah image", guild=guild_object)
@is_allowed_user()
async def tuah(interaction: discord.Interaction):
    await interaction.response.send_message(
        "https://media.discordapp.net/attachments/625765035754651673/1367451011186429992/IMG_0140.png"
    )


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.DEBUG)
