import discord
from discord.ext import commands
from discord import app_commands

import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

# Configuration


# YouTube and FFmpeg Options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': True}

# Intents setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = commands.Bot(command_prefix='!', intents=intents)


# MusicBot Cog
class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []  # Song queue
        self.volume = 0.5  # Default volume
        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))

    async def play_next(self, guild):
        """Plays the next song in the queue."""
        if self.queue:
            url, title = self.queue.pop(0)
            self.current_song = title  # Update the current song FIRST
            voice_client = guild.voice_client
            try:
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
                )
                source.volume = self.volume
                voice_client.play(
                    source,
                    after=lambda _: asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)
                )
                # Send the now playing message AFTER updating the current song
                await guild.system_channel.send(f"🎵 Now playing: **{self.current_song}**")
            except Exception as e:
                print(f"Error playing song: {e}")
                self.current_song = None  # Reset if playback fails
        else:
            self.current_song = None  # Reset when queue is empty
            await guild.system_channel.send("🎶 Queue is now empty.")

    async def yt_search(self, query):
        """Search YouTube and return the first result."""
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            return info['entries'][0]

    @app_commands.command(name="play", description="Plays a song from a query or URL.")
    async def play(self, interaction: discord.Interaction, search: str):
        """Handles play command for songs."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("🔇 You must be in a voice channel to use this command.", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        await interaction.response.defer(thinking=True)

        try:
            # Connect to VC if not already connected
            if not interaction.guild.voice_client:
                await voice_channel.connect()
            elif interaction.guild.voice_client.channel != voice_channel:
                await interaction.guild.voice_client.move_to(voice_channel)

            # Spotify track handling
            if 'spotify.com/track' in search:
                track_info = self.sp.track(search)
                title = track_info['name']
                artist = track_info['artists'][0]['name']
                search_query = f"{title} {artist}"
                info = await self.yt_search(search_query)
            else:
                info = await self.yt_search(search)

            self.queue.append((info['url'], info['title']))
            if not interaction.guild.voice_client.is_playing():
                await self.play_next(interaction.guild)

            await interaction.followup.send(f"🎶 **Added to queue:** `{info['title']}`")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}")

    @app_commands.command(name="nowplaying", description="Displays the currently playing song.")
    async def now_playing(self, interaction: discord.Interaction):
        """Shows the currently playing song."""
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            if hasattr(self, "current_song") and self.current_song:
                await interaction.response.send_message(f"🎵 **Now Playing:** `{self.current_song}`")
            else:
                await interaction.response.send_message("🎶 A song is playing, but its title is unavailable.")
        else:
            await interaction.response.send_message("⚠️ No music is currently playing.")

    @app_commands.command(name="pause", description="Pauses the current song.")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Music paused.")
        else:
            await interaction.response.send_message("⚠️ No music is currently playing.")

    @app_commands.command(name="resume", description="Resumes the paused song.")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Music resumed.")
        else:
            await interaction.response.send_message("⚠️ No music is paused right now.")

    @app_commands.command(name="queue", description="Displays the current song queue.")
    async def queue_command(self, interaction: discord.Interaction):
        if not self.queue:
            await interaction.response.send_message("🎶 The queue is currently empty.")
        else:
            queue_list = "\n".join([f"{i+1}. {title}" for i, (_, title) in enumerate(self.queue)])
            await interaction.response.send_message(f"📋 **Current Queue:**\n{queue_list}")

    @app_commands.command(name="skip", description="Skips the current song.")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped the current song.")
        else:
            await interaction.response.send_message("⚠️ No song is currently playing.")

    @app_commands.command(name="stop", description="Stops music and clears the queue.")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            self.queue.clear()
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("🛑 Music stopped, and queue cleared.")
        else:
            await interaction.response.send_message("⚠️ I'm not connected to a voice channel.")


# Register Commands
@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    try:
        synced = await client.tree.sync()
        print(f"🔗 Synced {len(synced)} command(s) globally.")
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}")


# Run Bot
async def main():
    async with client:
        await client.add_cog(MusicBot(client))
        await client.start(TOKEN)


asyncio.run(main())
