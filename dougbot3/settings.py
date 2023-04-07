from typing import Callable

from discord import Intents, Message
from discord.ext.commands import Bot
from pydantic import BaseModel, BaseSettings, SecretStr

from dougbot3.utils.config import use_settings_file

DEFAULT_INTENTS = Intents.all() ^ Intents(Intents.typing.flag | Intents.presences.flag)


class _Intents(Intents):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value) -> Intents:  # noqa: ANN001
        if isinstance(value, Intents):
            return value
        if isinstance(value, int):
            return Intents(value)
        raise ValueError(f"Invalid intents {value}")


async def resolve_prefix(bot: Bot, msg: Message):
    if msg.guild is None:
        return ""
    return bot.user.mention


class BotOptions(BaseModel):
    intents: _Intents = DEFAULT_INTENTS
    command_prefix: list[str] | Callable = resolve_prefix
    case_insensitive: bool = True
    strip_after_prefix: bool = True
    help_command: str = None


class BotSettings(BaseSettings):
    Config = use_settings_file("instance/discord.toml")

    bot_options: BotOptions = BotOptions()


class AppSecrets(BaseSettings):
    Config = use_settings_file("instance/secrets.toml")

    DISCORD_BOT_TOKEN: SecretStr = SecretStr("")
    OPENAI_TOKEN: SecretStr = SecretStr("")

    def get_bot_token(self):
        return self.DISCORD_BOT_TOKEN.get_secret_value()
