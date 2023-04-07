from typing import get_args

from discord.app_commands.models import Choice


def literal_choices(choices: list[str]) -> list[Choice]:
    return [Choice(name=choice, value=choice) for choice in get_args(choices)]
