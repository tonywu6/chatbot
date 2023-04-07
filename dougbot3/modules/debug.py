from discord.ext.commands import Bot, Cog, Context, hybrid_command


class DebugCommands(Cog):
    @hybrid_command("echo")
    async def echo(self, ctx: Context, *, message: str):
        return await ctx.send(message)


async def setup(bot: Bot) -> None:
    await bot.add_cog(DebugCommands())
