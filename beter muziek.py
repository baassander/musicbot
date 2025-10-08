import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import itertools
TOKEN = os.getenv("TOKEN")

# Lijst van proxies
proxies_list = [
    "http://38.60.91.60:80",
    "http://213.142.156.97:80",
    "http://193.31.117.184:80",
    "http://158.255.77.168:80",
    "http://41.32.39.7:3128",
    "http://158.255.77.169:80",
    "http://133.18.234.13:80",
    "http://32.223.6.94:80",
    # Voeg hier je andere proxies toe
]

proxy_cycle = itertools.cycle(proxies_list)

# ---------------------
# CONFIG
# ---------------------


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents)

song_queue = []
tasker = None

# ---------------------
# YT-DLP instellingen
# ---------------------
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

# Haal de proxy op via de environment variable 'PROXY'
#proxy = os.getenv("PROXY")  # geeft "http://108.141.130.146:80"

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt',
    'extract_flat': False,
    'geo_bypass': True,   
    'socket_timeout': 60, 
    'retries': 5,  
}

# Voeg de proxy correct toe
if proxy:
    ytdl_format_options['proxy'] = proxy

ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


# ---------------------
# CLASS VOOR AUDIO
# ---------------------
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Onbekend nummer')
        self.duration = data.get('duration', 0)

@classmethod
async def from_url(cls, url, *, stream=True):
    for _ in range(len(proxies_list)):
        proxy = next(proxy_cycle)
        ytdl_format_options['proxy'] = proxy
        ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

        try:
            data = await asyncio.to_thread(ytdl.extract_info, url, download=not stream)
            if 'entries' in data:
                entries = data.get('entries')
                if not entries:
                    raise Exception("Geen resultaten gevonden op YouTube.")
                data = entries[0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

        except Exception as e:
            print(f"Fout met proxy {proxy}: {e}")
            continue

    raise Exception("Alle proxies gefaald, geen verbinding mogelijk.")


# ---------------------
# EVENTS
# ---------------------
@bot.event
async def on_ready():
    print(f"✅ Ingelogd als {bot.user} (ID: {bot.user.id})")
    print("------")


# ---------------------
# COMMANDS
# ---------------------
@bot.command(name='join', help='Laat de bot jouw voice channel joinen')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"✅ Verbonden met **{channel}**")
    else:
        await ctx.send("❌ Je moet eerst in een voice channel zitten!")


@bot.command(name='leave', help='Laat de bot de voice channel verlaten')
async def leave(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("👋 Bot heeft de voice channel verlaten.")
    else:
        await ctx.send("❌ De bot is niet verbonden met een voice channel.")


@bot.command(name='play', aliases=['p'], help='Speel een nummer af van YouTube')
async def play(ctx, *, query: str):
    global song_queue

    if not ctx.author.voice:
        await ctx.send("❌ Je moet in een voice channel zitten om muziek af te spelen!")
        return

    voice_client = ctx.guild.voice_client
    if not voice_client:
        channel = ctx.author.voice.channel
        await channel.connect()

    voice_client = ctx.guild.voice_client

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(query, stream=True)
        except Exception as e:
            await ctx.send(f"⚠️ Er ging iets mis: {e}")
            return

        if not voice_client.is_playing() and len(song_queue) == 0:
            song_queue.append(player)
            await start_playing(ctx, player)
        else:
            song_queue.append(player)
            await ctx.send(f"🎶 Toegevoegd aan queue: **{player.title}**")


async def start_playing(ctx, player):
    global song_queue, tasker
    voice_client = ctx.guild.voice_client

    if not voice_client:
        await ctx.send("❌ Geen voice client gevonden.")
        return

    if len(song_queue) == 0:
        song_queue.append(player)

    current_song = song_queue[0]
    voice_client.play(current_song, after=lambda e: print(f"Player error: {e}") if e else None)
    await ctx.send(f"▶️ Nu aan het spelen: **{current_song.title}**")

    tasker = asyncio.create_task(track_duration(ctx, current_song.duration))


async def track_duration(ctx, duration):
    global song_queue, tasker
    try:
        await asyncio.sleep(duration)
        if len(song_queue) > 0:
            song_queue.pop(0)
        if len(song_queue) > 0:
            await start_playing(ctx, song_queue[0])
        else:
            await ctx.send("✅ Queue is leeg.")
    except asyncio.CancelledError:
        pass


@bot.command(name='skip', help='Sla het huidige nummer over')
async def skip(ctx):
    global tasker
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        if tasker:
            tasker.cancel()
        await ctx.send("⏭️ Nummer overgeslagen.")
    else:
        await ctx.send("❌ Er wordt momenteel niets afgespeeld.")


@bot.command(name='stop', help='Stop alle muziek en leeg de queue')
async def stop(ctx):
    global song_queue, tasker
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
    song_queue.clear()
    if tasker:
        tasker.cancel()
    await ctx.send("⏹️ Alles gestopt en queue leeggemaakt.")


@bot.command(name='pause', help='Pauzeer de muziek')
async def pause(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Muziek gepauzeerd.")
    else:
        await ctx.send("❌ Er speelt momenteel geen muziek.")


@bot.command(name='resume', help='Hervat de muziek')
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Muziek hervat.")
    else:
        await ctx.send("❌ Er is geen gepauzeerde muziek om te hervatten.")


@bot.command(name='queue', help='Bekijk de wachtrij')
async def queue(ctx):
    if len(song_queue) == 0:
        await ctx.send("🎵 De queue is leeg.")
    else:
        msg = "**Queue:**\n"
        for i, song in enumerate(song_queue):
            if i == 0:
                msg += f"▶️ Nu: **{song.title}**\n"
            else:
                msg += f"{i}. {song.title}\n"
        await ctx.send(msg)


# ---------------------
# RUN
# ---------------------
bot.run(TOKEN)











