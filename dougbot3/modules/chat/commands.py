from discord import Interaction
from discord.app_commands import command
from discord.app_commands.checks import bot_has_permissions
from discord.ext.commands import Bot, Cog


class ChatCommands(Cog):
    @command(name="chat", description="Start a chat thread with the bot.")
    @bot_has_permissions(send_messages=True, create_public_threads=True)
    async def chat(self, interaction: Interaction):
        raise ValueError(1)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands())
