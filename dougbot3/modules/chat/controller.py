from discord import Thread
from discord.ext.commands import UserInputError

from dougbot3.modules.chat.helpers import IdempotentTasks, system_message
from dougbot3.modules.chat.session import ChatSession


class ChatController:
    def __init__(self):
        self.sessions: dict[int, ChatSession] = {}
        self._invalid_threads = set[int]()
        self._pending_threads = IdempotentTasks()

    def get_session(self, thread: Thread):
        return self.sessions.get(thread.id)

    def set_session(self, thread: Thread, chain: ChatSession):
        self.sessions[thread.id] = chain

    def delete_session(self, thread: Thread):
        self.sessions.pop(thread.id, None)

    async def ensure_session(self, thread: Thread, *, refresh=False, verbose=False):
        session = self.get_session(thread)

        if session and not refresh:
            return session

        if thread.id in self._invalid_threads:
            raise UserInputError("Invalid chat thread.")

        if verbose:
            notice = system_message().set_description("Rebuilding chat history ...")
            await thread.send(embed=notice)

        task = ChatSession.from_thread(thread)
        session = await self._pending_threads.run(thread.id, task)

        if not session:
            self._invalid_threads.add(thread.id)
            raise UserInputError("Could not find params for this chat.")

        self.set_session(thread, session)
        return session
