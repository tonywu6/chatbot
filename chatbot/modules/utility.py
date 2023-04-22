from discord import Interaction
from discord.app_commands import Group
from discord.ext.commands import Bot, Cog, UserInputError

from chatbot.utils.discord.markdown import a
from chatbot.utils.errors import system_message


class UtilityCommand(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    util_commands = Group(name="utils", description="Debugging commands")

    @util_commands.command(
        name="to-top",
        description="Create a link to the first message in a channel",
    )
    async def to_top(self, interaction: Interaction):
        if not getattr(interaction.channel, "history", None):
            raise UserInputError("This command can only be used in text channels")
        async for message in interaction.channel.history(limit=1, oldest_first=True):
            link = a("Go to first message", message.jump_url)
            response = system_message().set_description(link)
            return await interaction.response.send_message(embed=response)


async def setup(bot: Bot):
    await bot.add_cog(UtilityCommand(bot))
