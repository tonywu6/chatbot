from contextlib import asynccontextmanager
from string import Template
from textwrap import shorten
from typing import Literal, Optional

import arrow
import orjson
from discord import (
    ButtonStyle,
    ChannelType,
    Interaction,
    Message,
    Object as Snowflake,
    RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    TextChannel,
    Thread,
)
from discord.app_commands import command, context_menu, describe, guild_only
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog, UserInputError
from discord.ui import Button, button
from faker import Faker
from loguru import logger
from more_itertools import first

from chatbot.modules.chat.controller import ChatController
from chatbot.modules.chat.helpers import ensure_chat_owner
from chatbot.modules.chat.models import (
    ChatCompletionRequest,
    ChatFeatures,
    ChatMessage,
    ChatModel,
    ChatSessionOptions,
    ReplyTo,
    Timing,
)
from chatbot.modules.chat.session import ChatSession
from chatbot.modules.chat.settings import ChatOptions
from chatbot.utils.config import load_settings
from chatbot.utils.discord import Embed2
from chatbot.utils.discord.checks import text_channel_only, thread_only
from chatbot.utils.discord.color import Color2
from chatbot.utils.discord.file import discord_open
from chatbot.utils.discord.transform import KeyOf
from chatbot.utils.discord.ui import DefaultView
from chatbot.utils.errors import is_system_message, system_message


