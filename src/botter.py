import logging
import os
import random
import re
import subprocess
from datetime import time

import discord
import dotenv
import psutil
import requests
from discord import app_commands
from discord.ext import commands, tasks

import nmap as nm
from eb import get_new_listings, EbayAuthError, EbayAPIError
from planes import get_nearby_aircraft

dotenv.load_dotenv()

# Configure logging to file only
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(id) for id in os.getenv("GUILD_IDS", "").split(",") if id]
USER_ID_CHAPPY = int(os.getenv("USER_ID_CHAPPY", 0))
USER_ID_JOSH = int(os.getenv("USER_ID_JOSH", 0))
USER_ID_MAX = int(os.getenv("USER_ID_MAX", 0))
PRIVATE_SERVER_BOT_CHANNEL_ID = int(os.getenv("PRIVATE_SERVER_BOT_CHANNEL_ID", 0))
GENERAL_G_CHANNEL_ID = int(os.getenv("GENERAL_G_CHANNEL_ID", 0))
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

logger.info("Configuration loaded")
logger.debug(f"Guild IDs: {GUILD_IDS}")
logger.debug(f"Bot channel ID: {PRIVATE_SERVER_BOT_CHANNEL_ID}")
logger.debug(f"General channel ID: {GENERAL_G_CHANNEL_ID}")

BLOCKED_USERS = {USER_ID_JOSH}
NETWORK_RANGES = ["192.168.5.0/24", "192.168.1.0/24"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="/", intents=intents)

handler = logging.FileHandler(filename="logs.log", encoding="utf-8", mode="a")


