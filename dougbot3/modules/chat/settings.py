from pydantic import BaseSettings

from dougbot3.utils.config import use_settings_file


class ChatOptions(BaseSettings):
    Config = use_settings_file("instance/chat.toml")
