from discord import Interaction, TextChannel, Thread
from discord.app_commands import CheckFailure, check


@check
def text_channel_only(interaction: Interaction):
    if not isinstance(interaction.channel, TextChannel):
        raise CheckFailure("This command can only be used in text channels.")
    return True


@check
def thread_only(interaction: Interaction):
    if not isinstance(interaction.channel, Thread):
        raise CheckFailure("This command can only be used in threads.")
    return True
