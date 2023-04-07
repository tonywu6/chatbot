from discord import Client, Interaction
from discord.app_commands import command
from discord.ext.commands import Bot, Cog

from dougbot3.utils.datetime import utcnow
from dougbot3.utils.discord.markdown import code


class DebugCommands(Cog):
    def __init__(self, client: Client):
        self.client = client

    @command(name="echo", description="Echo a message back to the user")
    async def echo(self, interaction: Interaction, *, message: str):
        return await interaction.response.send_message(message)

    @command(
        name="ping",
        description="Test the network latency between Discord and the bot",
    )
    async def ping(self, interaction: Interaction):
        gateway_latency = self.client.latency * 1000
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


async def setup(bot: Bot) -> None:
    await bot.add_cog(DebugCommands(bot))
