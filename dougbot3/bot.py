import asyncio
import importlib
import inspect
import io
import pkgutil
import sys
import traceback
from types import ModuleType
from typing import Iterable, NoReturn

from discord import File, Forbidden, Interaction, Permissions
from discord.app_commands import (
    AppCommandError,
    BotMissingPermissions,
    CommandInvokeError,
    TransformerError,
)
from discord.ext.commands import Bot, ConversionError, UserInputError
from discord.utils import oauth_url
from loguru import logger

from dougbot3 import modules
from dougbot3.settings import BotSettings
from dougbot3.utils.datetime import utcnow
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

    @bot.listen()
    async def on_ready():
        invite_url = oauth_url(
            bot.user.id,
            permissions=Permissions(532576324672),
            scopes=["bot", "applications.commands"],
        )
        logger.info(f"Invite URL: {invite_url}")

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

        unwrapped_error = getattr(error, "original", None) or error.__cause__ or error

        def get_traceback() -> File:
            if not isinstance(unwrapped_error, BaseException):
                return
            tb = traceback.format_exception(
                type(unwrapped_error),
                unwrapped_error,
                unwrapped_error.__traceback__,
            )
            tb_body = "".join(tb)
            for path in sys.path:
                tb_body = tb_body.replace(path, "")
            tb_file = io.BytesIO(tb_body.encode())
            filename = f'stacktrace.{utcnow().isoformat().replace(":", ".")}.py'
            return File(tb_file, filename=filename)

        match unwrapped_error:
            case UserInputError() | ConversionError() | TransformerError():
                color = Color2.orange()
                title = "HTTP 400 Bad Request"
            case Forbidden():
                color = Color2.red()
                title = "HTTP 403 Forbidden"
            case BotMissingPermissions():
                color = Color2.dark_red()
                title = "HTTP 503 Service Unavailable"
            case _:
                color = Color2.red()
                title = "HTTP 500 Internal Server Error"

        report = (
            Embed2()
            .set_timestamp()
            .set_color(color)
            .set_title(title)
            .set_description(str(unwrapped_error))
        )

        with logger.catch(Exception):
            response = {"embed": report, "ephemeral": True}
            if await bot.is_owner(interaction.user):
                response["file"] = get_traceback()
            if interaction.response.is_done():
                await interaction.followup.send(**response)
            else:
                await interaction.response.send_message(**response)

    return bot
