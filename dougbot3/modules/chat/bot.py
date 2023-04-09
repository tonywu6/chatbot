from typing import Optional

import openai
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
from discord.ui import Button, View, button
from faker import Faker
from loguru import logger

from dougbot3.errors import report_error
from dougbot3.modules.chat.controller import ChatController
from dougbot3.modules.chat.helpers import (
    is_system_message,
    system_message,
    token_limit_warning,
)
from dougbot3.modules.chat.models import ChatCompletionRequest, ChatMessage, ChatModel
from dougbot3.modules.chat.session import ChatSession
from dougbot3.modules.chat.settings import ChatOptions
from dougbot3.settings import AppSecrets
from dougbot3.utils.config import load_settings
from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.file import discord_open
from dougbot3.utils.discord.transform import KeyOf

SECRETS = load_settings(AppSecrets)
CHAT_OPTIONS = load_settings(ChatOptions)

CHAT_PRESETS: dict[str, list[ChatMessage]] = {
    "Helpful assistant": [
        ChatMessage(
            role="system",
            content="%(environment)s. You are an helpful assistant.",
        )
    ],
    "Empty": [],
    **CHAT_OPTIONS.presets,
}


class ManageChatView(View):
    def __init__(self, bot: Bot, controller: ChatController = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.controller = controller or ChatController()

    @button(
        label="Export session",
        style=ButtonStyle.blurple,
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
        preset: KeyOf[CHAT_PRESETS] = "Helpful assistant",
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

        environment_info = (
            f"You are {self.bot.user.mention}"
            f" talking to {interaction.user.mention} over Discord."
            f" Server name: {interaction.guild.name}."
            f" Channel name: {thread_name}"
        )
        substitutions = {"environment": environment_info}
        preset_dialog = []
        if system_message:
            preset_dialog = [
                ChatMessage(role="system", content=system_message % substitutions)
            ]
        else:
            preset_dialog = [
                message.copy(update={"content": message.content % substitutions})
                for message in CHAT_PRESETS.get(preset, [])
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

    # TODO: starting system message, thread rename, summary, deferred response

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

        await session.process_request(message)

        if message.author.mention != session.atom.user:
            return

        async with thread.typing():
            logger.info("Chat {0}: sending API request", thread.mention)

            try:
                response = await openai.ChatCompletion.acreate(
                    **session.to_request().dict(),
                    api_key=SECRETS.OPENAI_TOKEN.get_secret_value(),
                )
            except Exception as e:
                await report_error(e, bot=self.bot, messageable=thread)
                return

            replies = session.prepare_replies(response)
            for reply in replies:
                await thread.send(**reply)

            logger.info("Chat {0}: resolved {1} replies", thread.mention, len(replies))

        if warning := token_limit_warning(session.usage, session.atom.model):
            await thread.send(embed=warning)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands(bot))
