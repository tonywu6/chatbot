from datetime import datetime

import openai
from discord import ButtonStyle, ChannelType, Interaction, Message, TextChannel, Thread
from discord.app_commands import choices, command, describe, guild_only
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog, UserInputError
from discord.ui import Button, View, button
from faker import Faker

from dougbot3.modules.chat.models import (
    ChatCompletionRequest,
    ChatMessage,
    ChatModel,
    ChatSessions,
)
from dougbot3.modules.chat.settings import ChatOptions
from dougbot3.settings import AppSecrets
from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.color import Color2
from dougbot3.utils.discord.transform import literal_choices


class ManageChatView(View):
    def __init__(self, bot: Bot, sessions: ChatSessions = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.sessions = sessions or ChatSessions()

    @button(label="End chat", style=ButtonStyle.red, custom_id="manage_chat:end_chat")
    async def end_chat(self, interaction: Interaction, button: Button):
        await interaction.channel.delete()
        self.sessions.delete_session(interaction.channel)

    @button(
        label="Rebuild history",
        style=ButtonStyle.blurple,
        custom_id="manage_chat:rebuild_history",
    )
    async def rebuild_history(self, interaction: Interaction, button: Button):
        channel = interaction.channel

        if not isinstance(channel, Thread):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        completion: ChatCompletionRequest | None = None
        start_epoch: datetime | None = None

        async for message in channel.history(limit=5, oldest_first=True):
            try:
                completion = ChatCompletionRequest.from_message(message)
                start_epoch = message.created_at
            except ValueError:
                pass

        if not completion:
            raise UserInputError("Could not find session params from this thread.")

        async for message in channel.history(
            limit=None,
            oldest_first=True,
            after=start_epoch,
        ):
            if not message.content:
                continue
            if message.author == interaction.user:
                completion.messages.append(
                    ChatMessage(role="user", content=message.content)
                )
            elif message.author == self.bot.user:
                completion.messages.append(
                    ChatMessage(role="assistant", content=message.content)
                )

        self.sessions.set_session(channel, completion)

        result = (
            Embed2()
            .set_title("Done rebuilding history")
            .set_color(Color2.teal())
            .set_description(f"Collected {len(completion.messages)} messages")
        )

        await interaction.followup.send(embed=result, ephemeral=True)


class ChatCommands(Cog):
    def __init__(self, bot: Bot) -> None:
        self.options = ChatOptions()
        self.bot = bot

        self.sessions = ChatSessions()
        self.bot.add_view(ManageChatView(self.bot, self.sessions))

        self.fake = Faker("en-US")

        self._api_key = AppSecrets().OPENAI_TOKEN

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
    ):
        if not isinstance(interaction.channel, TextChannel):
            raise UserInputError("This command can only be used in a text channel.")

        thread_name = " ".join(self.fake.words(part_of_speech="noun"))
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=ChannelType.private_thread,
        )
        await thread.add_user(interaction.user)

        session = ChatCompletionRequest(user=interaction.user.mention, model=model)
        self.sessions.set_session(thread, session)

        await thread.send(
            embed=session.describe_session(),
            view=ManageChatView(self.bot, self.sessions),
        )

        response = (
            Embed2()
            .set_title("Chat created!")
            .set_description(f"New thread: {thread.mention}")
            .personalized(interaction.user)
        )
        await interaction.response.send_message(embed=response, ephemeral=True)

    @Cog.listener("on_message")
    async def on_message(self, message: Message):
        if not isinstance(message.channel, Thread):
            return

        session = self.sessions.get_session(message.channel)
        if not session:
            return
        if message.author.mention != session.request.user:
            return
        if not message.content:
            return

        request = session.request.with_outgoing(message)

        async with message.channel.typing():
            response = await openai.ChatCompletion.acreate(
                **request,
                api_key=self._api_key.get_secret_value(),
            )

        reply = session.request.update(message, response)
        await message.channel.send(content=reply.content)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands(bot))
