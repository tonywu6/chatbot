import io
from contextlib import contextmanager

from discord import File


@contextmanager
def discord_open(filename: str):
    stream = io.BytesIO()
    file = File(stream, filename=filename)
    try:
        yield (stream, file)
    finally:
        stream.seek(0)
