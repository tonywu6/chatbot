from discord import Interaction
from discord.app_commands import command
from discord.ext.commands import Bot, Cog


class ChatCommands(Cog):
    @command(name="chat", description="Start a chat thread with the bot.")
    async def chat(self, interaction: Interaction):
        pass


async def setup(bot: Bot) -> None:
    await bot.add_cog(ChatCommands())
