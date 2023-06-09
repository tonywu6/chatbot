import asyncio
import importlib
import inspect
import pkgutil
import sys
from types import ModuleType
from typing import Iterable, NoReturn

from discord import Interaction, Permissions
from discord.app_commands import AppCommandError
from discord.ext.commands import Bot, CommandError, Context
from discord.utils import oauth_url
from loguru import logger

from chatbot import modules
from chatbot.settings import BotSettings
from chatbot.utils.config import load_settings
from chatbot.utils.discord.ui import ErrorReportView
from chatbot.utils.errors import report_error


def find_extensions(entry: ModuleType) -> frozenset[str]:
    def ignore_module(module: pkgutil.ModuleInfo) -> bool:
        return any(name.startswith("_") for name in module.name.split("."))

    def on_error(name: str) -> NoReturn:
        raise ImportError(name)

    extensions = set()
    for module_info in pkgutil.walk_packages(
        entry.__path__,
        f"{entry.__name__}.",
        onerror=on_error,
    ):
        if ignore_module(module_info):
            continue
        imported = importlib.import_module(module_info.name)
        if not inspect.isfunction(getattr(imported, "setup", None)):
            continue
        extensions.add(module_info.name)

    return frozenset(extensions)


async def load_all_extensions(bot: Bot, extensions: Iterable[str]) -> None:
    async def load_extension(ext: str) -> None:
        logger.info("Loading extension {0}", ext)
        await bot.load_extension(ext)

    extension_loaders = [load_extension(ext) for ext in extensions]
    await asyncio.gather(*extension_loaders)


async def create_bot():
    settings = load_settings(BotSettings)

    options = settings.bot_options.dict()

    bot = Bot(**options)

    extensions = find_extensions(modules)
    await load_all_extensions(bot, extensions)

    @bot.listen()
    async def on_ready():
        if bot.user:
            invite_url = oauth_url(
                bot.user.id,
                permissions=Permissions(532576324672),
                scopes=["bot", "applications.commands"],
            )
            logger.info("Invite URL: {0}", invite_url)

    @bot.tree.error
    async def on_app_command_error(interaction: Interaction, error: AppCommandError):
        await report_error(error, interaction=interaction)

    @bot.event
    async def on_command_error(ctx: Context, error: CommandError):
        await report_error(error, messageable=ctx)

    @bot.event
    async def on_error(event: str, *args, **kwargs):
        exc_t, exc, tb = sys.exc_info()
        channel = bot.get_channel(settings.error_report_channel)
        await report_error(exc, messageable=channel)

    bot.add_view(ErrorReportView())

    return bot
