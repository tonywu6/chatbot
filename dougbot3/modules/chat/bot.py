import asyncio

import openai
from discord import ButtonStyle, ChannelType, Interaction, Message, TextChannel, Thread
from discord.app_commands import choices, command, describe, guild_only
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog, UserInputError
from discord.ui import Button, View, button
from faker import Faker
from loguru import logger

from dougbot3.errors import report_error
from dougbot3.modules.chat.helpers import (
    Cancellation,
    is_system_message,
    system_message,
    token_limit_warning,
)
from dougbot3.modules.chat.models import ChatCompletionRequest, ChatModel
from dougbot3.modules.chat.session import ChatMessageChain
from dougbot3.modules.chat.settings import ChatOptions
from dougbot3.settings import AppSecrets
from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.transform import literal_choices


class ChatSessions:
    def __init__(self):
        self.sessions: dict[int, ChatMessageChain] = {}

    def get_session(self, thread: Thread):
        return self.sessions.get(thread.id)

    def set_session(self, thread: Thread, chain: ChatMessageChain):
        self.sessions[thread.id] = chain

    def delete_session(self, thread: Thread):
        self.sessions.pop(thread.id, None)


class ManageChatView(View):
    def __init__(self, bot: Bot, sessions: ChatSessions = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.sessions = sessions or ChatSessions()

    @button(label="End chat", style=ButtonStyle.red, custom_id="manage_chat:end_chat")
    async def end_chat(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel
        if not channel:
            return
        await channel.delete()
        self.sessions.delete_session(channel)
        logger.info("Chat {0}: ended.", channel.mention)

    @button(
        label="Rebuild history",
        style=ButtonStyle.blurple,
        custom_id="manage_chat:rebuild_history",
    )
    async def rebuild_history(self, interaction: Interaction, button: Button = None):
        channel = interaction.channel

        if not isinstance(channel, Thread):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        session = await ChatMessageChain.from_thread(channel)

        if not session:
            raise UserInputError(
                "Could not find the original session params for this chat."
                "\nThe message may have been deleted. Unfortunately, this means"
                " you can no longer have conversation in this thread."
            )

        self.sessions.set_session(channel, session)

        result = (
            Embed2()
            .set_title("Done rebuilding history")
            .set_color(Color2.teal())
            .set_description(f"Collected {len(session.messages)} messages")
        )

        await interaction.followup.send(embed=result, ephemeral=True)


class ChatCommands(Cog):
    def __init__(self, bot: Bot) -> None:
        self.options = ChatOptions()
        self._api_key = AppSecrets().OPENAI_TOKEN

        self.sessions = ChatSessions()
        self.bot = bot
        self.bot.add_view(ManageChatView(self.bot, self.sessions))

        self._fake = Faker("en-US")
        self._invalid_threads = set[int]()
        self._cancellation = Cancellation()

    @command(name="chat", description="Start a chat thread with the bot.")
    @describe(model="The GPT model to use.")
    @choices(model=literal_choices(ChatModel))
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

        request = ChatCompletionRequest(
            model=model,
            user=interaction.user.mention,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        session = ChatMessageChain(request=request, assistant=self.bot.user.mention)

        await thread.send(
            embed=session.to_atom(),
            view=ManageChatView(self.bot, self.sessions),
        )
        await thread.add_user(interaction.user)

    @command(name="stats", description="Get stats about the current chat.")
    @guild_only()
    async def stats(self, interaction: Interaction):
        if not isinstance(interaction.channel, Thread):
            raise UserInputError("This command can only be used in a thread.")

        session = self.sessions.get_session(interaction.channel)
        helper = ManageChatView(self.bot, self.sessions)

        if not session:
            report = (
                Embed2()
                .set_color(Color2.dark_orange())
                .set_title("Chat history not found in cache.")
                .set_description("Rebuild it, then try again.")
            )
            await interaction.response.send_message(
                view=helper,
                embed=report,
                ephemeral=True,
            )
            return

        report = session.to_atom().set_timestamp()

        await interaction.response.send_message(
            embed=report,
            view=helper,
            ephemeral=True,
        )

    @Cog.listener("on_message")
    async def on_message(self, message: Message):
        if is_system_message(message):
            return

        thread = message.channel
        if not isinstance(thread, Thread) or thread.id in self._invalid_threads:
            return

        session = self.sessions.get_session(thread)

        if session:
            await session.process_request(message)

        else:
            if not message.author.bot:
                notice = system_message().set_description("Rebuilding chat history ...")
                await thread.send(embed=notice)

            try:
                token = self._cancellation.supersede(thread.id)
                session = await ChatMessageChain.from_thread(thread, token)
            except asyncio.CancelledError:
                return

            if not session:
                self._invalid_threads.add(thread.id)
                return

            self.sessions.set_session(thread, session)

        if message.author.mention != session.atom.user:
            return

        async with thread.typing():
            logger.info("Chat {0}: sending API request", thread.mention)

            try:
                response = await openai.ChatCompletion.acreate(
                    **session.to_request().dict(),
                    api_key=self._api_key.get_secret_value(),
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
