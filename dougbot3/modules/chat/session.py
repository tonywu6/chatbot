import asyncio
from contextlib import asynccontextmanager

import openai
import yaml
from discord import Attachment, Embed, Message, Thread
from loguru import logger
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from more_itertools import constrained_batches, first, split_at

from dougbot3.modules.chat.helpers import (
    is_system_message,
    system_message,
    token_limit_warning,
)
from dougbot3.modules.chat.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageType,
    DiscordMessage,
)
from dougbot3.settings import AppSecrets
from dougbot3.utils.config import load_settings
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.embed import Embed2, EmbedReader
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.markdown import divide_text, pre
from dougbot3.utils.errors import report_error

SECRETS = load_settings(AppSecrets)

MAX_MESSAGE_LENGTH = 1996


class ChatSession:
    def __init__(
        self,
        request: ChatCompletionRequest,
        assistant: str,
    ):
        self.atom = request
        self.assistant = assistant

        self.messages: list[ChatMessage] = []
        self.usage: int = -1

        self._processing = asyncio.Lock()

    def to_request(self) -> ChatCompletionRequest:
        request = self.atom.copy()
        request.messages = [*request.messages, *self.messages]
        return request

    def to_atom(self) -> Embed2:
        params = yaml.safe_dump(
            self.atom.dict(),
            default_flow_style=False,
            sort_keys=False,
        )
        report = (
            system_message()
            .set_title("Chat session")
            .add_field("Parameters", pre(params, "yaml"))
            .add_field("Token usage", self.usage)
        )
        return report

    async def fetch(self):
        return await openai.ChatCompletion.acreate(
            **self.to_request().dict(), api_key=SECRETS.OPENAI_TOKEN.get_secret_value()
        )

    @classmethod
    async def from_thread(cls, thread: Thread):
        logger.info("Chat {0}: rebuilding history", thread.mention)

        def get_parameters(message: Message):
            try:
                embed = message.embeds[0]
                reader = EmbedReader(embed)
                params = reader["Parameters"]
                atom = ChatCompletionRequest(**params)
            except LookupError:
                logger.info("Chat {0}: not a valid thread", thread.mention)
                raise ValueError
            else:
                logger.info("Found atom: {0}", atom)
                return atom

        session: cls | None = None

        async for message in thread.history(oldest_first=True):
            if session:
                await session.process_request(message)
                continue

            try:
                atom = get_parameters(message)
                assistant = message.author.mention
                session = cls(request=atom, assistant=assistant)
            except ValueError:
                return None

        return session

    @classmethod
    def embed_to_plain_text(cls, role: str, author: str, embed: Embed) -> ChatMessage:
        embed = Embed2.upgrade(embed)
        match embed.type:
            case "article":
                document_type = "an article"
            case "gifv":
                document_type = "a GIF"
            case "image":
                document_type = "an image"
            case "link":
                document_type = "a link"
            case "rich":
                document_type = "a Markdown document"
            case "video":
                document_type = "a video"
        parts: list[str] = []
        parts.append(f"Discord: {author} sent {document_type}:\n")
        parts.append(str(embed))
        return ChatMessage(
            role=role,
            type_hint=ChatMessageType.PLAIN_TEXT,
            content="\n".join(parts),
        )

    @classmethod
    def embed_to_json_code_block(cls, embed: Embed) -> ChatMessage:
        raise NotImplementedError

    @classmethod
    async def attachment_to_plain_text(
        cls,
        role: str,
        author: str,
        attachment: Attachment,
    ) -> ChatMessage:
        content = f"Discord: {author} uploaded a file. "
        if attachment.filename:
            content = f"{content}Filename: {attachment.filename}. "
        if attachment.content_type:
            content = f"{content}Content type: {attachment.content_type}. "
        file_content = await attachment.read()
        try:
            text_content = file_content.decode("utf-8")
            content = f"{content}Content:\n\n{text_content}"
        except UnicodeDecodeError:
            content = f"{content}Content: (binary)."
        return ChatMessage(
            role=role,
            type_hint=ChatMessageType.PLAIN_TEXT,
            content=content,
        )

    @classmethod
    async def parse_message(
        cls,
        user: str,
        assistant: str,
        message: Message,
    ) -> list[ChatMessage]:
        if is_system_message(message):
            return []

        if message.is_system():
            content = message.system_content
            for member in [message.author, *message.mentions]:
                content = content.replace(member.name, member.mention)
            return [
                ChatMessage(
                    role="system",
                    content=f"Discord: {content}",
                    message_id=message.id,
                )
            ]

        author = message.author
        messages: list[ChatMessage] = []

        role = "assistant" if author.mention == assistant else "user"

        if message.content:
            content = message.content
            if author.mention != user and author.mention != assistant:
                content = f"{author.mention}: {content}"
            messages.append(ChatMessage(role=role, content=content))

        for embed in message.embeds:
            messages.append(cls.embed_to_plain_text(role, author.mention, embed))

        for attachment in message.attachments:
            item = await cls.attachment_to_plain_text(role, author.mention, attachment)
            messages.append(item)

        logger.debug("Parsed messages:")

        for result in messages:
            result.message_id = message.id
            logger.debug("{result}", result)

        return messages

    async def splice_messages(self, delete: int, insert: Message | None = None) -> None:
        index = [i for i, m in enumerate(self.messages) if m.message_id == delete]
        if insert:
            updated = await self.parse_message(self.atom.user, self.assistant, insert)
        else:
            updated = []
        if not index:
            self.messages.extend(updated)
        else:
            self.messages[min(index) : max(index) + 1] = updated

    async def process_request(self, message: Message) -> None:
        """Parse a Discord message and add it to the chain.

        Text messages from the user or the assistant will be saved as they are.
        Text messages from other users will be quoted in third-person.
        Multi-modal content (e.g. images) will be narrated in third-person from
        Discord's perspective (e.g. "Discord: <user> sent an image ...")

        :param message: a Discord Message object
        :type message: Message
        """
        async with self._processing:
            await self.splice_messages(message.id, message)

    def prepare_replies(self, response: ChatCompletionResponse) -> list[DiscordMessage]:
        """Parse an API response into a list of Discord messages.

        Long messages will be divided into chunks, splitting at new lines or
        sentences. Code blocks become individual messages. Code blocks too long
        for a Discord message become attachments.

        :param response: an API response dict
        :type response: ChatCompletionResponse
        :return: a list of DiscordMessage typed dict
        :rtype: list[DiscordMessage]
        """
        self.usage = response["usage"]["total_tokens"]

        if not response["choices"]:
            return []

        choice = response["choices"][0]
        text = choice["message"]["content"]
        finish_reason = choice["finish_reason"]

        parser = MarkdownIt()
        tokens = parser.parse(text)
        tree = SyntaxTreeNode(tokens)

        lines = text.splitlines()
        chunks: list[DiscordMessage] = []

        for node in tree.children:
            line_begin, line_end = node.map
            block = "\n".join(filter(None, lines[line_begin:line_end]))

            if node.type == "fence":
                if len(block) > MAX_MESSAGE_LENGTH:
                    with discord_open(f"code.{node.info}") as (stream, file):
                        stream.write(node.content.encode())
                    chunks.append({"files": [file]})
                else:
                    chunks.append({"content": block})

            else:
                for sentences in divide_text(
                    block,
                    maxlen=MAX_MESSAGE_LENGTH,
                    delimiter="\n.;?!",
                ):
                    chunks.append({"content": sentences})

        def is_rich_content(message: DiscordMessage) -> bool:
            return message.get("embeds") or message.get("files")

        results: list[DiscordMessage] = []

        for group in split_at(chunks, is_rich_content, keep_separator=True):
            if is_rich_content(group[0]):
                results.extend(group)
                continue
            texts = filter(None, (chunk.get("content") for chunk in group))
            paragraphs = constrained_batches(texts, MAX_MESSAGE_LENGTH, strict=True)
            results.extend(({"content": "\n".join(p)} for p in paragraphs))

        logger.info(
            "Parsed a completion response of length {length} into {num} messages",
            length=len(text),
            num=len(results),
        )

        logger.info("Finish reason: {0}", finish_reason)

        if finish_reason != "stop":
            warning = (
                system_message()
                .set_title("Finish reason")
                .set_description(f"Finish reason was `{finish_reason}`")
                .set_color(Color2.orange())
            )
            results.append({"embeds": [warning]})

        return results

    async def write_title(self):
        request = ChatCompletionRequest(max_tokens=256, temperature=0.2)
        session = ChatSession(request=request, assistant=request.model)
        messages: list[str] = [f"{m.role}: {m.content}" for m in self.messages]
        session.messages.append(
            ChatMessage(
                role="user",
                content="Write an eye-catching slug that best characterizes"
                " the topic of the following conversation,"
                " as if you are writing an article title."
                " Your slug should be in the conversation's original language."
                " Respond with just the topic itself."
                " Avoid punctuation such as quotes or periods.",
            ),
        )
        session.messages.append(
            ChatMessage(role="user", content="\n".join(messages)),
        )
        try:
            response = await session.fetch()
        except Exception as e:
            await report_error(e)
            return
        answer = first(session.prepare_replies(response), None)
        if answer:
            return answer.get("content") or None
        return None

    def should_answer(self, message: Message):
        # TODO: deferred response
        return message.author.mention == self.atom.user

    @asynccontextmanager
    async def maybe_update_title(self, channel: Thread):
        def response_count():
            return len([*filter(lambda m: m.role == "assistant", self.messages)])

        if response_count() > 0:
            try:
                yield
            finally:
                pass
            return

        try:
            yield
        except Exception:
            pass
        else:
            if response_count() == 0:
                return
            title = await self.write_title()
            if title:
                await channel.edit(name=title)

    async def answer(self, message: Message | None = None):
        await self.process_request(message)

        if not self.should_answer(message):
            return

        thread = message.channel

        async with thread.typing(), self.maybe_update_title(thread):
            logger.info("Chat {0}: sending API request", thread.mention)

            try:
                response = await self.fetch()
            except Exception as e:
                await report_error(e, bot=self.bot, messageable=thread)
                return

            replies = self.prepare_replies(response)
            logger.info("Chat {0}: resolved {1} replies", thread.mention, len(replies))

            for reply in replies:
                await thread.send(**reply)

        if warning := token_limit_warning(self.usage, self.atom.model):
            await thread.send(embed=warning)
