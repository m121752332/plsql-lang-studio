"""翻譯檢查規則（見 docs/adr/0011-validation-rules.md）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

from .convert import is_simplified_char

PLACEHOLDER = re.compile(r"%\d")
LOWER_WORD = re.compile(r"[a-z]{2,}")  # 全大寫縮寫（DML、NLS）通常不翻，不算漏翻
FILE_NAME = re.compile(r"[\w.-]+\.\w{2,4}")


def _looks_technical(s: str) -> bool:
    return "://" in s or "\\" in s or bool(FILE_NAME.fullmatch(s))


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    message: str


def covered(text: str, words: Iterable[str]) -> set[int]:
    """text 中被任一個 words 出現位置涵蓋的字元索引。"""
    hit: set[int] = set()
    for w in words:
        if not w:
            continue
        start = text.find(w)
        while start >= 0:
            hit.update(range(start, start + len(w)))
            start = text.find(w, start + 1)
    return hit


def simplified_spans(text: str, exceptions: Iterable[str] = ()) -> list[tuple[int, int]]:
    skip = covered(text, exceptions)
    return [(i, i + 1) for i, c in enumerate(text) if i not in skip and is_simplified_char(c)]


def _has_accel(s: str) -> bool:
    return "&" in s.replace("&&", "")


def _edges(s: str) -> tuple[bool, bool]:
    return (s[:1].isspace(), s[-1:].isspace())


def check(source: str, target: str, exceptions: Iterable[str] = ()) -> list[Issue]:
    issues: list[Issue] = []
    ps, pt = set(PLACEHOLDER.findall(source)), set(PLACEHOLDER.findall(target))
    if ps != pt:
        issues.append(Issue("error", "PLACEHOLDER",
                            f"佔位符不一致：英文 {' '.join(sorted(ps)) or '無'}，翻譯 {' '.join(sorted(pt)) or '無'}"))
    if _has_accel(source) and not _has_accel(target):
        issues.append(Issue("warning", "ACCEL", "英文有快速鍵 &，翻譯沒有"))
    if target == source and LOWER_WORD.search(source) and not _looks_technical(source):
        issues.append(Issue("warning", "UNTRANSLATED", "翻譯跟英文完全相同，可能漏翻"))
    spans = simplified_spans(target, exceptions)
    if spans:
        chars = "".join(dict.fromkeys(target[a:b] for a, b in spans))
        issues.append(Issue("warning", "SIMPLIFIED", f"殘留簡體字：{chars}"))
    if target and _edges(source) != _edges(target):
        issues.append(Issue("warning", "SPACES", "開頭或結尾的空白跟英文不一致"))
    return issues
