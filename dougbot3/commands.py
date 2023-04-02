from discord.ext.commands import Cog, Context, hybrid_command


class DebugCommands(Cog):
    @hybrid_command("echo")
    async def echo(self, ctx: Context, *, message: str):
        return await ctx.send(message)
