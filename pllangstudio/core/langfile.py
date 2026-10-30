"""語言檔解析與寫回（格式見 docs/adr/0001-lang-file-format.md）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import i18n, langcrypt
from .i18n import QT_TRANSLATE_NOOP

NFIELDS = 15
FLAG_LEN = 2 + 2 * NFIELDS


class Field(Enum):
    CAPTION = 0
    HINT = 1
    ITEMS = 2


FIELD_LABEL = {Field.CAPTION: QT_TRANSLATE_NOOP("Field", "標題"), Field.HINT: QT_TRANSLATE_NOOP("Field", "提示"),
               Field.ITEMS: QT_TRANSLATE_NOOP("Field", "項目")}  # 顯示時用 i18n.translate("Field", 名稱)
# 旗標欄位索引（0 起算）：英文 p6～p8 → 5～7，翻譯 p9～p11 → 8～10
SOURCE_FLAG = {Field.CAPTION: 5, Field.HINT: 6, Field.ITEMS: 7}
TARGET_FLAG = {Field.CAPTION: 8, Field.HINT: 9, Field.ITEMS: 10}


class LangFormatError(ValueError):
    def __init__(self, line_no: int, message: str):
        super().__init__(i18n.translate("langfile", "第 {line} 行：{message}").format(line=line_no, message=message))
        self.line_no = line_no
        self.message = message


@dataclass
class Entry:
    flags: list[int]
    window: str
    parents: list[str]
    component: list[str]
    ctype: list[str]
    comments: list[str]
    source: dict[Field, list[str]]
    target: dict[Field, list[str]]
    reserved: list[str]  # p12～p15 對應的行，原樣保留
    line_no: int = 0  # 旗標行在檔案中的行號（1 起算）

    @property
    def key(self) -> tuple[str, ...]:
        return (self.window, *self.parents, *self.component, *self.ctype)

    def lines(self) -> list[str]:
        flags = list(self.flags)
        flags[1], flags[2], flags[3], flags[4] = (
            len(self.parents), len(self.component), len(self.ctype), len(self.comments))
        for f in Field:
            flags[SOURCE_FLAG[f]] = len(self.source[f])
            flags[TARGET_FLAG[f]] = len(self.target[f])
        out = ["||" + "".join(f"{n:02d}" for n in flags), self.window]
        out += self.parents + self.component + self.ctype + self.comments
        for f in Field:
            out += self.source[f]
        for f in Field:
            out += self.target[f]
        return out + self.reserved


def check_line(line: str) -> None:
    """翻譯的單一行不能破壞檔案格式，不合法就拋出 ValueError。"""
    if "\r" in line or "\n" in line:
        raise ValueError(i18n.translate("langfile", "翻譯的單一行不能包含換行字元"))
    if line.startswith("||"):
        raise ValueError(i18n.translate("langfile", "翻譯不能以 || 開頭（會被當成下一筆的旗標）"))


@dataclass
class LangFile:
    header: list[str]
    entries: list[Entry]
    trailing_newline: bool

    @property
    def language(self) -> str:
        return self.header[0].lstrip(":") if self.header else ""

    def set_target(self, index: int, field: Field, lines: list[str]) -> None:
        for line in lines:
            check_line(line)
        self.entries[index].target[field] = list(lines)


def parse(plain: bytes) -> LangFile:
    if not plain.startswith(langcrypt.BOM):
        raise LangFormatError(1, i18n.translate("langfile", "缺少 UTF-8 BOM，不是語言檔"))
    body = plain[len(langcrypt.BOM):]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise LangFormatError(body[:e.start].count(b"\n") + 1, i18n.translate("langfile", "不是有效的 UTF-8 文字")) from None
    lines = text.split("\r\n")
    for no, line in enumerate(lines, 1):
        if "\n" in line or "\r" in line:
            raise LangFormatError(no, i18n.translate("langfile", "換行字元必須是 CRLF"))
    trailing = lines[-1] == ""
    if trailing:
        lines.pop()

    i = 0
    while i < len(lines) and not lines[i].startswith("||"):
        i += 1
    header, entries = lines[:i], []
    while i < len(lines):
        flag = lines[i]
        if not (flag.startswith("||") and len(flag) == FLAG_LEN and flag[2:].isdigit()):
            raise LangFormatError(i + 1, i18n.translate("langfile", "這裡應該是旗標行（|| 加 30 位數字），實際是：{actual}")
                                  .format(actual=repr(flag[:40])))
        p = [int(flag[2 + 2 * k:4 + 2 * k]) for k in range(NFIELDS)]
        if p[0] != 1:
            raise LangFormatError(i + 1, i18n.translate("langfile", "旗標第 1 欄應為 01，實際是 {actual}").format(actual=f"{p[0]:02d}"))
        n = sum(p)
        block = lines[i + 1:i + 1 + n]
        if len(block) < n:
            raise LangFormatError(i + 1, i18n.translate("langfile", "旗標記錄 {n} 行，但檔案只剩 {left} 行").format(n=n, left=len(block)))
        for j, line in enumerate(block):
            if line.startswith("||"):
                raise LangFormatError(i + 2 + j, i18n.translate(
                    "langfile", "旗標記錄 {n} 行，但第 {at} 行就遇到下一筆的旗標（行數少了）").format(n=n, at=j + 1))
        c = 1

        def take(k: int) -> list[str]:
            nonlocal c
            got = block[c:c + k]
            c += k
            return got

        parents, component, ctype, comments = take(p[1]), take(p[2]), take(p[3]), take(p[4])
        source = {f: take(p[SOURCE_FLAG[f]]) for f in Field}
        target = {f: take(p[TARGET_FLAG[f]]) for f in Field}
        entries.append(Entry(p, block[0], parents, component, ctype, comments, source, target,
                             block[c:], line_no=i + 1))
        i += 1 + n
    return LangFile(header, entries, trailing)


def serialize(lf: LangFile) -> bytes:
    lines = list(lf.header)
    for e in lf.entries:
        lines += e.lines()
    text = "\r\n".join(lines) + ("\r\n" if lf.trailing_newline else "")
    return langcrypt.BOM + text.encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    """先寫 .tmp 再 os.replace，檔案不是舊的就是新的，不會只寫一半。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def load(path: Path) -> LangFile:
    return parse(langcrypt.decrypt(Path(path).read_bytes()))


def save(path: Path, lf: LangFile) -> None:
    atomic_write(Path(path), langcrypt.encrypt(serialize(lf)))
