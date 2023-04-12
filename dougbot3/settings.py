from typing import Callable

from discord import AllowedMentions, Intents
from pydantic import BaseModel, BaseSettings, SecretStr

from dougbot3.utils.config import use_settings_file

DEFAULT_INTENTS = Intents.all() ^ Intents(Intents.typing.flag | Intents.presences.flag)
DEFAULT_MENTIONS = AllowedMentions(everyone=False, roles=False, users=True)


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


class _AllowedMentions(AllowedMentions):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value) -> Intents:  # noqa: ANN001
        if isinstance(value, AllowedMentions):
            return value
        if isinstance(value, dict):
            return cls(**value)
        raise ValueError(f"Invalid allowed mentions {value}")


class BotOptions(BaseModel):
    intents: _Intents = DEFAULT_INTENTS
    allowed_mentions: _AllowedMentions = DEFAULT_MENTIONS

    command_prefix: list[str] | Callable = "\x00"
    case_insensitive: bool = True
    strip_after_prefix: bool = True
    help_command: str = None


class BotSettings(BaseSettings):
    Config = use_settings_file("instance/discord.toml")

    bot_options: BotOptions = BotOptions()

    error_report_channel: int | None = None


class AppSecrets(BaseSettings):
    Config = use_settings_file("instance/secrets.toml")

    DISCORD_BOT_TOKEN: SecretStr
    OPENAI_TOKEN: SecretStr

    def get_bot_token(self):
        return self.DISCORD_BOT_TOKEN.get_secret_value()
