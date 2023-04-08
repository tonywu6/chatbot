import asyncio

from discord import Attachment, Embed, Message, Thread
from loguru import logger
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from more_itertools import constrained_batches, split_at
from ruamel import yaml

from dougbot3.modules.chat.helpers import is_system_message
from dougbot3.modules.chat.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageType,
    DiscordMessage,
)
from dougbot3.utils.discord.embed import Embed2, EmbedReader
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.markdown import divide_text, pre

MAX_MESSAGE_LENGTH = 1996


class ChatMessageChain:
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

    @classmethod
    async def from_thread(cls, thread: Thread, cancelled: asyncio.Event | None = None):
        logger.info("Chat {0}: Rebuilding history", thread.mention)

        def get_parameters(message: Message):
            try:
                embed = message.embeds[0]
                reader = EmbedReader(embed)
                params = reader["Parameters"]
                atom = ChatCompletionRequest(**params)
            except LookupError:
                raise ValueError
            else:
                logger.info("Found atom: {0}", atom)
                return atom

        session: cls | None = None

        async for message in thread.history(oldest_first=True):
            if cancelled and cancelled.is_set():
                raise asyncio.CancelledError()

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
    async def parse_discord_message(
        cls,
        user: str,
        assistant: str,
        message: Message,
    ) -> list[ChatMessage]:
        if is_system_message(message):
            return []

        author = message.author
        messages: list[ChatMessage] = []

        if message.is_system():
            content = message.system_content.replace(author.name, author.mention)
            system_message = ChatMessage(role="system", content=f"Discord: {content}")
            messages.append(system_message)
            return messages

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
            messages = await self.parse_discord_message(
                self.atom.user,
                self.assistant,
                message,
            )
            self.messages.extend(messages)

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

        logger.info("Received response. Finish reason: {0}", choice["finish_reason"])

        parser = MarkdownIt()
        tokens = parser.parse(text)
        tree = SyntaxTreeNode(tokens)

        lines = text.splitlines()
        chunks: list[DiscordMessage] = []

        for node in tree.children:
            line_begin, line_end = node.map
            block = "\n".join(lines[line_begin:line_end])

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

        consolidated: list[DiscordMessage] = []

        for group in split_at(chunks, is_rich_content, keep_separator=True):
            if is_rich_content(group[0]):
                consolidated.extend(group)
                continue
            texts = [chunk["content"] for chunk in group]
            paragraphs = constrained_batches(texts, MAX_MESSAGE_LENGTH, strict=True)
            consolidated.extend(({"content": "\n".join(p)} for p in paragraphs))

        logger.info(
            "Parsed a completion response of length {length} into {num} messages",
            length=len(text),
            num=len(consolidated),
        )
        return consolidated

    def remove_messages(self, *message_ids: int) -> None:
        filtered = [
            message
            for message in self.messages
            if not message.message_id or message.message_id not in message_ids
        ]
        self.messages.clear()
        self.messages.extend(filtered)

    def to_request(self) -> ChatCompletionRequest:
        request = self.atom.copy()
        request.messages = [*request.messages, *self.messages]
        return request

    def to_atom(self) -> Embed2:
        params = yaml.safe_dump(self.atom.dict(), default_flow_style=False)
        report = (
            Embed2()
            .set_title("Chat session")
            .add_field("Parameters", pre(params, "yaml"))
            .add_field("Token usage", self.usage)
        )
        if self.atom.messages:
            system_message = self.atom.messages[0]
            if system_message.role == "system":
                report = report.add_field("System message", system_message.content)
        return report
