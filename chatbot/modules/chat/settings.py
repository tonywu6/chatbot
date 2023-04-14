from pydantic import BaseSettings

from chatbot.modules.chat.models import ChatMessage
from chatbot.utils.config import use_settings_file


class ChatOptions(BaseSettings):
    Config = use_settings_file("instance/chat.yaml")

    presets: dict[str, list[ChatMessage]] = {}
