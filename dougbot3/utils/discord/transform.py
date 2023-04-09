from typing import Literal


class KeyOf(str):
    @classmethod
    def __class_getitem__(cls, collection: dict):
        return Literal[tuple(collection.keys())]  # type: ignore
