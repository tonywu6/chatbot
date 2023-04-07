import re
from datetime import datetime
from math import floor
from textwrap import indent
from typing import Iterable, Literal

from discord.utils import escape_markdown

RE_USER_MENTION = re.compile(r"<@(\d+)>")
RE_ROLE_MENTION = re.compile(r"<@&(\d+)>")
RE_CHANNEL_MENTION = re.compile(r"<#(\d+)>")

RE_CODE_START = re.compile(r"```(\w+)$")
RE_CODE_END = re.compile(r"^(.*?)```")

RE_URL = re.compile(r"https?://\S*(\.[^)\]<\s]+)+[^)\]<\s]*")

_TIMESTAMP_FORMATS = Literal[
    "yy/mm/dd",
    "hh:mm:ss",
    "hh:mm",
    "full",
    "long",
    "date",
    "relative",
]
TIMESTAMP_PROCESSOR: dict[_TIMESTAMP_FORMATS, str] = {
    "yy/mm/dd": "d",
    "hh:mm:ss": "T",
    "hh:mm": "t",
    "full": "F",
    "long": "f",
    "date": "D",
    "relative": "R",
}


def tag_literal(kind: str, val: int):
    """Format this integer as a Discord mention as if it is a Discord object."""
    return {
        "user": "<@%(val)s>",
        "member": "<@%(val)s>",
        "channel": "<#%(val)s>",
        "role": "<@&%(val)s>",
    }[kind] % {"val": val}


def em(s: str) -> str:
    """Format as italics."""
    return f"_{s}_"


def strong(s: str) -> str:
    """Format as bold."""
    return f"**{s}**"


def u(s: str) -> str:
    """Format as underline."""
    return f"__{s}__"


def code(s: str) -> str:
    """Format as monospace characters."""
    return f"`{s}`"


def pre(s: str, lang="") -> str:
    """Format as a code block, optionally with syntax highlighting."""
    return f"```{lang}\n{s}\n```"


def strike(s: str) -> str:
    """Format as a strikethrough."""
    return f"~~{s}~~"


def redact(s: str) -> str:
    """Format as redaction."""
    return f"||{s}||"


def blockquote(s: str) -> str:
    """Format as a blockquote.

    The > character is added at the beginnings
    of every new line.
    """
    return indent(s, "> ", predicate=lambda t: True)


def a(text: str, href: str) -> str:
    """Format as a markdown hyperlink."""
    return f"[{text}]({href})"


def verbatim(text: str) -> str:
    """Escape all markdowns in the text and format it as a monospace string."""
    return code(escape_markdown(text))


def traffic_light(val: bool | None, strict=False):
    """Convert truthy values to the `green` emoji and falsy values to `red`.

    If `strict` is True, convert `None` to the `yellow` emoji.
    """
    if val:
        return "🟢"
    elif strict and val is None:
        return "🟡"
    else:
        return "⛔"


def pointer(d: Literal["N", "E", "S", "W"]) -> str:
    """Make an arrow pointing towards a direction."""
    return {
        "N": "↑",
        "E": "→",
        "S": "↓",
        "W": "←",
    }[d]


def timestamp(
    t: datetime | float | int | str,
    f: Literal[
        "yy/mm/dd",
        "hh:mm:ss",
        "hh:mm",
        "full",
        "long",
        "date",
        "relative",
    ],
) -> str:
    """Create a Discord timestamp markdown from a timestamp.

    :param t: The timestamp
    :type t: Union[datetime, float, int, str]
    :param f: The displayed format
    :type f: Literal['yy/mm/dd', 'hh:mm:ss', 'hh:mm',
        'full', 'long', 'date', 'relative']
    """
    if isinstance(t, datetime):
        t = t.timestamp()
    if isinstance(t, str):
        t = float(t)
    return f"<t:{floor(t):.0f}:{TIMESTAMP_PROCESSOR.get(f, f)}>"


def untagged(text: str) -> str:
    """Remove all user/role/channel mentions and show their IDs instead."""
    text = RE_USER_MENTION.sub(r"user:\1", text)
    text = RE_ROLE_MENTION.sub(r"role:\1", text)
    text = RE_CHANNEL_MENTION.sub(r"channel:\1", text)
    return text


def unwrap_codeblock(text: str, lang: str = "") -> str:
    """Remove the opening and closing backticks from a code block.

    If `lang` is specified, assert that the code block is marked
    as this language too.
    """
    text = text.strip()
    sig = f"```{lang}"
    if not text.startswith(f"{sig}\n"):
        raise ValueError(f"Code block does not begin with {sig}")
    if not text.endswith("\n```"):
        raise ValueError("Code block does not end with ```")
    return text.removeprefix(f"{sig}\n").removesuffix("```")


def find_codeblock(text: str, langs: tuple[str, ...]) -> tuple[str, int]:
    """Find and return the first valid code blocks matching\
    this language from the text.

    :param text: The text to search
    :type text: str
    :param langs: Find only code blocks in these languages.
    :type langs: tuple[str, ...]
    :return: The code block with backticks stripped, and the position
    in the original string at which it ends.
    :rtype: tuple[str, int]
    """
    lines = iter(text.splitlines())
    passed = []
    block = []
    end = ""
    for line in lines:
        if not block:
            passed.append(line)
            matched = RE_CODE_START.search(line)
            if not matched:
                continue
            if matched.group(1) in langs:
                passed.append("")
                block.append(line)
            else:
                return "", 0
        else:
            matched = RE_CODE_END.search(line)
            if matched:
                block.append(matched.group(1))
                end = "```"
                break
            else:
                block.append(line)
    code = "\n".join(block[1:])
    length = len("\n".join(passed)) + len(code) + len(end)
    return code, length


def rgba2int(r: int, g: int, b: int, a: int | None = None) -> int:
    """Convert an RGB(A) tuple to its integer representation (numeric value of the hex code)."""
    if a is None:
        return (r << 16) + (g << 8) + b
    else:
        return (r << 24) + (g << 16) + (b << 8) + a


def iter_urls(s: str) -> Iterable[str]:
    """Iterate over all URLs in text.

    A substring is consider a URL if Discord
    will display it as one.
    """
    for m in RE_URL.finditer(s):
        yield m.group(0)
