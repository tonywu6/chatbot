import asyncio
import importlib
import inspect
import pkgutil
from contextlib import suppress
from types import ModuleType
from typing import Iterable, NoReturn

from discord import Interaction
from discord.app_commands import AppCommandError, CommandInvokeError
from discord.ext.commands import Bot
from loguru import logger

from dougbot3 import modules
from dougbot3.settings import BotSettings
from dougbot3.utils.discord import Color2, Embed2


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
        logger.info("Loading extension {ext}", ext=ext)
        await bot.load_extension(ext)

    extension_loaders = [load_extension(ext) for ext in extensions]
    await asyncio.gather(*extension_loaders)


async def create_bot():
    settings = BotSettings()
    options = settings.bot_options.dict()

    bot = Bot(**options)

    extensions = find_extensions(modules)
    await load_all_extensions(bot, extensions)

    @bot.tree.error
    async def on_app_command_error(interaction: Interaction, error: AppCommandError):
        if isinstance(error, CommandInvokeError):
            logger.exception(error)
        else:
            logger.warning(
                "Error while executing `{cmd}` in {server} #{channel}: {error}",
                cmd=interaction.command.name,
                channel=interaction.channel,
                server=interaction.guild,
                error=error,
            )

        report = (
            Embed2()
            .set_timestamp()
            .set_color(Color2.red())
            .set_title("Error while executing command")
            .set_description(str(error))
        )

        with suppress(Exception):
            if interaction.response.is_done():
                await interaction.followup.send(embed=report, ephemeral=True)
            else:
                await interaction.response.send_message(embed=report, ephemeral=True)

    return bot
