from enum import Enum
from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, Field, root_validator

ChatModel = Literal["gpt-3.5-turbo"]

ChatModelInfo = TypedDict("ModelInfo", {"token_limit": int})

CHAT_MODELS: dict[ChatModel, ChatModelInfo] = {
    "gpt-3.5-turbo": {"token_limit": 4096},
}


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


class ChatCompletionDelta(TypedDict):
    index: int
    delta: ChatCompletionChoiceMessage
    finish_reason: Literal["stop", "length", None]


class ChatCompletionChunk(TypedDict):
    id: str
    object: str
    created: int
    choices: list[ChatCompletionDelta]


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
    user: str = "user"
    model: ChatModel = "gpt-3.5-turbo"
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 1
    messages: list[ChatMessage] = []

    def limit_max_tokens(self, usage: int) -> bool:
        """Adjust max_tokens to fit within the token limit for the model.

        :param usage: the number of tokens in the prompt
        :type usage: int
        :return: whether max_tokens was adjusted
        :rtype: bool
        :raises ValueError: if usage exceeds the token limit
        """
        if self.max_tokens is None:
            return
        quota = CHAT_MODELS[self.model]["token_limit"] - usage
        if quota <= 0:
            raise ValueError("usage exceeds token limit")
        if self.max_tokens > quota:
            # round down to nearest 10 to compensate for inconsistency in tokenization
            self.max_tokens = quota // 10 * 10
            return True
        return False


Timing = Literal["immediately", "when mentioned"]
ReplyTo = Literal["anyone", "any human", "initial user"]


class ChatFeatures(BaseModel):
    response_timing: Timing = "immediately"
    respond_to_bots: bool = False

    timing: Optional[Timing] = Field(default=None, exclude=True)
    """.. deprecated:: 0.1.1"""
    reply_to: Optional[ReplyTo] = Field(default=None, exclude=True)
    """.. deprecated:: 0.1.1"""

    @root_validator(pre=True)
    @classmethod
    def _deprecated_fields(cls, values: dict):
        values = {**values}
        if values.get("timing") is not None:
            values["response_timing"] = values["timing"]
        if values.get("reply_to") is not None:
            values["respond_to_bots"] = values["reply_to"] == "anyone"
        return values


class ChatSessionOptions(BaseModel):
    request: ChatCompletionRequest
    features: ChatFeatures = Field(default_factory=ChatFeatures)
