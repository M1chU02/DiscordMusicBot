import discord
from discord.ext import commands
import yt_dlp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': True}

class MusicBot(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.queue = []
        self.current_song = None
    
    @commands.command()
    async def play(self, ctx, *, search):
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("You're not in a voice channel")
        
        if not ctx.voice_client:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)

        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)
                    if 'entries' in info:
                        info = info['entries'][0]
                    url = info['url']
                    title = info['title']
                    self.queue.append((url, title))
                    await ctx.send(f'Added to queue: **{title}**')
                except Exception as e:
                    await ctx.send(f"Error occurred: {str(e)}")
                    return
        
        if not ctx.voice_client.is_playing() and not self.current_song:
            await self.play_next(ctx)

    async def play_next(self, ctx):
        if self.queue:
            url, title = self.queue.pop(0)
            self.current_song = title
            try:
                source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
                ctx.voice_client.play(source, after=lambda _: self.client.loop.create_task(self.on_song_end(ctx)))
                await ctx.send(f'Now playing: **{title}**')
            except Exception as e:
                await ctx.send(f"Failed to play: **{title}**\nError: {str(e)}")
                self.current_song = None
                await self.play_next(ctx)  # Attempt to play the next song if one fails
        else:
            self.current_song = None
            await ctx.send('Queue is empty, leaving the voice channel.')
            await ctx.voice_client.disconnect()

    async def on_song_end(self, ctx):
        self.current_song = None
        if self.queue:
            await self.play_next(ctx)

    @commands.command()
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send('Skipped')

    @commands.command()
    async def queue(self, ctx):
        if self.queue:
            queue_list = '\n'.join([f"{idx + 1}. {title}" for idx, (_, title) in enumerate(self.queue)])
            await ctx.send(f"Current Queue:\n{queue_list}")
        else:
            await ctx.send("The queue is empty.")

client = commands.Bot(command_prefix='!', intents=intents)

async def main():
    await client.add_cog(MusicBot(client))
    await client.start('token')

asyncio.run(main())
