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
from discord.ext import commands, tasks

import nmap as nm
from eb import get_new_listings, EbayAuthError, EbayAPIError

dotenv.load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(id) for id in os.getenv("GUILD_IDS", "").split(",") if id]
USER_ID_CHAPPY = int(os.getenv("USER_ID_CHAPPY", 0))
USER_ID_JOSH = int(os.getenv("USER_ID_JOSH", 0))
USER_ID_MAX = int(os.getenv("USER_ID_MAX", 0))
PRIVATE_SERVER_BOT_CHANNEL_ID = int(os.getenv("PRIVATE_SERVER_BOT_CHANNEL_ID", 0))

BLOCKED_USERS = {USER_ID_JOSH}
NETWORK_RANGES = ["192.168.5.0/24", "192.168.1.0/24"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="/", intents=intents)

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")


def is_allowed_user():
    """Check decorator to restrict commands - blocks specific users."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in BLOCKED_USERS:
            await interaction.response.send_message(
                "https://tenor.com/view/no-i-dont-think-i-will-captain-america-old-capt-gif-17162888", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


# @tasks.loop(seconds=10)
@tasks.loop(minutes=5)
async def check_ebay():
    channel = bot.get_channel(PRIVATE_SERVER_BOT_CHANNEL_ID)
    if not channel:
        logging.error("eBay channel not found")
        return

    try:
        listings = get_new_listings()

        for listing in listings:
            embed = discord.Embed(
                title=listing["title"],
                url=listing["url"],
                color=0x00ff00
            )
            embed.add_field(name="Price", value=listing["price"], inline=True)

            if listing["delivery"]:
                delivery = listing["delivery"]
                delivery_text = delivery["cost"]
                if delivery["min_date"] and delivery["max_date"]:
                    delivery_text += f" ({delivery['min_date']} - {delivery['max_date']})"
                embed.add_field(name="Delivery", value=delivery_text, inline=True)

            if listing["image"]:
                embed.set_thumbnail(url=listing["image"])

            await channel.send(embed=embed)

    except EbayAuthError as e:
        embed = discord.Embed(
            title="⚠️ eBay Authentication Error",
            description=str(e),
            color=0xff0000
        )
        await channel.send(embed=embed)
        logging.error(f"eBay auth error: {e}")

    except EbayAPIError as e:
        embed = discord.Embed(
            title="⚠️ eBay API Error",
            description=str(e),
            color=0xff9900
        )
        await channel.send(embed=embed)
        logging.error(f"eBay API error: {e}")

    except Exception as e:
        embed = discord.Embed(
            title="❌ eBay Check Failed",
            description=f"Unexpected error: {type(e).__name__}",
            color=0xff0000
        )
        await channel.send(embed=embed)
        logging.exception("Unexpected error in check_ebay")


@check_ebay.before_loop
async def before_check_ebay():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    for guild_id in GUILD_IDS:
        await bot.tree.sync(guild=discord.Object(id=guild_id))
    print(f"Logged in as {bot.user.name} ({bot.user.id})")

    if not check_ebay.is_running():
        check_ebay.start()


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

    trigger_words = ["tuah", "hawk", "the thing", "67"]
    if any(word in message.content.lower() for word in trigger_words):
        await message.channel.send(
            "https://tenor.com/view/marvel-fan4stic-fantastic-four-the-thing-say-that-again-gif-9345984830195785978"
        )

    if message and random.randint(1, 1000) == 1:
        await message.channel.send("1 in 1000!")

    await bot.process_commands(message)


@bot.tree.command(name="cpu", description="Show current CPU usage")
@is_allowed_user()
async def cpu(interaction: discord.Interaction):
    cpu_usage = psutil.cpu_percent(interval=1)
    await interaction.response.send_message(f"{cpu_usage}%")


@bot.tree.command(name="ip", description="Get public and private IP addresses")
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


@bot.tree.command(name="scan", description="Ping scan for known network ranges")
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


@bot.tree.command(name="portscan", description="Scan local network for devices and open ports")
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


@bot.tree.command(name="robots", description="Fetch robots.txt from a website")
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
        chunks = [content[i: i + 1990] for i in range(0, len(content), 1990)]
        for chunk in chunks:
            await interaction.followup.send(f"```\n{chunk}```")

    except requests.RequestException as e:
        await interaction.followup.send(f"Error fetching robots.txt: {e}")


@bot.tree.command(name="tuah", description="Reveal the tuah image")
@is_allowed_user()
async def tuah(interaction: discord.Interaction):
    await interaction.response.send_message(
        "https://media.discordapp.net/attachments/625765035754651673/1367451011186429992/IMG_0140.png"
    )


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.DEBUG)
