from typing import Callable, Iterable


# From ddarknut. Blessed.
def divide_text(
    text: str,
    maxlen: int,
    pred: Callable[[str], bool] = str.isspace,
    *,
    hyphen="-",
    maxsplit=float("inf"),
) -> Iterable[str]:
    """Break long text into smaller parts of roughly the same size while\
    avoiding breaking inside words/lines."""

    if len(hyphen) > maxlen:
        raise ValueError("Hyphenation cannot be longer than length limit.")
    if not text or maxsplit < 1:
        yield text
        return

    end = sep = begin = 0
    splits = 0
    while begin < len(text):
        if end >= len(text) or splits >= maxsplit:
            yield text[begin:]
            return
        if pred(text[end:]):
            sep = end
        end += 1
        if end > begin + maxlen:
            if sep > begin:
                end = sep
                yield text[begin:end]
            else:
                end -= len(hyphen) + 1
                yield text[begin:end] + hyphen
            begin = end
            splits += 1
