"""OpenCC 包裝：簡轉繁（台灣用語）與簡體字判斷。"""

from functools import lru_cache

import opencc

_s2t = opencc.OpenCC("s2t")
_s2twp = opencc.OpenCC("s2twp")


def s2twp(text: str) -> str:
    return _s2twp.convert(text)


@lru_cache(maxsize=None)
def is_simplified_char(c: str) -> bool:
    """經過 s2t 會變成別的字，就視為簡體字。"""
    return "一" <= c <= "鿿" and _s2t.convert(c) != c
