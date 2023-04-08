from enum import Enum
from typing import Literal, Optional, TypedDict

from discord import Embed, File
from pydantic import BaseModel, Field

ChatModel = Literal["gpt-3.5-turbo", "gpt-3.5-turbo-0301"]


class ChatCompletionChoiceMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionChoice(TypedDict):
    index: int
    message: ChatCompletionChoiceMessage
    finish_reason: Literal["stop", "length"]


class ChatCompletionUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(TypedDict):
    id: str
    object: str
    created: int
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ChatMessageType(Enum):
    PLAIN_TEXT = 0
    CODE_BLOCK = 1
    EMBED = 2
    BINARY = 3


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    message_id: Optional[int] = Field(exclude=True, default=None)
    type_hint: ChatMessageType = Field(exclude=True, default=ChatMessageType.PLAIN_TEXT)

    def __str__(self) -> str:
        return f"{self.role}: {self.content}"


class ChatCompletionRequest(BaseModel):
    model: ChatModel = "gpt-3.5-turbo-0301"
    messages: list[ChatMessage] = []
    temperature: float = 0.7
    top_p: float = 1
    max_tokens: Optional[int] = 2000
    user: str = "user"


class DiscordMessage(TypedDict):
    content: Optional[str]
    embeds: Optional[list[Embed]]
    files: Optional[list[File]]
