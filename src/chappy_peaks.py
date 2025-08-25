
# @bot.event
# async def on_presence_update(before, after):
#     if before.id == CHAPPY:
#         if str(before.status) != "online" and str(after.status) == "online":
#             last_peak_time = get_last_peak_time()
#             update_total_peaks()
#
#             if last_peak_time:
#                 last_peak_dt = datetime.strptime(last_peak_time, "%Y-%m-%d %H:%M:%S.%f")
#                 time_since_last_peak = datetime.now() - last_peak_dt
#                 time_since_last_peak_str = str(time_since_last_peak).split('.')[0]  # Remove microseconds
#             else:
#                 time_since_last_peak_str = "N/A"
#             channel = discord.utils.get(after.guild.text_channels, name="white-pilled-hopecore")  # Replace with your channel name
#             if channel:
#                 nice_format_start_date = datetime.strptime(get_start_date(), "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%y")
#                 await channel.send(
#                     f"{after.name} alert! {get_total_peaks()} total peaks since {nice_format_start_date}! "
#                     f"time since last peak: {time_since_last_peak_str}."
#                 )

# @filter_disallowed_users
# @bot.tree.command(name="chappy_peaks", description="Get the total peaks and time since last peak", guild=discord.Object(id=GUILD_ID))
# async def chappy_peaks(interaction: discord.Interaction):
#     msg = f"{get_total_peaks()}. Last peak was {get_last_peak_time()}."
#     await interaction.response.send_message(msg)