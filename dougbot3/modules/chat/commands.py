from typing import Callable, Optional

from discord import ButtonStyle, ChannelType, Interaction, TextChannel
from discord.app_commands import choices, command, describe, guild_only
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog, UserInputError
from discord.ui import Button, View, button
from faker import Faker

from dougbot3.modules.chat.models import ChatCompletionRequest, ChatModel
from dougbot3.modules.chat.settings import ChatOptions
from dougbot3.utils.discord import Embed2
from dougbot3.utils.discord.transform import literal_choices


class ManageChatView(View):
    def __init__(self, *, on_chat_end: Optional[Callable] = None):
        super().__init__(timeout=None)
        self.on_chat_end = on_chat_end

    @button(label="End chat", style=ButtonStyle.red, custom_id="manage_chat:end_chat")
    async def end_chat(self, interaction: Interaction, button: Button):
        await interaction.channel.delete()
        if self.on_chat_end:
            self.on_chat_end()


class ChatCommands(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.options = ChatOptions()
        self.fake = Faker("en-US")
        self.sessions: dict[int, ChatCompletionRequest] = {}

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

        def on_chat_end():
            self.sessions.pop(interaction.channel.id, None)

        session = ChatCompletionRequest(user=interaction.user.mention, model=model)
        self.sessions[interaction.channel.id] = session

        await thread.send(
            embed=session.describe_session(),
            view=ManageChatView(on_chat_end=on_chat_end),
        )

        response = (
            Embed2()
            .set_title("Chat created!")
            .set_description(f"New thread: {thread.mention}")
            .personalized(interaction.user)
        )
        await interaction.response.send_message(embed=response, ephemeral=True)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands(bot))
    bot.add_view(ManageChatView())
