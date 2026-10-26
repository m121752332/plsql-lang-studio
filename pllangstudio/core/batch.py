"""批次操作的預覽（見 ADR-0010）：只計算「修改前 → 修改後」，不直接改資料。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from . import convert
from .compare import Row, get_text
from .glossary import Rule, apply_rules
from .langfile import LangFile


@dataclass
class Change:
    row: Row
    before: str
    after: str
    checked: bool = True


def preview(rows: list[Row], master: LangFile, slave: LangFile,
            fn: Callable[[Row, str, str | None], str]) -> list[Change]:
    """fn(row, slave_text, master_text) → 新的 slave_text。"""
    out = []
    for row in rows:
        if row.s_index is None:
            continue
        before = get_text(slave, row.s_index, row.field, row.item)
        after = fn(row, before, get_text(master, row.m_index, row.field, row.item))
        if after != before:
            out.append(Change(row, before, after))
    return out


def preview_rules(rows, master, slave, rules: list[Rule]) -> list[Change]:
    return preview(rows, master, slave, lambda r, s, m: apply_rules(s, rules))


def preview_replace(rows, master, slave, find: str, replace: str,
                    regex: bool = False, case: bool = True) -> list[Change]:
    pattern = re.compile(find if regex else re.escape(find), 0 if case else re.IGNORECASE)
    repl = replace if regex else replace.replace("\\", "\\\\")
    return preview(rows, master, slave, lambda r, s, m: pattern.sub(repl, s))


def preview_s2twp(rows, master, slave) -> list[Change]:
    """把主語系的文字轉成台灣繁體填入副語系；主語系沒有這筆時保持不變。"""
    return preview(rows, master, slave, lambda r, s, m: s if m is None else convert.s2twp(m))