class ManageChatView(DefaultView):
    def __init__(self, bot: Bot, controller: ChatController = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.controller = controller or ChatController()

    @button(
        label="Export session",
        custom_id="manage_chat:export_session",
    )
    async def export_session(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel
        if not isinstance(channel, Thread):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        session = await self.controller.ensure_session(channel)

        request = session.to_request().dict()

        with discord_open("request.json") as (stream, file):
            stream.write(orjson.dumps(request, option=orjson.OPT_INDENT_2))

        await interaction.followup.send(file=file, ephemeral=True)

    @button(label="Rename thread", custom_id="manage_chat:rename_thread")
    async def rename_thread(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel
        if not isinstance(channel, Thread):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        session = await self.controller.ensure_session(channel)

        ensure_chat_owner(interaction, session)

        title = await session.write_title()
        if title:
            await channel.edit(name=shorten(title, 100, placeholder="..."))

        await interaction.delete_original_response()

    @button(
        label="Rebuild history",
        custom_id="manage_chat:rebuild_history",
    )
    async def rebuild_history(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel
        if not isinstance(channel, Thread):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        session = await self.controller.ensure_session(channel, refresh=True)

        result = (
            system_message()
            .set_title("Done rebuilding history")
            .set_color(Color2.teal())
            .set_description(f"Collected {len(session.messages)} messages")
        )
        await interaction.followup.send(embed=result, ephemeral=True)

    @button(label="End chat", style=ButtonStyle.red, custom_id="manage_chat:end_chat")
    async def end_chat(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel
        if not isinstance(channel, Thread):
            return

        session = await self.controller.ensure_session(channel, refresh=True)
        ensure_chat_owner(interaction, session)

        await channel.delete()
        self.controller.delete_session(channel)
        logger.info("Chat {0}: ended.", channel.mention)


class ChatCommands(Cog):
    CHAT_OPTIONS = load_settings(ChatOptions)

    CHAT_PRESETS: dict[str, list[ChatMessage]] = {
        "Discord bot": [
            ChatMessage(
                role="system",
                content="You are a helpful Discord bot. Your name is ${assistant}. ${discord}.",
            )
        ],
        "Insightful assistant": [
            ChatMessage(
                role="system",
                content="You are an insightful assistant."
                " You like to provide detailed responses to questions."
                " Your name is ${assistant}. ${discord}.",
            )
        ],
        "ChatGPT": [
            ChatMessage(
                role="system",
                content="You are ChatGPT, a large language model trained by OpenAI."
                " Answer as detailed as possible."
                " You are answering questions from ${user} over Discord.",
            )
        ],
        "Empty": [],
        **CHAT_OPTIONS.presets,
    }

    def __init__(self, bot: Bot) -> None:
        self.controller = ChatController()
        self.bot = bot
        self.bot.add_view(ManageChatView(self.bot, self.controller))

        self._fake = Faker("en-US")

    @command(name="chat", description="Start a chat thread with the bot.")
    @describe(
        preset="Include predefined initial messages.",
        model="The GPT model to use.",
        system_message="Provide a custom system message.",
        timing="Limit the frequency of the bot responding to messages.",
        reply_to="Control to whose messages the bot will respond.",
        thread_access="Limit who can access the thread.",
    )
    @guild_only()
    @text_channel_only
    @bot_has_permissions(
        view_channel=True,
        create_public_threads=True,
        create_private_threads=True,
        send_messages_in_threads=True,
        manage_threads=True,
    )
    async def chat(
        self,
        interaction: Interaction,
        *,
        model: ChatModel = "gpt-3.5-turbo",
        preset: KeyOf[CHAT_PRESETS] = first(CHAT_PRESETS),  # type: ignore (doesn't work like TypeScript lol)
        system_message: Optional[str] = None,
        timing: Timing = "immediately",
        reply_to: ReplyTo = "initial user",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        thread_access: Literal["private", "public"] = "private",
    ):
        if not isinstance(interaction.channel, TextChannel):
            raise UserInputError("This command can only be used in a text channel.")

        thread_name = " ".join(self._fake.words(part_of_speech="noun"))
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=ChannelType.private_thread
            if thread_access == "private"
            else ChannelType.public_thread,
        )

        logger.info("Chat {0}: started", thread.mention)

        response = (
            Embed2()
            .set_title("Session started!")
            .set_description(thread.mention)
            .personalized(interaction.user)
        )
        await interaction.response.send_message(embed=response, ephemeral=True)

        env = {
            "assistant": self.bot.user.mention,
            "user": interaction.user.mention,
            "server": interaction.guild.name,
            "channel": thread.mention,
            "current_date": arrow.now().format("YYYY-MM-DD"),
        }
        env["discord"] = (
            "You are talking to {user} over Discord."
            " Server name: {server}."
            " Channel: {channel}"
        ).format(**env)

        preset_dialog = []
        if system_message:
            tmpl = Template(system_message)
            preset_dialog = [
                ChatMessage(role="system", content=tmpl.safe_substitute(env))
            ]
        else:
            preset_dialog = [
                m.copy(update={"content": Template(m.content).safe_substitute(env)})
                for m in self.CHAT_PRESETS.get(preset, [])
            ]

        atom = ChatSessionOptions(
            request=ChatCompletionRequest(
                model=model,
                user=interaction.user.mention,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=preset_dialog,
            ),
            features=ChatFeatures(timing=timing, reply_to=reply_to),
        )
        session = ChatSession(assistant=self.bot.user.mention, options=atom)

        await thread.send(
            **session.to_atom(),
            view=ManageChatView(self.bot, self.controller),
        )
        await thread.add_user(interaction.user)

    @command(name="stats", description="Get stats about the current chat.")
    @guild_only()
    @thread_only
    async def stats(self, interaction: Interaction):
        session = await self.controller.ensure_session(interaction.channel)

        helper = ManageChatView(self.bot, self.controller)

        await interaction.response.send_message(
            **session.to_atom(),
            view=helper,
            ephemeral=True,
        )

    @command(name="regenerate", description="Regenerate response.")
    @guild_only()
    @thread_only
    async def regenerate(self, interaction: Interaction):
        session = await self.controller.ensure_session(interaction.channel)

        to_delete: list[int] = []

        for message in reversed(session.messages):
            if message.role == "system":
                continue
            if message.role != "assistant":
                break
            to_delete.append(message.message_id)

        await interaction.response.defer(ephemeral=True)

        await session.splice_messages(to_delete)
        await interaction.channel.delete_messages([Snowflake(id=x) for x in to_delete])

        async with session.editing:
            pass

        await interaction.delete_original_response()
        await session.answer(interaction.channel)

    @command(name="ask", description="Generate a one-shot response.")
    @describe(model="The GPT model to use.")
    async def ask(
        self,
        interaction: Interaction,
        *,
        text: str,
        model: ChatModel = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        session = ChatSession(
            assistant=self.bot.user.mention,
            options=ChatSessionOptions(
                request=ChatCompletionRequest(
                    user=interaction.user.mention,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[ChatMessage(role="user", content=text)],
                ),
            ),
        )
        user = interaction.user.mention
        await interaction.response.defer()
        await session.answer(interaction.channel)
        await interaction.edit_original_response(content=f"{user} asked: {text}")

    async def _delete_messages(self, channel_id: int, *message_ids: int):
        thread = self.bot.get_channel(channel_id)
        session = self.controller.get_session(thread)
        if not session:
            return
        async with session.editing:
            for message in message_ids:
                await session.splice_messages(message)

    @classmethod
    @asynccontextmanager
    async def maybe_update_thread_name(cls, session: ChatSession, channel: Thread):
        def responded() -> bool:
            return any(m.role == "assistant" for m in session.all_messages)

        def sufficiently_long() -> bool:
            return session.token_count_upper_bound > 128

        if responded() and sufficiently_long():
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
            if not responded() or not sufficiently_long():
                return
            title = await session.write_title()
            if title:
                await channel.edit(name=shorten(title, 100, placeholder="..."))

    @Cog.listener("on_message")
    async def on_message(self, message: Message):
        thread = message.channel
        if not isinstance(thread, Thread):
            return

        send_notice = not message.author.bot

        try:
            session = await self.controller.ensure_session(thread, verbose=send_notice)
        except Exception:
            return

        async with session.editing, self.maybe_update_thread_name(session, thread):
            await session.read_chat(message)

    @Cog.listener("on_raw_message_edit")
    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent):
        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, Thread):
            return

        session = self.controller.get_session(channel)
        if not session:
            return

        before = payload.cached_message
        try:
            after = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        async with session.editing:
            if before and before.flags.loading:
                # respond to edits due to command deferral
                await session.read_chat(after)
            else:
                # don't respond to regular message edits
                await session.process_request(after)

    async def delete_message(self, interaction: Interaction, message: Message):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, Thread) or is_system_message(message):
            await interaction.delete_original_response()
            return

        try:
            session = await self.controller.ensure_session(channel)
        except Exception:
            return

        ensure_chat_owner(interaction, session)

        await interaction.delete_original_response()
        await message.delete()

    @Cog.listener("on_raw_message_delete")
    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent):
        await self._delete_messages(payload.channel_id, payload.message_id)

    @Cog.listener("on_raw_bulk_message_delete")
    async def on_raw_bulk_message_delete(self, payload: RawBulkMessageDeleteEvent):
        await self._delete_messages(payload.channel_id, *payload.message_ids)


async def setup(bot: Bot) -> None:
    cog = ChatCommands(bot)
    bot.tree.add_command(context_menu(name="Chat: Delete")(cog.delete_message))
    await bot.add_cog(cog)
