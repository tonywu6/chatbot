import os

import psutil
from discord import Interaction
from discord.app_commands import Choice, choices, command
from discord.ext.commands import Bot, Cog

from dougbot3.utils.datetime import utcnow
from dougbot3.utils.discord.markdown import code


class DebugCommands(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="echo", description="Echo a message back to the user")
    async def echo(self, interaction: Interaction, *, message: str):
        return await interaction.response.send_message(message)

    @command(
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

    @command(name="kill")
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


async def setup(bot: Bot) -> None:
    await bot.add_cog(DebugCommands(bot))
