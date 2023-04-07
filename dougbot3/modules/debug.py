from discord import Message
from discord.ext.commands import Bot, Cog, Context, hybrid_command

from dougbot3.utils.datetime import utcnow, utctimestamp
from dougbot3.utils.markdown import code


class DebugCommands(Cog):
    @hybrid_command("echo", description="Echo a message back to the user.")
    async def echo(self, ctx: Context, *, message: str):
        return await ctx.send(message)

    @hybrid_command(
        "ping",
        description="Test the network latency between Discord and the bot.",
    )
    async def ping(self, ctx: Context):
        return await ctx.send(f":PONG {utctimestamp()}")

    @Cog.listener("on_message")
    async def on_ping(self, message: Message):
        gateway_dst = utctimestamp()

        if message.content[:6] != ":PONG ":
            return

        try:
            message_created = float(message.content[6:])
        except ValueError:
            return

        gateway_latency = 1000 * (gateway_dst - message_created)
        edit_start = utcnow()
        await message.edit(
            content=f"Gateway (http send -> gateway receive time): {gateway_latency:.3f}ms"
        )
        edit_latency = (utcnow() - edit_start).total_seconds() * 1000

        await message.edit(
            content=(
                f'Gateway: {code(f"{gateway_latency:.3f}ms")}'
                f'\nHTTP API (Edit): {code(f"{edit_latency:.3f}ms")}'
            )
        )


async def setup(bot: Bot) -> None:
    await bot.add_cog(DebugCommands())
