from discord import Interaction
from discord.abc import Messageable

from dougbot3.utils.discord.typing import OutgoingMessage

Answerable = Messageable | Interaction


async def send_message(dest: Answerable, message: OutgoingMessage):
    new_message = {**message}
    if isinstance(dest, Interaction):
        if dest.response.is_done():
            await dest.followup.send(**message)
        else:
            await dest.response.send_message(**message)
    else:
        new_message.pop("ephemeral", None)
        await dest.send(**message)
