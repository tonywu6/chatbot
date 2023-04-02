from discord.ext.commands import Bot

from dougbot3.commands import DebugCommands

from .settings import BotSettings


async def create_bot():
    settings = BotSettings()
    options = settings.bot_options.dict()
    bot = Bot(**options)
    await bot.add_cog(DebugCommands())
    return bot
