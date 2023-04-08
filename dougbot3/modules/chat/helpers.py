import asyncio
from typing import Any

from discord import Message

from dougbot3.modules.chat.models import ChatModel
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.embed import Embed2


def system_message():
    return Embed2().set_footer("System message")


def is_system_message(message: Message):
    if not message.embeds:
        return False
    embed = message.embeds[0]
    return bool(embed.footer and embed.footer.text == "System message")


def token_limit_warning(usage: int, model: ChatModel):
    limits: dict[ChatModel, int] = {
        "gpt-3.5-turbo": 4096,
        "gpt-3.5-turbo-0301": 4096,
    }
    if model not in limits:
        return None
    limit = limits[model]
    percentage = usage / limit
    if percentage > 0.75:
        return (
            system_message()
            .set_title("Token limit")
            .set_description(
                f"Total tokens used is at {percentage * 100:.0f}%"
                " of the modal's limit."
            )
            .set_color(Color2.orange())
        )


class Cancellation:
    def __init__(self) -> None:
        self.tokens: dict[Any, asyncio.Event] = {}

    def cancel(self, key: Any):
        token = self.tokens.pop(key, None)
        if token:
            token.set()

    def supersede(self, key: Any):
        self.cancel(key)
        self.tokens[key] = token = asyncio.Event()
        return token
