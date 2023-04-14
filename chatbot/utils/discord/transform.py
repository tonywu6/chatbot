from typing import Literal

from discord.app_commands.models import Choice


class KeyOf(str):
    @classmethod
    def __class_getitem__(cls, collection: dict):
        return Literal[tuple(collection.keys())]  # type: ignore


def choice_name(value: int | str | float, choices: list[Choice]):
    for c in choices:
        if c.value == value:
            return c.name
    return value


def dict_choices(data: dict) -> list[Choice]:
    return [Choice(name=k, value=v) for k, v in data.items()]
