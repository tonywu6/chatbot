from typing import Optional, TypedDict

from discord import Embed, File
from discord.ui import View


class OutgoingMessage(TypedDict, total=False):
    content: Optional[str]
    embeds: Optional[list[Embed]]
    files: Optional[list[File]]
    view: Optional[View]
    ephemeral: Optional[bool]
