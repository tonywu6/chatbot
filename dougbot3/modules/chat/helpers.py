import asyncio
from typing import Any

from discord import Message

from dougbot3.utils.discord.embed import Embed2


def system_message():
    return Embed2().set_footer("System message")


def is_system_message(message: Message):
    if not message.embeds:
        return False
    embed = message.embeds[0]
    return bool(embed.footer and embed.footer.text == "System message")


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
