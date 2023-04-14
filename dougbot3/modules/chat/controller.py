from discord import Thread
from discord.ext.commands import UserInputError

from dougbot3.modules.chat.helpers import IdempotentTasks
from dougbot3.modules.chat.session import ChatSession
from dougbot3.utils.errors import system_message


class ChatController:
    def __init__(self):
        self.sessions: dict[Thread, ChatSession] = {}
        self._invalid_threads = set[int]()
        self._pending_threads = IdempotentTasks()

    def get_session(self, thread: Thread):
        return self.sessions.get(thread)

    def set_session(self, thread: Thread, chain: ChatSession):
        self.delete_session(thread)
        self.sessions[thread] = chain

    def delete_session(self, thread: Thread):
        session = self.sessions.pop(thread, None)
        if session is not None:
            self._pending_threads.cancel(thread)
        return session

    async def ensure_session(self, thread: Thread, *, refresh=False, verbose=False):
        session = self.get_session(thread)

        if session and not refresh:
            return session

        if thread in self._invalid_threads:
            raise UserInputError("Invalid chat thread.")

        if verbose:
            notice = system_message().set_description(
                "Rebuilding chat history. Please wait"
            )
            await thread.send(embed=notice, delete_after=10)

        task = ChatSession.from_thread(thread)
        session = await self._pending_threads.run(thread, task)

        if not session:
            self._invalid_threads.add(thread)
            raise UserInputError("Could not find params for this chat.")

        self.set_session(thread, session)
        return session
