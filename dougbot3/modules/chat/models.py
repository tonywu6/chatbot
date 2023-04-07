from typing import Literal, Optional, TypedDict, Union

from discord import Message, Thread
from pydantic import BaseModel, Field

from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.embed import EmbedReader
from dougbot3.utils.discord.markdown import pre

ChatModel = Literal["gpt-3.5-turbo", "gpt-3.5-turbo-0301"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    message_id: Optional[int] = Field(exclude=True, default=None)
    finish_reason: Optional[str] = Field(exclude=True, default=None)


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

    @classmethod
    def from_message(cls, message: Message):
        try:
            embed = message.embeds[0]
            reader = EmbedReader(embed)
            params = reader["Parameters"]
            return cls(**params)
        except IndexError:
            raise ValueError(
                "Message does not contain a valid embed describing a chat session."
            )

    def with_outgoing(self, message: Message):
        self.messages.append(ChatMessage(role="user", content=message.content))
        info = self.dict()
        self.messages.pop()
        return info

    def update(self, user_message: Message, chat_response: "ChatCompletionResponse"):
        if not chat_response["choices"]:
            raise ValueError("No choices found in response.")

        self.messages.append(ChatMessage(role="user", content=user_message.content))

        message = ChatMessage(**chat_response["choices"][0]["message"])
        self.messages.append(message)

        return message


class ChatMessageRoleDelta(TypedDict):
    role: str


class ChatMessageContentDelta(TypedDict):
    content: str


class ChatMessageEndDelta(TypedDict):
    pass


ChatMessageChunk = Union[
    ChatMessageRoleDelta, ChatMessageContentDelta, ChatMessageEndDelta
]


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


class ChatSession(BaseModel):
    request: ChatCompletionRequest
    usage: Optional[ChatCompletionUsage] = None


class ChatSessions:
    def __init__(self):
        self.sessions: dict[int, ChatSession] = {}

    def get_session(self, thread: Thread):
        return self.sessions.get(thread.id)

    def set_session(self, thread: Thread, request: ChatCompletionRequest):
        self.sessions[thread.id] = ChatSession(request=request)

    def delete_session(self, thread: Thread):
        self.sessions.pop(thread.id, None)
