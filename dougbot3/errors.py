import sys
import traceback

import openai
from discord import File, Interaction, errors as discord_errors
from discord.abc import Messageable
from discord.app_commands import errors as app_cmd_errors
from discord.ext.commands import Bot, errors as ext_cmd_errors
from discord.ui import Button, View, button
from loguru import logger

from dougbot3.utils.datetime import utcnow
from dougbot3.utils.discord import Color2, Embed2
from dougbot3.utils.discord.file import discord_open


class ErrorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Close", custom_id="delete_error:close")
    async def close(self, interaction: Interaction, button: Button = None):
        if not interaction.message:
            return
        await interaction.message.delete()

    async def on_error(self, interaction: Interaction, error: Exception, item) -> None:
        return await report_error(error, messageable=interaction.channel)


async def report_error(
    error: Exception,
    *,
    bot: Bot | None = None,
    interaction: Interaction | None = None,
    messageable: Messageable | None = None,
):
    error = getattr(error, "original", None) or error.__cause__ or error

    match error:
        case (
            ext_cmd_errors.UserInputError()
            | ext_cmd_errors.CheckFailure()
            | app_cmd_errors.CheckFailure()
            | openai.InvalidRequestError()
        ):
            color = Color2.orange()
            title = "HTTP 400 Bad Request"
        case discord_errors.Forbidden():
            color = Color2.red()
            title = "HTTP 403 Forbidden"
        case discord_errors.NotFound():
            color = Color2.dark_gray()
            title = "HTTP 404 Forbidden"
        case (
            ext_cmd_errors.CommandOnCooldown()
            | ext_cmd_errors.MaxConcurrencyReached()
            | ext_cmd_errors.BotMissingPermissions()
            | app_cmd_errors.BotMissingPermissions()
        ):
            color = Color2.dark_red()
            title = "HTTP 503 Service Unavailable"
        case ext_cmd_errors.CommandNotFound():
            return
        case _:
            color = Color2.red()
            title = "HTTP 500 Internal Server Error"
            logger.exception(error)

    def get_traceback() -> File:
        if not isinstance(error, BaseException):
            return
        tb = traceback.format_exception(
            type(error),
            error,
            error.__traceback__,
        )
        tb_body = "".join(tb)
        for path in sys.path:
            tb_body = tb_body.replace(path, "")
        filename = f'stacktrace.{utcnow().isoformat().replace(":", ".")}.py'
        with discord_open(filename) as (stream, file):
            stream.write(tb_body.encode())
        return file

    report = (
        Embed2()
        .set_timestamp()
        .set_color(color)
        .set_title(title)
        .set_description(str(error))
    )

    with logger.catch(Exception):
        response = {"embed": report, "view": ErrorView()}
        if interaction:
            response["ephemeral"] = True
            if bot and await bot.is_owner(interaction.user):
                response["file"] = get_traceback()
            if interaction.response.is_done():
                await interaction.followup.send(**response)
            else:
                await interaction.response.send_message(**response)
        if messageable:
            await messageable.send(**response)
