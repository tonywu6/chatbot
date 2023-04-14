from discord import Interaction
from discord.ui import View, button

from chatbot.utils.errors import report_error


class DefaultView(View):
    async def on_error(self, interaction: Interaction, error: Exception, item) -> None:
        return await report_error(error, interaction=interaction)


class ErrorReportView(DefaultView):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Close", custom_id="delete_error:close")
    async def close(self, interaction: Interaction, button=None):
        if not interaction.message:
            return
        await interaction.message.delete()
