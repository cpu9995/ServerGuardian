import discord
from discord.ext import commands
import sqlite3
import os
from datetime import datetime
import random
import json
import asyncio
import string
import secrets
import pytz
from datetime import datetime
import datetime

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='!', intents=intents)

from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

script_directory = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists("databases"):
    os.makedirs("databases")

if not os.path.exists("config"):
    os.makedirs("config")

config_file_path = os.path.join("config", 'config.json')
db_audit_path = os.path.join("databases", 'audit_log.db')
db_filter_path = os.path.join("databases", 'bad_words.db')
db_reminders_path = os.path.join("databases", "reminders.db")

try:
    with open(config_file_path, 'r') as config_file:
        config_data = json.load(config_file)
    print("Config loaded successfully.")
except FileNotFoundError:
    print(f"Config file not found at '{config_file_path}'.")
except json.JSONDecodeError as e:
    print(f"Error decoding JSON: {e}")

def initialize_database():
    connection = sqlite3.connect(db_filter_path)
    cursor = connection.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bad_words (
        word TEXT PRIMARY KEY
    )
    """)
    connection.commit()
    connection.close()

def load_bad_words():
    connection = sqlite3.connect(db_filter_path)
    cursor = connection.cursor()
    cursor.execute("SELECT word FROM bad_words")
    bad_words = [row[0] for row in cursor.fetchall()]
    connection.close()
    return bad_words

def save_bad_word(word):
    connection = sqlite3.connect(db_filter_path)
    cursor = connection.cursor()
    cursor.execute("INSERT OR IGNORE INTO bad_words (word) VALUES (?)", (word,))
    connection.commit()
    connection.close()

def has_verified_role(member):
    return any(role.name == "Verified" for role in member.roles)

initialize_database()
filtered_words = load_bad_words()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

    total_members = sum([len(guild.members) for guild in bot.guilds])

    activity = discord.Game(name=f"Protecting {total_members} Users")
    await bot.change_presence(activity=activity)

    bot.start_time = datetime.datetime.utcnow()

last_member_join = None

@bot.event
async def on_member_join(member):
    global last_member_join

    if last_member_join is None:
        last_member_join = datetime.now()
    else:
        time_difference = (datetime.now() - last_member_join).total_seconds()

        account_age_days = (datetime.now() - member.created_at).days
        
        rate_limit_threshold = 10

        ban_threshold_days = 7

        if account_age_days < ban_threshold_days:
            await member.ban(reason="Suspicious account age")
            log_raid_attempt(member.id, "Ban", "Suspicious account age")
        else:
            return

        if time_difference < rate_limit_threshold:
            await member.ban(reason="Possible raid attempt")
            log_raid_attempt(member.id, "Ban", "Possible raid attempt")
        else:
            last_member_join = datetime.now()

    welcome_message = (
        f"Welcome, {member.mention}!\n\n"
        "To gain full access to the server, please use the command '!verify' in the 'verify' text channel to receive the 'Verified' role."
    )
    await member.send(welcome_message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.lower()

    if message.guild is None and content.strip() == "!verify":
        await message.author.send("You can only use '!verify' in the 'verify' text channel. Please join the server you are trying to verify in and use '!verify' in the 'verify' channel.")
        return

    await bot.process_commands(message)

    for word in filtered_words:
        if word in content:
            await message.delete()
            await message.author.send("Your message has been removed due to inappropriate content.")

@bot.command()
async def verify(ctx):
    if ctx.guild is None:
        return

    if has_verified_role(ctx.author):
        await ctx.send(f"{ctx.author.mention} You are already verified.")
        return

    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    if verified_role:
        await ctx.author.add_roles(verified_role)
        await ctx.send(f"{ctx.author.mention} You have been verified and now have the 'Verified' role. You can access the server.")
    else:
        await ctx.send(f"{ctx.author.mention} The 'Verified' role does not exist on this server. Please contact an administrator.")

@bot.command()
async def add_bad_word(ctx, *, word):
    if ctx.message.author.guild_permissions.administrator:
        filtered_words.append(word.lower())
        save_bad_word(word.lower())
        await ctx.send(f"'{word}' has been added to the filter list.")
    else:
        await ctx.send("You do not have permission to add bad words to the filter list.")

@bot.command()
async def ping(ctx):
    latency = bot.latency * 1000
    await ctx.send(f'{ctx.author.mention} Pong! Latency is {latency:.2f} ms')

@bot.command()
async def about(ctx):
    embed = discord.Embed(title="About FZ", description="Author of this bot", color=0x7289DA)
    embed.set_thumbnail(url="https://i.imgur.com/J6e2vVo.jpg")
    embed.add_field(name="Name", value="FZ", inline=True)
    embed.add_field(name="GitHub", value="[GitHub Profile](https://github.com/cpu9995)", inline=True)
    embed.add_field(name="Discord", value="fzee.", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    server = ctx.guild

    embed = discord.Embed(title=f"Server Information - {server.name}", color=0x7289DA)
    
    if server.icon:
        embed.set_thumbnail(url=server.icon_url)
    
    embed.add_field(name="Server ID", value=server.id, inline=True)
    embed.add_field(name="Owner", value=server.owner, inline=True)
    embed.add_field(name="Members", value=server.member_count, inline=True)
    embed.add_field(name="Text Channels", value=len(server.text_channels), inline=True)
    embed.add_field(name="Voice Channels", value=len(server.voice_channels), inline=True)
    embed.add_field(name="Roles", value=len(server.roles), inline=True)
    embed.add_field(name="Created At", value=server.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    embed = discord.Embed(title=f"User Information - {member.display_name}", color=0x7289DA)

    embed.set_thumbnail(url=member.avatar.url)

    embed.add_field(name="User ID", value=member.id, inline=True)
    embed.add_field(name="Username", value=member.name, inline=True)
    embed.add_field(name="Discriminator", value=member.discriminator, inline=True)
    embed.add_field(name="Nickname", value=member.display_name, inline=True)
    embed.add_field(name="Created At", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="Joined At", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, *, member: discord.Member = None):
    if member is None:
        member = ctx.author

    embed = discord.Embed(title=f"Avatar - {member.display_name}", color=0x7289DA)
    embed.set_image(url=member.avatar.url)

    await ctx.send(embed=embed)

@bot.command()
async def clear(ctx, amount: int):
    if ctx.author.guild_permissions.administrator:
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"{amount} messages have been cleared by {ctx.author.mention}.", delete_after=5)
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    if ctx.author.guild_permissions.administrator:
        try:
            await member.kick(reason=reason)
            await ctx.send(f"{member.mention} has been kicked by {ctx.author.mention} for the reason: {reason}.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to kick members.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if ctx.author.guild_permissions.administrator:
        try:
            await member.ban(reason=reason)
            await ctx.send(f"{member.mention} has been banned by {ctx.author.mention} for the reason: {reason}.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to ban members.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def mute(ctx, member: discord.Member, *, reason="No reason provided"):
    if ctx.author.guild_permissions.administrator:
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not muted_role:
            muted_role = await ctx.guild.create_role(name="Muted")

        if ctx.guild.me.guild_permissions.manage_roles:
            try:
                await member.add_roles(muted_role, reason=reason)
                await ctx.send(f"{member.mention} has been muted by {ctx.author.mention} for the reason: {reason}.")
            except discord.Forbidden:
                await ctx.send("I don't have the necessary permissions to manage roles.")
        else:
            await ctx.send("I don't have the necessary permissions to manage roles.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def unmute(ctx, member: discord.Member):
    if ctx.author.guild_permissions.administrator:
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if muted_role:
            if ctx.guild.me.guild_permissions.manage_roles:
                try:
                    await member.remove_roles(muted_role)
                    await ctx.send(f"{member.mention} has been unmuted by {ctx.author.mention}.")
                except discord.Forbidden:
                    await ctx.send("I don't have the necessary permissions to manage roles.")
            else:
                await ctx.send("I don't have the necessary permissions to manage roles.")
        else:
            await ctx.send("The 'Muted' role does not exist on this server.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def checkverification(ctx, member: discord.Member):
    if ctx.author.guild_permissions.administrator:
        verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
        if verified_role and verified_role in member.roles:
            await ctx.send(f"{member.mention} is verified.")
        else:
            await ctx.send(f"{member.mention} is not verified.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Heads", "Tails"])

    await ctx.send(f"{ctx.author.mention} The coin landed on **{result}**!")

@bot.command()
async def invite(ctx):
    if ctx.guild.me.guild_permissions.create_instant_invite:
        invite = await ctx.channel.create_invite(max_age=0, max_uses=1, unique=True)
        await ctx.send(f"Here's the invite link for the server {ctx.author.mention}: {invite.url}")
    else:
        await ctx.send(f"{ctx.author.mention} I don't have permission to create invites in this server.")

@bot.command()
async def suggest(ctx, suggestion):
    server_id = str(ctx.guild.id)

    if server_id in config_data:
        suggestion_channel_id = config_data[server_id]["suggestion_channel_id"]
        
        suggestion_channel = bot.get_channel(suggestion_channel_id)
        
        if suggestion_channel:
            suggestion_embed = discord.Embed(
                title="New Suggestion",
                description=suggestion,
                color=discord.Color.blue()
            )
            suggestion_embed.set_footer(text=f"Submitted by {ctx.author.display_name}")
            
            suggestion_message = await suggestion_channel.send(embed=suggestion_embed)
            
            await ctx.message.delete()
            
            await ctx.send(f"Thank you for your suggestion {ctx.author.mention}! It has been sent for review.")
        else:
            await ctx.send(f"{ctx.author.mention} Suggestion channel not found. Please contact a server administrator.")
    else:
        await ctx.send(f"{ctx.author.mention} Server configuration not found. Please contact a server administrator.")

@bot.command()
async def report(ctx, user: discord.User, *, reason):
    server_id = str(ctx.guild.id)

    if server_id in config_data:
        report_channel_id = config_data[server_id]["report_channel_id"]
        
        report_channel = bot.get_channel(report_channel_id)
        
        if report_channel:
            report_embed = discord.Embed(
                title="New User Report",
                description=f"**Reporter:** {ctx.author.mention}\n"
                            f"**Reported User:** {user.mention}\n"
                            f"**Reason:** {reason}",
                color=discord.Color.red()
            )
            
            report_message = await report_channel.send(embed=report_embed)
            
            await ctx.message.delete()
            
            await ctx.send(f"{ctx.author.mention} Thank you for your report! It has been sent to the administrators for review.")
        else:
            await ctx.send(f"{ctx.author.mention} Report channel not found. Please contact a server administrator.")
    else:
        await ctx.send(f"{ctx.author.mention} Server configuration not found. Please contact a server administrator.")

conn = sqlite3.connect(db_reminders_path)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS reminders
                  (user_id INTEGER, time_minutes INTEGER, message TEXT)''')
conn.commit()

@bot.command()
async def setreminder(ctx, time, *, message):
    try:
        user_id = ctx.author.id
        time_minutes = int(time)
        
        if time_minutes <= 0:
            await ctx.send(f"{ctx.author.mention} Please enter a positive time value for the reminder.")
            return
        
        reminder_time = time_minutes * 60
        
        cursor.execute("INSERT INTO reminders (user_id, time_minutes, message) VALUES (?, ?, ?)",
                       (user_id, time_minutes, message))
        conn.commit()
        
        await ctx.send(f"{ctx.author.mention} Reminder set for {time_minutes} minute(s): {message}")
        await asyncio.sleep(reminder_time)
        
        await ctx.send(f"{ctx.author.mention} Reminder for {time_minutes} minute(s): {message}")
    except ValueError:
        await ctx.send("Please enter a valid time value (in minutes) for the reminder.")

@bot.command()
async def generatepassword(ctx, length: int = 12):
    """Generate a strong random password."""
    
    if length < 6:
        await ctx.send("Password length must be at least 6 characters.")
        return
    
    characters = string.ascii_letters + string.digits + string.punctuation
    
    password = ''.join(secrets.choice(characters) for _ in range(length))
    
    await ctx.send(f"Your generated password is: `{password}`")

@bot.command()
async def addrole(ctx, user: discord.Member, *, role_name: str):
    if ctx.author.guild_permissions.administrator:
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if role:
            if ctx.guild.me.guild_permissions.manage_roles:
                try:
                    await user.add_roles(role)
                    await ctx.send(f"{user.mention} has been assigned the role: {role.name}")
                except discord.Forbidden:
                    await ctx.send("I don't have the necessary permissions to manage roles.")
            else:
                await ctx.send("I don't have the necessary permissions to manage roles.")
        else:
            await ctx.send(f"The role '{role_name}' does not exist on this server.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def removerole(ctx, user: discord.Member, *, role_name: str):
    if ctx.author.guild_permissions.administrator:
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if role:
            if ctx.guild.me.guild_permissions.manage_roles:
                try:
                    await user.remove_roles(role)
                    await ctx.send(f"{role.name} role has been removed from {user.mention}.")
                except discord.Forbidden:
                    await ctx.send("I don't have the necessary permissions to manage roles.")
            else:
                await ctx.send("I don't have the necessary permissions to manage roles.")
        else:
            await ctx.send(f"The role '{role_name}' does not exist on this server.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def createchannel(ctx, channel_name: str):
    if ctx.author.guild_permissions.administrator:
        new_channel = await ctx.guild.create_text_channel(name=channel_name)

        await ctx.send(f"New channel '{new_channel.name}' has been created.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def deletechannel(ctx, channel: discord.TextChannel):
    if ctx.author.guild_permissions.administrator:
        try:
            await channel.delete()
            await ctx.send(f"Channel '{channel.name}' has been deleted.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to delete channels.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def lockdown(ctx, *, reason="Server maintenance"):
    if ctx.author.guild_permissions.administrator:
        await ctx.guild.edit(verification_level=discord.VerificationLevel.high)
        
        for text_channel in ctx.guild.text_channels:
            await text_channel.set_permissions(ctx.guild.default_role, send_messages=False)
        
        lockdown_message = f"🔒 **Server is in lockdown mode!**\n\nReason: {reason}\n\nNo new members can join, and chat is restricted."
        await ctx.send(lockdown_message)
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def unlock(ctx, *, reason="Lockdown lifted"):
    if ctx.author.guild_permissions.administrator:
        await ctx.guild.edit(verification_level=discord.VerificationLevel.low)
        
        for text_channel in ctx.guild.text_channels:
            await text_channel.set_permissions(ctx.guild.default_role, send_messages=True)
        
        unlock_message = f"🔓 **Server lockdown has been lifted!**\n\nReason: {reason}\n\nNew members can join, and chat is restored."
        await ctx.send(unlock_message)
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def prefix(ctx, new_prefix: str):
    if ctx.author.guild_permissions.administrator:
        bot.command_prefix = new_prefix
        await ctx.send(f"Command prefix has been changed to `{new_prefix}`")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def serverstats(ctx):
    if ctx.author.guild_permissions.administrator:
        server = ctx.guild
        
        total_members = server.member_count
        online_members = len([member for member in server.members if member.status != discord.Status.offline])
        
        current_time = datetime.now(pytz.UTC)
        joined_today = len([member for member in server.members if (current_time - member.joined_at).days == 0])
        joined_this_week = len([member for member in server.members if (current_time - member.joined_at).days <= 7])
        joined_this_month = len([member for member in server.members if (current_time - member.joined_at).days <= 30])
        
        embed = discord.Embed(title=f"Server Statistics - {server.name}", color=0x7289DA)
        embed.add_field(name="Total Members", value=total_members, inline=True)
        embed.add_field(name="Online Members", value=online_members, inline=True)
        embed.add_field(name="Members Joined Today", value=joined_today, inline=True)
        embed.add_field(name="Members Joined This Week", value=joined_this_week, inline=True)
        embed.add_field(name="Members Joined This Month", value=joined_this_month, inline=True)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def listreports(ctx):
    if ctx.author.guild_permissions.administrator:
        server_id = str(ctx.guild.id)

        if server_id in config_data:
            report_channel_id = config_data[server_id]["report_channel_id"]
            
            report_channel = bot.get_channel(report_channel_id)
            
            if report_channel:
                reports = []
                
                async for message in report_channel.history(limit=None):
                    if message.embeds:
                        for embed in message.embeds:
                            if "Report" in embed.to_dict().get("title", ""):
                                reports.append(embed.to_dict().get("description", ""))
                
                if reports:
                    reports_message = "Recent user reports:\n\n" + "\n\n".join(reports)
                else:
                    reports_message = "No recent user reports found."
                await ctx.send(reports_message)
            else:
                await ctx.send(f"{ctx.author.mention} Report channel not found. Please contact a server administrator.")
        else:
            await ctx.send(f"{ctx.author.mention} Server configuration not found. Please contact a server administrator.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def deletereport(ctx, report_id: int):
    if ctx.author.guild_permissions.administrator:
        server_id = str(ctx.guild.id)

        if server_id in config_data:
            report_channel_id = config_data[server_id]["report_channel_id"]

            report_channel = bot.get_channel(report_channel_id)

            if report_channel:
                message = await report_channel.fetch_message(report_id)

                if message:
                    await message.delete()
                    await ctx.send(f"Report with ID {report_id} has been deleted.")
                else:
                    await ctx.send(f"Report with ID {report_id} not found.")
            else:
                await ctx.send(f"Report channel not found. Please contact a server administrator.")
        else:
            await ctx.send(f"Server configuration not found. Please contact a server administrator.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def poll(ctx, question, *options):
    if len(options) < 2:
        await ctx.send("Please provide at least two options for the poll.")
        return

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

    poll_message = f"**{question}**\n\n"

    for i, option in enumerate(options):
        if i < len(emojis):
            poll_message += f"{emojis[i]} {option}\n"
        else:
            break

    poll_embed = discord.Embed(title="Poll", description=poll_message, color=0x7289DA)
    poll_embed.set_footer(text=f"Poll created by {ctx.author.display_name}")
    poll = await ctx.send(embed=poll_embed)

    for i in range(len(options)):
        if i < len(emojis):
            await poll.add_reaction(emojis[i])

@bot.command()
async def survey(ctx, question, *options):
    if len(options) < 2:
        await ctx.send("Please provide at least two options for the survey question.")
        return

    survey_message = f"**Survey Question:** {question}\n\n"

    for i, option in enumerate(options):
        survey_message += f"{i+1}. {option}\n"

    survey_embed = discord.Embed(title="Survey", description=survey_message, color=0x7289DA)
    survey_embed.set_footer(text=f"Survey created by {ctx.author.display_name}")
    survey = await ctx.send(embed=survey_embed)

    for i in range(len(options)):
        await survey.add_reaction(str(i + 1))

@bot.command()
async def announce(ctx, *, message):
    if ctx.author.guild_permissions.administrator:
        server_id = str(ctx.guild.id)

        if server_id in config_data:
            announcement_channel_id = config_data[server_id].get('announcement_channel_id')

            if announcement_channel_id:
                announcement_channel = ctx.guild.get_channel(int(announcement_channel_id))

                if announcement_channel is not None:
                    embed = discord.Embed(title="Announcement", description=message, color=0x7289DA)

                    announcement_message = await announcement_channel.send(embed=embed)
                    await ctx.send("Announcement sent successfully.")

                    emojis = ["❤️", "👍", "👏", "🎉", "🔥"]

                    for emoji in emojis:
                        await announcement_message.add_reaction(emoji)
                else:
                    await ctx.send("The announcement channel does not exist or the ID is incorrect.")
            else:
                await ctx.send("The announcement_channel_id is not specified in the config.json file for this server.")
        else:
            await ctx.send("Server configuration not found. Please contact a server administrator.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def slowmode(ctx, channel: discord.TextChannel, duration: int):
    if ctx.author.guild_permissions.administrator:
        try:
            await channel.edit(slowmode_delay=duration)
            await ctx.send(f"Slow mode has been enabled in {channel.mention} for {duration} seconds.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to edit slow mode in this channel.")
    else:
        await ctx.send("You do not have permission to use this command.")

@bot.command()
async def uptime(ctx):
    current_time = datetime.datetime.utcnow()
    uptime = current_time - bot.start_time

    uptime_str = str(uptime).split(".")[0]

    embed = discord.Embed(
        title="ServerGuardian Uptime",
        description=f"ServerGuardian has been online for: {uptime_str}",
        color=0x7289DA
    )

    embed.set_thumbnail(url=bot.user.avatar)

    await ctx.send(embed=embed)

def initialize_raid_log_database():
    connection = sqlite3.connect(db_audit_path)
    cursor = connection.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raid_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP,
        user_id INTEGER,
        action TEXT,
        details TEXT
    )
    """)
    connection.commit()
    connection.close()

def log_raid_attempt(user_id, action, details):
    connection = sqlite3.connect(db_audit_path)
    cursor = connection.cursor()
    cursor.execute("INSERT INTO raid_log (timestamp, user_id, action, details) VALUES (CURRENT_TIMESTAMP, ?, ?, ?)", (user_id, action, details))
    connection.commit()
    connection.close()

bot.run(BOT_TOKEN)