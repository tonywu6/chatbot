import asyncio
from typing import Any, Awaitable, Generic, Optional, TypeVar

import tiktoken
from attr import dataclass
from loguru import logger
from more_itertools import flatten

from chatbot.modules.chat.models import ChatMessage

T = TypeVar("T")


@dataclass
class PendingTask(Generic[T]):
    execution: Optional[asyncio.Task]
    resolution: asyncio.Future[T]
    finished: asyncio.Event


class IdempotentTasks:
    def __init__(self) -> None:
        self.tasks: dict[Any, PendingTask] = {}

    def cancel(self, key: Any):
        task = self.tasks.get(key)
        if task is None or task.execution is None:
            return
        task.execution.cancel()

    async def run(self, key: Any, awaitable: Awaitable[T]) -> T:
        if key not in self.tasks:
            task = PendingTask(
                execution=None,
                resolution=asyncio.Future(),
                finished=asyncio.Event(),
            )
            self.tasks[key] = task

        else:
            task = self.tasks[key]

        if task.execution is not None:
            task.execution.cancel()

        def on_finish(execution: asyncio.Task):
            try:
                task.resolution.set_result(execution.result())
                task.finished.set()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if not task.resolution.done():
                    task.resolution.set_exception(e)
                task.finished.set()

        execution = asyncio.create_task(awaitable)
        execution.add_done_callback(on_finish)
        task.execution = execution

        await task.finished.wait()
        return task.resolution.result()


# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages: list[ChatMessage], model="gpt-3.5-turbo-0301"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        logger.debug("[tiktoken] Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo":
        logger.debug(
            "[tiktoken] Warning: gpt-3.5-turbo may change over time."
            " Returning num tokens assuming gpt-3.5-turbo-0301."
        )
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301")
    elif model == "gpt-4":
        logger.debug(
            "[tiktoken] Warning: gpt-4 may change over time."
            " Returning num tokens assuming gpt-4-0314."
        )
        return num_tokens_from_messages(messages, model="gpt-4-0314")
    elif model == "gpt-3.5-turbo-0301":
        # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_message = 4
        # if there's a name, the role is omitted
        # tokens_per_name = -1
    elif model == "gpt-4-0314":
        tokens_per_message = 3
        # tokens_per_name = 1
    else:
        raise NotImplementedError(
            f"num_tokens_from_messages() is not implemented for model {model}."
            " See https://github.com/openai/openai-python/blob/main/chatml.md"
            " for information on how messages are converted to tokens."
        )
    num_tokens = 0
    num_tokens += sum(
        len(t)
        for t in encoding.encode_batch(flatten((m.role, m.content) for m in messages))
    )
    num_tokens += tokens_per_message * len(messages)
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens
