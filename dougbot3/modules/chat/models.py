from typing import Literal, TypedDict, Union

from pydantic import BaseModel

from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.markdown import pre

ChatModel = Literal["gpt-3.5-turbo", "gpt-3.5-turbo-0301"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    user: str
    model: ChatModel = "gpt-3.5-turbo-0301"
    messages: list[ChatMessage] = []

    def describe_session(self) -> Embed2:
        params = self.json(exclude={"messages"}, indent=2)
        return (
            Embed2()
            .set_title("Chat session")
            .add_field("Parameters", pre(params, "json"))
        )


class ChatMessageRoleDelta(TypedDict):
    role: str


class ChatMessageContentDelta(TypedDict):
    content: str


class ChatMessageEndDelta(TypedDict):
    pass


ChatMessageChunk = Union[
    ChatMessageRoleDelta, ChatMessageContentDelta, ChatMessageEndDelta
]
