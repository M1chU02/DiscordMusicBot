import discord
from discord.ext import commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.reactions = True

FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': True}

class MusicBot(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.queue = []
        self.current_song = None
        self.volume = 0.3
        self.now_playing_message = None
        self.playlist_extractor_task = None

        spotify_client_id = os.getenv('spotify_client_id')
        spotify_client_secret = os.getenv('spotify_client_secret')

        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=spotify_client_id, client_secret=spotify_client_secret))

    @commands.command()
    async def play(self, ctx, *, search):
        """Plays a song or playlist from a text/url"""
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("You're not in a voice channel")
        
        if not ctx.voice_client:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)

        async with ctx.typing():
            try:
                if 'spotify.com/track' in search:
                    track_info = self.sp.track(search)
                    title = track_info['name']
                    artist = track_info['artists'][0]['name']
                    search_query = f"{title} {artist}"
                    info = await self.yt_search(search_query)
                    url = info['url']
                    title = info['title']
                    self.queue.append((url, title))
                    await ctx.send(f'🎶 **Added to queue:** `{title}`')
                elif 'spotify.com/playlist' in search:
                    playlist_info = self.sp.playlist_tracks(search)
                    await ctx.send(f'🎶 **Processing Spotify playlist...**')
                    first = True
                    for item in playlist_info['items']:
                        track = item['track']
                        title = track['name']
                        artist = track['artists'][0]['name']
                        search_query = f"{title} {artist}"
                        info = await self.yt_search(search_query)
                        url = info['url']
                        self.queue.append((url, title))
                        if first and not ctx.voice_client.is_playing():
                            await self.play_next(ctx)
                            first = False
                    await ctx.send(f'🎶 **Added Spotify playlist to queue**')
                else:
                    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                        if 'youtube.com/playlist' in search or '&list=' in search:
                            info = ydl.extract_info(search, download=False)
                            self.playlist_extractor_task = asyncio.create_task(self.process_playlist(ctx, info['entries']))
                            await ctx.send(f'🎶 **Processing playlist...**')
                        else:
                            info = ydl.extract_info(f"ytsearch:{search}", download=False)
                            if 'entries' in info:
                                info = info['entries'][0]
                            url = info['url']
                            title = info['title']
                            self.queue.append((url, title))
                            await ctx.send(f'🎶 **Added to queue:** `{title}`')
            except Exception as e:
                await ctx.send(f"Error occurred: {str(e)}")
                return

        if not ctx.voice_client.is_playing() and not self.current_song:
            await self.play_next(ctx)

    async def yt_search(self, query):
        """Searches YouTube for the query and returns the first result."""
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            if 'entries' in info:
                return info['entries'][0]

    async def process_playlist(self, ctx, entries):
        """Process each song in the playlist one by one."""
        first = True
        for entry in entries:
            if not entry:
                continue
            try:
                url = entry['url']
                title = entry['title']
                self.queue.append((url, title))
                if first and not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                    first = False
            except Exception as e:
                await ctx.send(f"Skipping a song due to an error: {str(e)}")
        
    async def play_next(self, ctx):
        if self.queue:
            url, title = self.queue.pop(0)
            self.current_song = title
            try:
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS))
                source.volume = self.volume
                ctx.voice_client.play(source, after=lambda _: self.client.loop.create_task(self.on_song_end(ctx)))
                
                if self.now_playing_message:
                    await self.now_playing_message.delete()
                self.now_playing_message = await ctx.send(f'🎵 **Now playing:** `{title}` | Volume: `{int(self.volume * 100)}%`')
                reactions = ['⏸️', '▶️', '⏭️', '🔉', '🔊', '🛑']
                for reaction in reactions:
                    await self.now_playing_message.add_reaction(reaction)
                    
            except Exception as e:
                await ctx.send(f"Failed to play: **{title}**\nError: {str(e)}")
                self.current_song = None
                await self.play_next(ctx) 
        else:
            self.current_song = None
            await ctx.send('Queue is empty, leaving the voice channel.')
            await ctx.voice_client.disconnect()

    async def on_song_end(self, ctx):
        self.current_song = None
        if self.queue:
            await self.play_next(ctx)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not self.now_playing_message or reaction.message.id != self.now_playing_message.id:
            return

        guild = reaction.message.guild  
        voice_client = guild.voice_client  

        if not voice_client:
            return
    
        try:
            if reaction.emoji == '⏸️':
                await self.pause(reaction.message)
            elif reaction.emoji == '▶️':
                await self.resume(reaction.message)
            elif reaction.emoji == '⏭️':
                await self.skip(reaction.message)
            elif reaction.emoji == '🔉':
                await self.volume_down(reaction.message)
            elif reaction.emoji == '🔊':
                await self.volume_up(reaction.message)
            elif reaction.emoji == '🛑':
                await self.stop(reaction.message)
        
            await reaction.remove(user)
        except Exception as e:
            print(f"Error handling reaction: {str(e)}")

    @commands.command()
    async def skip(self, ctx):
        """Plays next song."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send('⏭️ Skipped the current song.')

    @commands.command()
    async def stop(self, ctx):
        """Stops the bot and clears the queue."""
        if ctx.voice_client:
            self.queue.clear()
            if self.playlist_extractor_task:
                self.playlist_extractor_task.cancel()  # Stop playlist processing
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send('🛑 Stopped the music and left the voice channel.')

    @commands.command()
    async def queue(self, ctx):
        """Displays queue."""
        if self.queue:
            queue_list = '\n'.join([f"{idx + 1}. `{title}`" for idx, (_, title) in enumerate(self.queue)])
            await ctx.send(f"🎶 **Current Queue:**\n{queue_list}")
        else:
            await ctx.send("The queue is empty.")

    @commands.command()
    async def pause(self, ctx):
        """Pauses the current song."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send('⏸️ Paused the song.')
        else:
            await ctx.send('No song is currently playing.')

    @commands.command()
    async def resume(self, ctx):
        """Resumes the paused song."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send('▶️ Resumed the song.')
        else:
            await ctx.send('No song is currently paused.')

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Sets the volume of the bot (0-100)."""
        if 0 <= volume <= 100:
            self.volume = volume / 100
            if ctx.voice_client and ctx.voice_client.source:
                ctx.voice_client.source.volume = self.volume
            await ctx.send(f'🔊 Volume set to `{volume}%`')
        else:
            await ctx.send('Please enter a value between 0 and 100.')

    @commands.command()
    async def volume_up(self, ctx, increment: int = 10):
        """Increases the volume by a specified increment (default 10%)."""
        new_volume = min(self.volume * 100 + increment, 100)
        await self.volume(ctx, int(new_volume))

    @commands.command()
    async def volume_down(self, ctx, decrement: int = 10):
        """Decreases the volume by a specified decrement (default 10%)."""
        new_volume = max(self.volume * 100 - decrement, 0)
        await self.volume(ctx, int(new_volume))

    @commands.command()
    async def now_playing(self, ctx):
        """Displays the currently playing song."""
        if self.current_song:
            await ctx.send(f'🎵 **Currently playing:** `{self.current_song}` | Volume: `{int(self.volume * 100)}%`')
        else:
            await ctx.send('No song is currently playing.')

client = commands.Bot(command_prefix='!', intents=intents)

async def main():
    await client.add_cog(MusicBot(client))
    await client.start(os.getenv('discord_bot_token'))

asyncio.run(main())
