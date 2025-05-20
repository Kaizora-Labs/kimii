import os
import time
import discord
from discord.ext import commands, tasks
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

COLOR_PINK = 0xFF69B4


user_memory = {}
MEMORY_DURATION = timedelta(hours=1)  


def get_latency_quality(latency_ms: int) -> str:
    if latency_ms <= 100:
        return "Wow Speedy!!"
    elif latency_ms <= 200:
        return "Hmm not bad"
    else:
        return "What the hell???"


async def send_ping_embed(ctx_or_interaction, latency_ms: int, api_rt_ms: int):
    quality = get_latency_quality(latency_ms)

    embed = discord.Embed(
        title="⚡ My Networkk!",
        description=(
            f"**Latency:** `{latency_ms} ms`\n                              ({quality})\n\n "
            f"**API Round-Trip:** `{api_rt_ms}` ms "
        ),
        color=COLOR_PINK
    )
    embed.set_footer(text="© Kaizora Labs")

    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed)
    elif isinstance(ctx_or_interaction, discord.abc.Messageable):
        await ctx_or_interaction.send(embed=embed)
    else:
        await ctx_or_interaction.send(embed=embed)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game("with you"))
    await bot.tree.sync()
    cleanup_memory.start()
    print("Slash commands synced.")


@bot.tree.command(name="ping", description="Check bot latency")
async def ping_slash(interaction: discord.Interaction):
    start = time.perf_counter()
    latency_ms = round(bot.latency * 1000)
    api_rt_ms = round((time.perf_counter() - start) * 1000)
    await send_ping_embed(interaction, latency_ms, api_rt_ms)


@bot.command(name="ping")
async def ping_prefix(ctx: commands.Context):
    start = time.perf_counter()
    latency_ms = round(bot.latency * 1000)
    api_rt_ms = round((time.perf_counter() - start) * 1000)
    await send_ping_embed(ctx, latency_ms, api_rt_ms)


def store_user_message(user_id, role, content):
    now = datetime.now(timezone.utc)
    if user_id not in user_memory:
        user_memory[user_id] = []
    user_memory[user_id].append((now, role, content))


def get_user_memory(user_id):
    now = datetime.now(timezone.utc)
    messages = user_memory.get(user_id, [])
    return [
        {"role": role, "content": content}
        for timestamp, role, content in messages
        if now - timestamp <= MEMORY_DURATION
    ]


@tasks.loop(minutes=10)
async def cleanup_memory():
    now = datetime.now(timezone.utc)
    for user_id in list(user_memory.keys()):
        user_memory[user_id] = [
            (timestamp, role, content)
            for (timestamp, role, content) in user_memory[user_id]
            if now - timestamp <= MEMORY_DURATION
        ]
        if not user_memory[user_id]:
            del user_memory[user_id]


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.author.bot:
        return

    content = message.content.strip()

    if bot.user in message.mentions:
        words = content.split()
        words = [w for w in words if not w.startswith(f"<@{bot.user.id}>") and not w.startswith(f"<@!{bot.user.id}>")]
        if len(words) > 0 and words[0].lower() == "ping":
            start = time.perf_counter()
            latency_ms = round(bot.latency * 1000)
            api_rt_ms = round((time.perf_counter() - start) * 1000)
            await send_ping_embed(message.channel, latency_ms, api_rt_ms)
            return

    responded = False

    if bot.user in message.mentions or message.reference:
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

        if message.reference:
            try:
                replied = await message.channel.fetch_message(message.reference.message_id)
                if replied and replied.content:
                    content = f"{replied.author.name} said: {replied.content}\nYou: {content}"
            except:
                pass

        if not content:
            await message.reply("Hey~ You mentioned me but didn't say anything! 💫")
            return

        try:
            async with message.channel.typing():
                user_id = message.author.id
                store_user_message(user_id, "user", content)

                context_msgs = get_user_memory(user_id)
                context_msgs.insert(0, {
                    "role": "system",
                    "content": (
                        "You are Kimii, a shy, cute girl who chats casually and makes conversations fun and lighthearted. "
                        "You are 17 years old and were made by Kaizora Team. Do not include any expressions."
                    )
                })

                response = groq_client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=context_msgs
                )

                reply = response.choices[0].message.content.strip()
                store_user_message(user_id, "assistant", reply)

            await message.reply(reply)
            responded = True

        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            responded = True

    if not responded:
        await bot.process_commands(message)


bot.run(DISCORD_TOKEN)
