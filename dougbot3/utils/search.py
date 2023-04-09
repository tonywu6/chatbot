from typing import Callable, TypeVar

from slugify import slugify

T = TypeVar("T")


def prefix_search(
    options: list[T],
    query: str,
    *,
    get_text: Callable[[T], str] = str,
) -> list[T]:
    keywords = slugify(query, allow_unicode=True).split("-")
    results: list[T] = []
    for item in options:
        tokens = slugify(get_text(item), allow_unicode=True).split("-")
        if all(any(t.startswith(k) for t in tokens) for k in keywords):
            results.append(item)
    return results