def fetch_weather():
    logger.info("Fetching weather data for Maidstone")
    url = f"http://api.openweathermap.org/data/2.5/forecast?q=Maidstone,GB&appid={OPENWEATHER_API_KEY}&units=metric"

    with requests.Session() as session:
        logger.debug(f"Sending weather API request to {url}")
        resp = session.get(url)
        logger.debug(f"Weather API response status code: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"Weather API returned {resp.status_code}")
            return None
        data = resp.json()

    forecasts = data['list'][:8]  # next 24h
    logger.debug(f"Processing {len(forecasts)} forecast entries")

    high = max(f['main']['temp_max'] for f in forecasts)
    low = min(f['main']['temp_min'] for f in forecasts)
    current = forecasts[0]['weather'][0]['description'].title()
    rain_expected = any('rain' in f['weather'][0]['main'].lower() for f in forecasts)
    logger.debug(f"Weather stats: High={high}°C, Low={low}°C, Current={current}, Rain={rain_expected}")

    # build hourly breakdown (3-hour intervals)
    hourly_lines = []
    for f in forecasts[:6]:  # next 18 hours
        time_str = f['dt_txt'].split(' ')[1][:5]  # "09:00"
        temp = f['main']['temp']
        icon = "🌧️" if 'rain' in f['weather'][0]['main'].lower() else "☀️"
        hourly_lines.append(f"`{time_str}` {icon} {temp:.0f}°C")

    embed = discord.Embed(
        title="☀️ Weather for Maidstone",
        color=0x5dadec
    )
    embed.add_field(name="Now", value=current, inline=False)
    embed.add_field(name="High", value=f"{high:.0f}°C", inline=True)
    embed.add_field(name="Low", value=f"{low:.0f}°C", inline=True)
    embed.add_field(name="Forecast", value="\n".join(hourly_lines), inline=False)

    if rain_expected:
        embed.add_field(name="⚠️", value="Rain expected today", inline=False)

    logger.info("Weather embed created successfully")
    return embed


@tasks.loop(time=time(hour=7, minute=0))
async def daily_weather():
    logger.info("Running daily weather task")
    channel = bot.get_channel(GENERAL_G_CHANNEL_ID)
    if not channel:
        logger.error(f"Weather channel not found: {GENERAL_G_CHANNEL_ID}")
        return

    logger.debug(f"Weather channel found: {channel.name}")
    weather_embed = fetch_weather()
    if weather_embed:
        await channel.send(embed=weather_embed)
        logger.info("Daily weather message sent successfully")
    else:
        logger.warning("Weather embed was None, skipping send")


@daily_weather.before_loop
async def before_daily_weather():
    await bot.wait_until_ready()


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
    logger.info("Running eBay check task")
    channel = bot.get_channel(PRIVATE_SERVER_BOT_CHANNEL_ID)
    if not channel:
        logger.error(f"eBay channel not found: {PRIVATE_SERVER_BOT_CHANNEL_ID}")
        return

    logger.debug(f"eBay channel found: {channel.name}")

    try:
        logger.debug("Calling get_new_listings()")
        listings = get_new_listings()
        logger.info(f"Received {len(listings)} new listings from eBay")

        for idx, listing in enumerate(listings, 1):
            logger.debug(f"Processing listing {idx}/{len(listings)}: {listing['title']}")
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
            logger.debug(f"Sent listing {idx} to Discord")

        if listings:
            logger.info(f"Successfully posted {len(listings)} eBay listings")
        else:
            logger.info("No new eBay listings to post")

    except EbayAuthError as e:
        logger.error(f"eBay auth error: {e}", exc_info=True)
        embed = discord.Embed(
            title="⚠️ eBay Authentication Error",
            description=str(e),
            color=0xff0000
        )
        await channel.send(embed=embed)

    except EbayAPIError as e:
        logger.error(f"eBay API error: {e}", exc_info=True)
        embed = discord.Embed(
            title="⚠️ eBay API Error",
            description=str(e),
            color=0xff9900
        )
        await channel.send(embed=embed)

    except Exception as e:
        logger.exception("Unexpected error in check_ebay")
        embed = discord.Embed(
            title="❌ eBay Check Failed",
            description=f"Unexpected error: {type(e).__name__}",
            color=0xff0000
        )
        await channel.send(embed=embed)


@check_ebay.before_loop
async def before_check_ebay():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    logger.info("Bot is ready, starting initialization")
    logger.debug(f"Commands in tree before sync: {[cmd.name for cmd in bot.tree.get_commands()]}")
    logger.info("Syncing commands with Discord...")

    # Copy global commands to each guild
    for guild_id in GUILD_IDS:
        logger.debug(f"Syncing commands for guild {guild_id}")
        guild_obj = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        logger.info(f"Guild ID {guild_id}: Synced {len(synced)} commands - {[cmd.name for cmd in synced]}")

    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")

    if not check_ebay.is_running():
        logger.info("Starting eBay check task")
        check_ebay.start()
    else:
        logger.debug("eBay check task already running")

    if not daily_weather.is_running():
        logger.info("Starting daily weather task")
        daily_weather.start()
    else:
        logger.debug("Daily weather task already running")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    logger.debug(f"Message received from {message.author.name} ({message.author.id}): {message.content[:50]}")

    if message.author.id == USER_ID_JOSH:
        logger.debug(f"Adding reactions to Josh's message")
        for emoji in ["🇬", "0️⃣", "🇴", "🇳"]:
            await message.add_reaction(emoji)

    if "x.com/" in message.content:
        logger.info(f"Detected x.com link in message from {message.author.name}")
        x_links = re.findall(r"https?://(?:www\.)?x\.com/\S+", message.content)
        if x_links:
            logger.debug(f"Found {len(x_links)} x.com links, converting to fixupx")
            new_content = re.sub(r"https?://(?:www\.)?x\.com/", "https://fixupx.com/", message.content)

            new_content = re.sub(r"\?s=[^\s]*", "", new_content)

            final_message = f"{message.author.mention}: {new_content}"

            files = [await attachment.to_file() for attachment in message.attachments]

            try:
                await message.delete()
                logger.debug("Original message deleted")
            except discord.errors.Forbidden:
                logger.warning("Could not delete original message (forbidden)")
                pass

            await message.channel.send(final_message, files=files if files else None)
            logger.info("Sent fixupx replacement message")

    if message and random.randint(1, 1000) == 1:
        logger.info("Random 1 in 1000 event triggered!")
        await message.channel.send("1 in 1000!")

    await bot.process_commands(message)


@bot.tree.command(name="fr", description="Show aircraft currently flying nearby")
#@is_allowed_user()
async def fr(interaction: discord.Interaction):
    logger.info(f"Command /fr invoked by {interaction.user.name} ({interaction.user.id})")
    await interaction.response.defer()

    try:
        logger.debug("Fetching nearby aircraft data")
        aircraft_list = get_nearby_aircraft(51.254038, 0.437667, radius_km=15)
        logger.debug(f"Found {len(aircraft_list) if aircraft_list else 0} aircraft")

        if not aircraft_list:
            logger.info("No aircraft found nearby")
            await interaction.followup.send("No aircraft detected nearby.")
            return

        lines = []
        for ac in aircraft_list:
            callsign = (ac[1] or "").strip() or "Unknown"
            origin_country = ac[2] or "?"
            altitude = ac[7]
            velocity = ac[9]
            vertical_rate = ac[11]  # meters/second

            alt_ft = int(altitude * 3.281) if altitude else "?"
            spd_kts = int(velocity * 1.944) if velocity else "?"

            # Calculate climb/descent indicator
            climb_indicator = ""
            if vertical_rate:
                if vertical_rate > 0.5:
                    climb_indicator = " ↗"
                elif vertical_rate < -0.5:
                    climb_indicator = " ↘"

            # Create FlightRadar24 link if we have a valid callsign
            if callsign != "Unknown":
                fr_link = f"https://www.flightradar24.com/{callsign}"
                lines.append(f"✈️ **[{callsign}]({fr_link})** ({origin_country}) - {alt_ft}ft, {spd_kts}kts{climb_indicator}")
            else:
                lines.append(f"✈️ **{callsign}** ({origin_country}) - {alt_ft}ft, {spd_kts}kts{climb_indicator}")

        response = "\n".join(lines)
        if len(response) > 1900:
            response = "\n".join(lines[:20]) + f"\n\n*...and {len(lines) - 20} more*"
            logger.debug("Response truncated due to length")

        await interaction.followup.send(response)
        logger.info(f"Sent aircraft list with {len(lines)} aircraft to {interaction.user.name}")
    except Exception as e:
        logger.error(f"Error in /fr command: {e}", exc_info=True)
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="cpu", description="Show current CPU usage")
@is_allowed_user()
async def cpu(interaction: discord.Interaction):
    logger.info(f"Command /cpu invoked by {interaction.user.name} ({interaction.user.id})")
    cpu_usage = psutil.cpu_percent(interval=1)
    logger.debug(f"CPU usage: {cpu_usage}%")
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
    logger.info(f"Command /scan invoked by {interaction.user.name} ({interaction.user.id})")
    await interaction.response.defer()
    if interaction.user.id != USER_ID_MAX:
        logger.warning(f"User {interaction.user.name} denied access to /scan command")
        await interaction.response.send_message("Access denied.", ephemeral=True)
        return

    try:
        logger.debug(f"Starting network scan on ranges: {NETWORK_RANGES}")
        hosts = nm.discover_hosts(NETWORK_RANGES)
        logger.info(f"Scan completed, found {len(hosts) if hosts else 0} hosts")
        if hosts:
            await interaction.followup.send(f"```\n{chr(10).join(hosts)}```")
        else:
            await interaction.followup.send("No hosts found.")
    except RuntimeError as e:
        logger.error(f"Error in /scan command: {e}", exc_info=True)
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="portscan", description="Scan local network for devices and open ports")
@is_allowed_user()
async def portscan(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.user.id != USER_ID_MAX:
        await interaction.response.send_message("Access denied.", ephemeral=True)
        return

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

    target = url.replace("https://", "").replace("http://", "").rstrip("/")

    try:
        response = requests.get(f"https://{target}/robots.txt", timeout=10)
        content = response.text

        if not content:
            await interaction.followup.send("Empty or no robots.txt found.")
            return

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


@bot.tree.command(name="weather", description="Get current weather for Maidstone")
@is_allowed_user()
async def weather(interaction: discord.Interaction):
    logger.info(f"Command /weather invoked by {interaction.user.name} ({interaction.user.id})")
    await interaction.response.defer()

    weather_embed = fetch_weather()
    if weather_embed:
        await interaction.followup.send(embed=weather_embed)
        logger.info(f"Weather data sent to {interaction.user.name}")
    else:
        logger.warning("Failed to fetch weather data")
        await interaction.followup.send("Failed to fetch weather data.")


if __name__ == "__main__":
    logger.info("Starting Discord bot")
    bot.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.DEBUG)
