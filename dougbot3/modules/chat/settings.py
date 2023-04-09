from pydantic import BaseSettings

from dougbot3.modules.chat.models import ChatMessage
from dougbot3.utils.config import use_settings_file


class ChatOptions(BaseSettings):
    Config = use_settings_file("instance/chat.yaml")

    presets: dict[str, list[ChatMessage]] = {}
