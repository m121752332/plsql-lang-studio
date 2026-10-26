"""依識別碼對齊 MASTER 與 SLAVE（見 ADR-0002、0003、0007）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from . import validate
from .langfile import Field, LangFile


class Status(Enum):
    DIFFERENT = "≠"
    UNTRANSLATED = "⚠"
    SIMPLIFIED = "簡"
    ONE_SIDED = "◐"
    MODIFIED = "✎"
    ERROR = "✖"
    WARNING = "!"


STATUS_LABEL = {
    Status.DIFFERENT: "不同", Status.UNTRANSLATED: "疑似漏翻", Status.SIMPLIFIED: "殘留簡體",
    Status.ONE_SIDED: "單邊", Status.MODIFIED: "已修改", Status.ERROR: "錯誤", Status.WARNING: "警告",
}


@dataclass(frozen=True)
class Row:
    key: tuple[str, ...]
    field: Field
    item: int | None  # None＝整個欄位一列（多行，以 \n 連接）
    source: str
    m_index: int | None
    s_index: int | None

    @property
    def ref(self) -> tuple[int | None, Field, int | None]:
        return (self.s_index, self.field, self.item)


def get_text(lf: LangFile, index: int | None, field: Field, item: int | None) -> str | None:
    if index is None:
        return None
    lines = lf.entries[index].target[field]
    if item is None:
        return "\n".join(lines)
    return lines[item] if item < len(lines) else ""


def set_text(lf: LangFile, index: int, field: Field, item: int | None, text: str) -> None:
    if item is None:
        lf.set_target(index, field, text.split("\n") if text else [])
        return
    if "\n" in text:
        raise ValueError("這一列是單行字串，不能輸入換行")
    lines = list(lf.entries[index].target[field])
    lines[item] = text
    lf.set_target(index, field, lines)


def _pairs(master: LangFile, slave: LangFile) -> list[tuple[int | None, int | None]]:
    s_by_key = {e.key: i for i, e in enumerate(slave.entries)}
    m_by_key = {e.key: i for i, e in enumerate(master.entries)}
    master_only: dict[int, list[int]] = defaultdict(list)
    last = -1
    for mi, e in enumerate(master.entries):
        if e.key in s_by_key:
            last = s_by_key[e.key]
        else:
            master_only[last].append(mi)
    out: list[tuple[int | None, int | None]] = [(mi, None) for mi in master_only[-1]]
    for si, e in enumerate(slave.entries):
        out.append((m_by_key.get(e.key), si))
        out += [(mi, None) for mi in master_only[si]]
    return out


def align(master: LangFile, slave: LangFile) -> list[Row]:
    rows: list[Row] = []
    for mi, si in _pairs(master, slave):
        ref = master.entries[mi] if mi is not None else slave.entries[si]
        for f in Field:
            src = ref.source[f]
            counts = [len(src)]
            if si is not None:
                counts.append(len(slave.entries[si].target[f]))
            if mi is not None:
                counts.append(len(master.entries[mi].target[f]))
            if max(counts) == 0:
                continue
            if len(set(counts)) == 1:
                rows += [Row(ref.key, f, k, src[k], mi, si) for k in range(len(src))]
            else:
                rows.append(Row(ref.key, f, None, "\n".join(src), mi, si))
    return rows


def row_status(row: Row, master: LangFile, slave: LangFile, original: str | None,
               exceptions: Iterable[str] = ()) -> tuple[set[Status], list[validate.Issue]]:
    status: set[Status] = set()
    m = get_text(master, row.m_index, row.field, row.item)
    s = get_text(slave, row.s_index, row.field, row.item)
    if m is None or s is None:
        status.add(Status.ONE_SIDED)
    elif m != s:
        status.add(Status.DIFFERENT)
    if s is None:
        return status, []
    if original is not None and s != original:
        status.add(Status.MODIFIED)
    issues = validate.check(row.source, s, exceptions)
    codes = {i.code for i in issues}
    if "UNTRANSLATED" in codes:
        status.add(Status.UNTRANSLATED)
    if "SIMPLIFIED" in codes:
        status.add(Status.SIMPLIFIED)
    if any(i.level == "error" for i in issues):
        status.add(Status.ERROR)
    if any(i.level == "warning" for i in issues):
        status.add(Status.WARNING)
    return status, issues


def count_differences(a: LangFile, b: LangFile) -> int:
    """部署前確認用：兩個語言檔有幾筆翻譯不同（含單邊）。"""
    bt = {e.key: e.target for e in b.entries}
    at = {e.key: e.target for e in a.entries}
    return sum(1 for k, t in at.items() if bt.get(k) != t) + sum(1 for k in bt if k not in at)
