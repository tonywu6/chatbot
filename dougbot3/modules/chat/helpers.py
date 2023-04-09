import asyncio
from typing import Any, Awaitable, Generic, Optional, TypeVar

from attr import dataclass
from discord import Message

from dougbot3.modules.chat.models import CHAT_MODEL_TOKEN_LIMITS, ChatModel
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.embed import Embed2

T = TypeVar("T")


def system_message():
    return Embed2().set_footer("System message")


def is_system_message(message: Message):
    if not message.embeds:
        return False
    embed = message.embeds[0]
    return bool(embed.footer and embed.footer.text == "System message")


def token_limit_warning(usage: int, model: ChatModel):
    if model not in CHAT_MODEL_TOKEN_LIMITS:
        return None
    limit = CHAT_MODEL_TOKEN_LIMITS[model]
    percentage = usage / limit
    if percentage > 0.75:
        return (
            system_message()
            .set_title("Token limit")
            .set_description(
                f"Total tokens used is at {percentage * 100:.0f}%"
                " of the modal's limit."
            )
            .set_color(Color2.orange())
        )


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
