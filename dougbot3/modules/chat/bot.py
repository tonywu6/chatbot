from string import Template
from typing import Optional

import arrow
import orjson
from discord import (
    ButtonStyle,
    ChannelType,
    Interaction,
    Message,
    RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent,
    TextChannel,
    Thread,
)
from discord.app_commands import choices, command, describe, guild_only
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog, UserInputError
from discord.ui import Button, button
from faker import Faker
from loguru import logger
from more_itertools import first

from dougbot3.modules.chat.controller import ChatController
from dougbot3.modules.chat.helpers import is_system_message, system_message
from dougbot3.modules.chat.models import ChatCompletionRequest, ChatMessage, ChatModel
from dougbot3.modules.chat.session import ChatSession
from dougbot3.modules.chat.settings import ChatOptions
from dougbot3.utils.config import load_settings
from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.transform import KeyOf
from dougbot3.utils.discord.ui import DefaultView

CHAT_OPTIONS = load_settings(ChatOptions)

CHAT_PRESETS: dict[str, list[ChatMessage]] = {
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
            " Answer as concisely as possible."
            " You are answering questions from ${user} over Discord."
            " Current date: ${current_date}",
        )
    ],
    "Empty": [],
    **CHAT_OPTIONS.presets,
}


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

        title = await session.write_title()
        if title:
            await channel.edit(name=title)

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
        if not channel:
            return
        await channel.delete()
        self.controller.delete_session(channel)
        logger.info("Chat {0}: ended.", channel.mention)


class ChatCommands(Cog):
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
    )
    @choices()
    @guild_only()
    @bot_has_permissions(
        view_channel=True,
        create_private_threads=True,
        send_messages_in_threads=True,
        manage_threads=True,
    )
    async def chat(
        self,
        interaction: Interaction,
        preset: KeyOf[CHAT_PRESETS] = first(CHAT_PRESETS),
        system_message: Optional[str] = None,
        model: ChatModel = "gpt-3.5-turbo-0301",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        if not isinstance(interaction.channel, TextChannel):
            raise UserInputError("This command can only be used in a text channel.")

        thread_name = " ".join(self._fake.words(part_of_speech="noun"))
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=ChannelType.private_thread,
        )

        logger.info("Chat {0}: started", thread.mention)

        response = (
            Embed2()
            .set_title("Session started!")
            .set_description(thread.mention)
            .personalized(interaction.user)
        )
        await interaction.response.send_message(embed=response, ephemeral=True)

        if max_tokens <= 0:
            max_tokens = None

        env = {
            "assistant": self.bot.user.mention,
            "user": interaction.user.mention,
            "server": interaction.guild.name,
            "channel": thread.mention,
            "current_date": arrow.now().isoformat(),
        }
        env["discord"] = (
            "You are talking to {user} over Discord."
            " Server name: {server}."
            " Channel: {channel}."
            " Current date: {current_date}"
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
                for m in CHAT_PRESETS.get(preset, [])
            ]

        request = ChatCompletionRequest(
            model=model,
            user=interaction.user.mention,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=preset_dialog,
        )
        session = ChatSession(request=request, assistant=self.bot.user.mention)

        await thread.send(
            embed=session.to_atom(),
            view=ManageChatView(self.bot, self.controller),
        )
        await thread.add_user(interaction.user)

    @command(name="stats", description="Get stats about the current chat.")
    @guild_only()
    async def stats(self, interaction: Interaction):
        if not isinstance(interaction.channel, Thread):
            raise UserInputError("This command can only be used in a thread.")

        session = await self.controller.ensure_session(interaction.channel)

        helper = ManageChatView(self.bot, self.controller)
        report = session.to_atom().set_timestamp()

        await interaction.response.send_message(
            embed=report,
            view=helper,
            ephemeral=True,
        )

    async def _delete_messages(self, channel_id: int, *message_ids: int):
        thread = self.bot.get_channel(channel_id)
        session = self.controller.get_session(thread)
        if not session:
            return
        for message in message_ids:
            await session.splice_messages(message)

    @Cog.listener("on_raw_message_delete")
    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent):
        await self._delete_messages(payload.channel_id, payload.message_id)

    @Cog.listener("on_raw_bulk_message_delete")
    async def on_raw_bulk_message_delete(self, payload: RawBulkMessageDeleteEvent):
        await self._delete_messages(payload.channel_id, *payload.message_ids)

    @Cog.listener("on_message_edit")
    async def on_message_edit(self, before: Message, after: Message):
        thread = after.channel
        session = self.controller.get_session(thread)
        if not session:
            return
        await session.splice_messages(before.id, after)

    @Cog.listener("on_message")
    async def on_message(self, message: Message):
        if is_system_message(message):
            return

        thread = message.channel
        if not isinstance(thread, Thread):
            return

        try:
            send_notice = not message.author.bot
            session = await self.controller.ensure_session(thread, verbose=send_notice)
        except UserInputError:
            return

        await session.answer(message)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands(bot))
