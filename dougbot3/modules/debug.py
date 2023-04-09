import os

import orjson
import psutil
from discord import Interaction, Message
from discord.app_commands import Choice, Group, choices, context_menu
from discord.ext.commands import Bot, Cog

from dougbot3.utils.datetime import utcnow
from dougbot3.utils.discord.embed import Embed2
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.markdown import code, pre
from dougbot3.utils.errors import unbound_error_handler


class DebugCommands(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    debug_commands = Group(name="debug", description="Debugging commands")

    @debug_commands.command(name="echo", description="Echo a message back to the user")
    async def echo(self, interaction: Interaction, *, message: str):
        return await interaction.response.send_message(message)

    @debug_commands.command(
        name="ping",
        description="Test the network latency between Discord and the bot",
    )
    async def ping(self, interaction: Interaction):
        gateway_latency = self.bot.latency * 1000
        await interaction.response.send_message("Pong!")

        edit_timestamp = utcnow()
        await interaction.edit_original_response(
            content="Pong! Latencies:" f"\nGateway: {code(f'{gateway_latency:.2f}ms')}"
        )
        edit_latency = (utcnow() - edit_timestamp).total_seconds() * 1000

        return await interaction.edit_original_response(
            content="Pong! Latencies:"
            f"\nGateway: {code(f'{gateway_latency:.2f}ms')}"
            f"\nHTTP API (Edit): {code(f'{edit_latency:.2f}ms')}"
        )

    @debug_commands.command(name="kill")
    @choices(
        signal=[
            Choice(name="SIGINT", value=2),
            Choice(name="SIGKILL", value=9),
            Choice(name="SIGTERM", value=15),
        ]
    )
    async def kill(self, interaction: Interaction, *, signal: int = 2):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Nuh uh.")
        await interaction.response.send_message("Sending signal ...")
        async with interaction.channel.typing():
            return psutil.Process(os.getpid()).send_signal(signal)


@context_menu(name="Debug: Embed as Markdown")
async def embed_as_markdown(interaction: Interaction, message: Message):
    if not message.embeds:
        return
    docs = [pre(str(Embed2.upgrade(e)), "md") for e in message.embeds]
    await interaction.response.send_message("\n".join(docs))


embed_as_markdown.error(unbound_error_handler)


@context_menu(name="Debug: Serialize message")
async def serialize_message(interaction: Interaction, message: Message):
    info = {
        "id": message.id,
        "url": message.jump_url,
        "timestamp": message.created_at,
        "author": f"{str(message.author)} {message.author.mention}",
        "channel": f"{str(message.channel)} {message.channel.mention}",
        "content": message.content,
    }

    info["embeds"] = [
        {"data": e.to_dict(), "preview": str(Embed2.upgrade(e))} for e in message.embeds
    ]
    info["files"] = [a.to_dict() for a in message.attachments]

    if message.reference:
        info["reference"] = message.reference.jump_url

    info["mentions"] = {
        "everyone": bool(message.mention_everyone),
        "roles": [r.mention for r in message.role_mentions],
        "users": [u.mention for u in message.mentions],
    }
    info["suppress_embeds"] = message.flags.suppress_embeds

    with discord_open(f"message.{message.id}.json") as (stream, file):
        stream.write(orjson.dumps(info, option=orjson.OPT_INDENT_2))

    await interaction.response.send_message(files=[file], ephemeral=True)


serialize_message.error(unbound_error_handler)


async def setup(bot: Bot) -> None:
    bot.tree.add_command(serialize_message)
    bot.tree.add_command(embed_as_markdown)
    await bot.add_cog(DebugCommands(bot))
