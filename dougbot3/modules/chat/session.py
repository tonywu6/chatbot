import asyncio
import warnings
from contextlib import asynccontextmanager
from textwrap import shorten

import openai
import yaml
from discord import Attachment, Embed, Message, MessageType, Thread
from loguru import logger
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from more_itertools import constrained_batches, first, locate, split_at

from dougbot3.modules.chat.helpers import num_tokens_from_messages
from dougbot3.modules.chat.models import (
    CHAT_MODEL_TOKEN_LIMITS,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageType,
    ChatSessionOptions,
    DiscordMessage,
)
from dougbot3.settings import AppSecrets
from dougbot3.utils.config import load_settings
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.embed import Embed2
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.markdown import divide_text
from dougbot3.utils.errors import (
    is_system_message,
    report_error,
    report_warnings,
    system_message,
)

SECRETS = load_settings(AppSecrets)

MAX_MESSAGE_LENGTH = 1996


class ChatSession:
    def __init__(
        self,
        assistant: str,
        options: ChatSessionOptions,
    ):
        self.assistant = assistant

        self.options = options
        self.messages: list[ChatMessage] = []

        self._processing = asyncio.Lock()

        self.token_usage: int = 0
        self.token_estimate: int = 0
        self.estimate_token_usage(removed=[], added=self.options.request.messages)

    @property
    def all_messages(self) -> list[ChatMessage]:
        """Create a list of all messages including messages from the preset."""
        return [
            *self.options.request.messages,
            *self.messages,
        ]

    @property
    def usage_description(self) -> str:
        if self.token_usage != self.token_estimate:
            return f"{self.token_count_upper_bound} (estimated)"
        return f"{self.token_usage}"

    @property
    def token_count_upper_bound(self) -> int:
        return max(self.token_estimate, self.token_usage)

    @property
    def system_message(self) -> str | None:
        if not self.options.request.messages:
            return None
        message = self.options.request.messages[0]
        if message.role != "system":
            return
        return message.content

    def estimate_token_usage(
        self,
        *,
        removed: list[ChatMessage],
        added: list[ChatMessage],
    ) -> None:
        removed_tokens = num_tokens_from_messages(removed)
        added_tokens = num_tokens_from_messages(added)
        self.token_estimate = self.token_estimate - removed_tokens + added_tokens

    def to_request(self) -> ChatCompletionRequest:
        """Return the API payload."""
        request = self.options.request.copy()
        request.messages = self.all_messages
        return request

    def to_atom(self) -> DiscordMessage:
        """Create a Discord message containing the session's config."""
        with discord_open("atom.yaml") as (stream, file):
            content = yaml.safe_dump(
                self.options.dict(),
                sort_keys=False,
                default_flow_style=False,
            )
            stream.write(content.encode())
        report = (
            system_message()
            .set_color(Color2.green())
            .set_title("Chat session")
            .set_description(
                shorten(self.system_message, 4000, replace_whitespace=False)
                or "(none)",
            )
            .add_field("Token usage", self.usage_description)
        )
        return {"embeds": [report], "files": [file]}

    async def fetch(self):
        request = self.to_request()
        if request.limit_max_tokens(self.token_count_upper_bound):
            warnings.warn(
                f"max_tokens was reduced to {request.max_tokens}"
                " to avoid exceeding the token limit",
                stacklevel=2,
            )
        return await openai.ChatCompletion.acreate(
            **request.dict(),
            api_key=SECRETS.OPENAI_TOKEN.get_secret_value(),
        )

    @classmethod
    async def from_thread(cls, thread: Thread):
        logger.info("Chat {0}: rebuilding history", thread.mention)

        async def get_options(message: Message):
            if not message.attachments:
                raise ValueError
            content = await message.attachments[0].read()
            try:
                return ChatSessionOptions(**yaml.safe_load(content))
            except (TypeError, ValueError, yaml.YAMLError):
                raise ValueError

        session: cls | None = None

        async for message in thread.history(oldest_first=True):
            if session:
                await session.process_request(message)
                continue

            try:
                options = await get_options(message)
                logger.info("Chat {0}: found options", options)
                assistant = message.author.mention
                session = cls(assistant=assistant, options=options)
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

        if message.type == MessageType.chat_input_command and message.interaction:
            invoker = message.interaction.user.mention
            action = f"the /{message.interaction.name} command"
            messages.append(ChatMessage(role=role, content=f"{invoker} used {action}"))

        if message.content:
            content = message.content
            if author.mention != user and author.mention != assistant:
                content = f"{author.mention} says: {content}"
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

    async def splice_messages(
        self,
        to_delete: int,
        to_insert: Message | None = None,
    ) -> bool:
        async with self._processing:
            index = [*locate(self.messages, lambda m: m.message_id == to_delete)]
            if (
                to_insert
                and not to_insert.flags.loading
                and not is_system_message(to_insert)
            ):
                updated = await self.parse_message(
                    self.options.request.user,
                    self.assistant,
                    to_insert,
                )
            else:
                updated = []
            if not index:
                removed = []
                self.messages.extend(updated)
            else:
                removed_slice = slice(min(index), max(index) + 1)
                removed = self.messages[removed_slice]
                self.messages[removed_slice] = updated
            self.estimate_token_usage(removed=removed, added=updated)
            return bool(updated)

    async def process_request(self, message: Message) -> bool:
        """Parse a Discord message and add it to the chain.

        Text messages from the user or the assistant will be saved as they are.
        Text messages from other users will be quoted in third-person.
        Multi-modal content (e.g. images) will be narrated in third-person from
        Discord's perspective (e.g. "Discord: <user> sent an image ...")

        :param message: a Discord Message object
        :type message: Message
        """
        return await self.splice_messages(message.id, message)

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
        self.token_usage = response["usage"]["total_tokens"]

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
            warnings.warn(f'Finish reason was "{finish_reason}"', stacklevel=2)

        return results

    async def write_title(self):
        session = ChatSession(
            assistant="assistant",
            options=ChatSessionOptions(
                request=ChatCompletionRequest(max_tokens=256, temperature=0),
            ),
        )
        messages: list[str] = [
            f"{m.role}: {m.content}" for m in self.messages if m.role != "system"
        ]
        session.messages.append(
            ChatMessage(
                role="user",
                content="Write an eye-catching slug that best characterizes"
                " the topic of the following conversation,"
                " as if you are writing an article title."
                " Your slug should be in the conversation's original language."
                " Respond with just the topic itself."
                " Do not put quotation marks or periods in your response.",
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

    def should_answer(self, message: Message):
        result = not message.author.mention == self.assistant
        if self.options.features.timing == "when mentioned":
            result = result and self.assistant in [m.mention for m in message.mentions]
        if self.options.features.reply_to == "initial user":
            result = result and message.author.mention == self.options.request.user
        elif self.options.features.reply_to == "any human":
            result = result and not message.author.bot
        return result

    async def answer(self, message: Message | None = None):
        new_message = await self.process_request(message)

        if not new_message or not self.should_answer(message):
            return

        thread = message.channel

        async with (
            self.maybe_update_title(thread),
            report_warnings(thread),
            thread.typing(),
        ):
            logger.info("Chat {0}: sending API request", thread.mention)

            try:
                response = await self.fetch()
            except Exception as e:
                await report_error(e, messageable=thread)
                return

            replies = self.prepare_replies(response)
            logger.info("Chat {0}: resolved {1} replies", thread.mention, len(replies))

            for reply in replies:
                await thread.send(**reply)

            self.warn_about_token_limit()

    def warn_about_token_limit(self):
        limit = CHAT_MODEL_TOKEN_LIMITS[self.options.request.model]
        percentage = self.token_count_upper_bound / limit
        if percentage > 0.75:
            warnings.warn(
                f"Token usage is at {percentage * 100:.0f}% of the model's limit.",
                stacklevel=2,
            )
