from typing import Callable

from discord import AllowedMentions, Intents
from pydantic import BaseModel, BaseSettings, SecretStr

from chatbot.utils.config import use_settings_file

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
    """Options for the Discord bot."""

    intents: _Intents = DEFAULT_INTENTS
    """The bot's default :external:class:`intents <discord.Intents>`."""

    allowed_mentions: _AllowedMentions = DEFAULT_MENTIONS
    """The bot's default :external:class:`allowed mentions <discord.AllowedMentions>`."""

    command_prefix: list[str] | Callable = ["\x00"]
    case_insensitive: bool = True
    strip_after_prefix: bool = True
    help_command: str = None


class BotSettings(BaseSettings):
    """Provide the following settings in ``instance/discord.toml``."""

    Config = use_settings_file("instance/discord.toml")

    bot_options: BotOptions = BotOptions()
    """Options for the Discord bot."""

    error_report_channel: int | None = None
    """The ID of the channel to send uncaught errors to.

    Errors caught during user actions, such as during a command, are sent as
    error messages to the channel the user is in. If an error occurs outside of
    a user action, such that there is no channel to send the error to, or if
    another exception occurred while reporting it, it is sent to this channel
    instead.
    """


class AppSecrets(BaseSettings):
    """Provide the following settings in ``instance/secrets.toml`` or through\
        environment variables."""

    Config = use_settings_file("instance/secrets.toml")

    DISCORD_BOT_TOKEN: SecretStr
    """The bot token for the Discord bot. Visit
    `Discord Developer Portal <https://discord.com/developers/applications>`_,
    create an application, and then create your bot."""

    OPENAI_TOKEN: SecretStr
    """Your OpenAI API token."""

    def get_bot_token(self):
        return self.DISCORD_BOT_TOKEN.get_secret_value()
