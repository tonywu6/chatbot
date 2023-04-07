import re
from datetime import datetime, timedelta, timezone

RE_DURATION = re.compile(r"(?P<num>[0-9]+)\s*?(?P<unit>(y|mo|w|d|h|m|s?))")


def utcnow() -> datetime:
    """Return an aware `datetime` set to current UTC time."""
    return datetime.now(tz=timezone.utc)


def utctimestamp() -> float:
    """Return the current POSIX UTC timestamp."""
    return datetime.now(tz=timezone.utc).timestamp()


def strpduration(s: str) -> timedelta:
    """Convert strings representing a duration to a `timedelta` object.

    Examples are `90s`, `1m30s`, `7d`, etc.

    Parsing is lenient: the function will consider any number followed by
    any word beginning with any of the possible units as part of
    the duration, thus the following will all return a non-zero duration:

        7 yes, 5 moments, 4d6d9y

    """
    seconds = 0
    unit = {
        "y": 31536000,
        "mo": 2592000,
        "w": 604800,
        "d": 86400,
        "h": 3600,
        "m": 60,
        "s": 1,
        "": 1,
    }
    for seg in RE_DURATION.finditer(s):
        seconds += int(seg["num"]) * unit[seg["unit"]]
    multiplier = -1 if s.startswith("-") else 1
    return timedelta(seconds=seconds * multiplier)
