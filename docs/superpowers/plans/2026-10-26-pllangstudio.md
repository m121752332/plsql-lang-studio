# PLLangStudio 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出 PLLangStudio.exe：用 MASTER（唯讀）／SLAVE（可編輯）逐字串對照 PL/SQL Developer 的 `.lang` 語言檔，可以編輯、批次修改、檢查錯誤，加密存回工作區後再部署。

**Architecture:** `pllangstudio/core/` 是不依賴畫面的核心（加解密、解析、對齊、檢查、用語表、工作區），全部用 Languages 目錄的真實語言檔測試；`pllangstudio/ui/` 是 PySide6 畫面，表格用 `QAbstractTableModel`＋篩選 proxy，所有編輯經過 `QUndoStack`。

**Tech Stack:** Python 3.13、uv、PySide6 6.12、opencc 1.4、pytest＋pytest-qt、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-26-pllangstudio-design.md`（決策細節見 `docs/adr/0001～0012`，術語見 `CONTEXT.md`）

## Global Constraints

- 專案根目錄：`C:\Users\game\langwork\LangEditor`（git repo，分支 `master`）。所有指令都在這個目錄執行。
- Python `>=3.13`，套件用 `uv` 管理；執行一律用 `uv run …`。
- 測試讀取 `C:\Program Files\PLSQL Developer 17\Languages` 的真實語言檔，**只讀不寫**；要寫入的測試先複製到 `tmp_path`。
- 不可修改 `C:\Program Files` 底下任何檔案（部署功能只在 Task 10 的人工驗收時，由使用者自己操作）。
- 語言檔明文格式：UTF-8＋BOM、CRLF；`serialize(parse(x)) == x` 對 14 個檔案都必須成立。
- 介面文字、訊息、註解一律使用繁體中文（台灣用語），術語依 `CONTEXT.md`（筆、字串、識別碼、MASTER、SLAVE、工作區、部署、用語對照表、例外詞、錯誤、警告）。
- exe 名稱：`PLLangStudio.exe`；Python 套件名稱：`pllangstudio`。
- 每個 commit 訊息結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## 檔案結構

```
pllangstudio/
├─ __init__.py
├─ __main__.py          程式進入點
├─ appconfig.py         記住上次的工作區（%APPDATA%\PLLangStudio\app.json）
├─ elevate.py           UAC 複製
├─ core/
│  ├─ __init__.py
│  ├─ langcrypt.py      加解密（從專案根目錄搬過來，內容不變）
│  ├─ langfile.py       解析／寫回／原子寫入
│  ├─ convert.py        OpenCC 包裝
│  ├─ validate.py       檢查規則
│  ├─ compare.py        對齊、列、狀態
│  ├─ glossary.py       用語對照表（含預設規則）
│  ├─ batch.py          批次操作預覽
│  └─ workspace.py      工作區
└─ ui/
   ├─ __init__.py
   ├─ theme.py          淺色主題
   ├─ compare_model.py  表格 model＋篩選
   ├─ commands.py       QUndoCommand
   ├─ detail_panel.py   詳細區
   ├─ file_panel.py     檔案清單
   ├─ batch_dialog.py   預覽對話框、尋找取代
   ├─ glossary_dialog.py 用語表編輯器
   └─ main_window.py    主視窗
tests/
├─ conftest.py          離屏顯示、lang_copy fixture
├─ langdata.py          LANG_DIR、needs_lang_dir
├─ core/  test_langcrypt.py test_langfile.py test_validate.py test_compare.py test_glossary_batch.py test_workspace.py
└─ ui/    test_compare_model.py test_widgets.py test_main_window.py
```

---
### Task 1: 專案骨架與 langcrypt 搬家

**Files:**
- Modify: `pyproject.toml`、`app.py:14`
- Move: `langcrypt.py` → `pllangstudio/core/langcrypt.py`
- Create: `pllangstudio/__init__.py`、`pllangstudio/core/__init__.py`、`pllangstudio/ui/__init__.py`（空檔）、`tests/langdata.py`、`tests/conftest.py`
- Move+Modify: `tests/test_langcrypt.py` → `tests/core/test_langcrypt.py`

**Interfaces:**
- Produces: `pllangstudio.core.langcrypt`（`KEY`、`BOM`、`xor()`、`decrypt()`、`normalize_text()`、`encrypt()`，內容不變）；`tests/langdata.py` 的 `LANG_DIR`、`LANG_FILES`、`needs_lang_dir`；fixture `lang_copy(name) -> Path`。

- [ ] **Step: 先 commit 目前的狀態當基準**

repo 目前還沒有任何 commit。`.gitignore` 已排除 `build/ dist/ *.spec temp/`。

```bash
git add -A
git commit -m "chore: 基準：tkinter 版 LangEditor、ADR 與規格" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step: 加入相依套件**

```bash
uv add pyside6 opencc
uv add --dev pytest-qt
```

把 `pyproject.toml` 的 `name = "lang-editor"` 改成 `name = "pllangstudio"`，`description` 改成 `"PL/SQL Developer 語言編輯與比對器"`，並把 `[tool.pytest.ini_options]` 改成：

```toml
[tool.pytest.ini_options]
pythonpath = [".", "tests"]
testpaths = ["tests"]
```

- [ ] **Step: 建立套件目錄並搬移 langcrypt**

```bash
mkdir -p pllangstudio/core pllangstudio/ui tests/core tests/ui
touch pllangstudio/__init__.py pllangstudio/core/__init__.py pllangstudio/ui/__init__.py
git mv langcrypt.py pllangstudio/core/langcrypt.py
git mv tests/test_langcrypt.py tests/core/test_langcrypt.py
```

`app.py`（舊的 tkinter 版，Task 10 才刪除）第 14 行 `import langcrypt` 改成：

```python
from pllangstudio.core import langcrypt
```

- [ ] **Step: 建立 `tests/langdata.py`**

```python
"""測試共用：PL/SQL Developer 的真實語言檔（見 ADR-0012）。"""

from pathlib import Path

import pytest

LANG_DIR = Path(r"C:\Program Files\PLSQL Developer 17\Languages")
LANG_FILES = sorted(LANG_DIR.glob("*.lang"))

needs_lang_dir = pytest.mark.skipif(not LANG_FILES, reason="找不到 PL/SQL Developer 的 Languages 目錄")
```

- [ ] **Step: 建立 `tests/conftest.py`**

```python
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 畫面測試時不顯示視窗

from langdata import LANG_DIR  # noqa: E402


@pytest.fixture
def lang_copy(tmp_path):
    """把真實語言檔複製到暫存資料夾，測試只能改副本。"""
    def _copy(name: str):
        dst = tmp_path / name
        dst.write_bytes((LANG_DIR / name).read_bytes())
        return dst
    return _copy
```

- [ ] **Step: 改寫 `tests/core/test_langcrypt.py`**

```python
import pytest

from langdata import LANG_FILES, needs_lang_dir
from pllangstudio.core import langcrypt


@needs_lang_dir
@pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    data = path.read_bytes()
    plain = langcrypt.decrypt(data)
    plain.decode("utf-8")
    assert langcrypt.encrypt(plain) == data


def test_normalize_adds_bom_and_crlf():
    assert langcrypt.normalize_text("甲\n乙\r\n丙".encode()) == langcrypt.BOM + "甲\r\n乙\r\n丙".encode()


def test_rejects_non_lang_file():
    with pytest.raises(ValueError):
        langcrypt.decrypt(b"hello world")


def test_rejects_non_utf8_text():
    with pytest.raises(UnicodeDecodeError):
        langcrypt.normalize_text("中文".encode("big5"))
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_langcrypt.py -v`
Expected: 17 個 PASS（14 個語言檔＋3 個單元測試）

- [ ] **Step: Commit**

```bash
git add -A
git commit -m "refactor: 建立 pllangstudio 套件骨架，langcrypt 搬進 core" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 2: langfile：解析、寫回、原子寫入

**Files:**
- Create: `pllangstudio/core/langfile.py`
- Test: `tests/core/test_langfile.py`

**Interfaces:**
- Consumes: `langcrypt.BOM`、`langcrypt.decrypt(bytes)->bytes`、`langcrypt.encrypt(bytes)->bytes`
- Produces: `Field`（CAPTION/HINT/ITEMS）、`FIELD_LABEL`、`LangFormatError(line_no, message)`、`Entry`（`.key`、`.source/.target: dict[Field, list[str]]`、`.comments`、`.lines()`）、`LangFile`（`.header`、`.entries`、`.trailing_newline`、`.language`、`.set_target(index, field, lines)`）、`parse(bytes)->LangFile`、`serialize(LangFile)->bytes`、`atomic_write(path, bytes)`、`load(path)->LangFile`、`save(path, LangFile)`

格式規則見 ADR-0001：旗標 15 欄，筆的行數 = 15 欄總和；p1 必為 01；p12～p15 的行原樣保留在 `Entry.reserved`。

- [ ] **Step: 寫測試 `tests/core/test_langfile.py`**

```python
import os

import pytest

from langdata import LANG_DIR, LANG_FILES, needs_lang_dir
from pllangstudio.core import langcrypt, langfile
from pllangstudio.core.langfile import Field, LangFormatError

pytestmark = needs_lang_dir


@pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    plain = langcrypt.decrypt(path.read_bytes())
    assert langfile.serialize(langfile.parse(plain)) == plain


@pytest.mark.parametrize("name,count", [("Taiwan.lang", 5876), ("Chinese.lang", 5876), ("Hungarian.lang", 5695)])
def test_entry_counts(name, count):
    lf = langfile.load(LANG_DIR / name)
    assert len(lf.entries) == count
    assert len(lf.header) == 12
    assert lf.trailing_newline


def test_parses_cancel_button():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    e = next(e for e in lf.entries if e.key == ("AAMacrosEditDlg", "ButtonPanel", "CancelBtn", "Button"))
    assert e.source[Field.CAPTION] == ["&Cancel"]
    assert e.target[Field.CAPTION] == ["&取消"]


def test_english_is_identical_across_languages():
    def english(name):
        return {e.key: e.source for e in langfile.load(LANG_DIR / name).entries}
    base = english("Chinese.lang")
    for name in ["German.lang", "Japanese.lang", "Taiwan.lang"]:
        other = english(name)
        assert all(other[k] == v for k, v in base.items() if k in other)


def test_keys_are_unique():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    keys = [e.key for e in lf.entries]
    assert len(keys) == len(set(keys))


def test_set_target_changes_only_that_line():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    before = langfile.serialize(lf).split(b"\r\n")
    i = next(i for i, e in enumerate(lf.entries) if e.target[Field.CAPTION] == ["&取消"])
    lf.set_target(i, Field.CAPTION, ["&取消X"])
    after = langfile.serialize(lf).split(b"\r\n")
    diff = [k for k, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(diff) == 1
    assert after[diff[0]] == "&取消X".encode()


def test_set_target_with_more_lines_updates_flags():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    i = next(i for i, e in enumerate(lf.entries) if e.target[Field.CAPTION] == ["&取消"])
    lf.set_target(i, Field.CAPTION, ["第一行", "第二行"])
    again = langfile.parse(langfile.serialize(lf))
    assert again.entries[i].target[Field.CAPTION] == ["第一行", "第二行"]
    assert again.entries[i].flags[8] == 2
    assert len(again.entries) == len(lf.entries)


def test_set_target_rejects_newlines_and_flag_prefix():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    with pytest.raises(ValueError):
        lf.set_target(0, Field.CAPTION, ["a\nb"])
    with pytest.raises(ValueError):
        lf.set_target(0, Field.CAPTION, ["||0100"])


def test_missing_line_reports_line_number():
    plain = langcrypt.decrypt((LANG_DIR / "Taiwan.lang").read_bytes())
    lines = plain.split(b"\r\n")
    k = lines.index("&取消".encode())
    broken = b"\r\n".join(lines[:k] + lines[k + 1:])
    with pytest.raises(LangFormatError) as err:
        langfile.parse(broken)
    assert err.value.line_no > 12


def test_rejects_non_bom():
    with pytest.raises(LangFormatError):
        langfile.parse(b"hello")


def test_save_is_atomic_when_replace_fails(lang_copy, monkeypatch):
    path = lang_copy("Taiwan.lang")
    original = path.read_bytes()
    lf = langfile.load(path)
    lf.set_target(1, Field.CAPTION, ["改過"])

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        langfile.save(path, lf)
    assert path.read_bytes() == original


def test_save_then_load(lang_copy):
    path = lang_copy("Taiwan.lang")
    lf = langfile.load(path)
    lf.set_target(1, Field.CAPTION, ["改過"])
    langfile.save(path, lf)
    assert langfile.load(path).entries[1].target[Field.CAPTION] == ["改過"]
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/core/test_langfile.py -v`
Expected: FAIL，`ImportError: cannot import name 'langfile'`

- [ ] **Step: 實作 `pllangstudio/core/langfile.py`**

```python
"""語言檔解析與寫回（格式見 docs/adr/0001-lang-file-format.md）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import langcrypt

NFIELDS = 15
FLAG_LEN = 2 + 2 * NFIELDS


class Field(Enum):
    CAPTION = 0
    HINT = 1
    ITEMS = 2


FIELD_LABEL = {Field.CAPTION: "標題", Field.HINT: "提示", Field.ITEMS: "項目"}
# 旗標欄位索引（0 起算）：英文 p6～p8 → 5～7，翻譯 p9～p11 → 8～10
SOURCE_FLAG = {Field.CAPTION: 5, Field.HINT: 6, Field.ITEMS: 7}
TARGET_FLAG = {Field.CAPTION: 8, Field.HINT: 9, Field.ITEMS: 10}


class LangFormatError(ValueError):
    def __init__(self, line_no: int, message: str):
        super().__init__(f"第 {line_no} 行：{message}")
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
            if "\r" in line or "\n" in line:
                raise ValueError("翻譯的單一行不能包含換行字元")
            if line.startswith("||"):
                raise ValueError("翻譯不能以 || 開頭（會被當成下一筆的旗標）")
        self.entries[index].target[field] = list(lines)


def parse(plain: bytes) -> LangFile:
    if not plain.startswith(langcrypt.BOM):
        raise LangFormatError(1, "缺少 UTF-8 BOM，不是語言檔")
    body = plain[len(langcrypt.BOM):]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise LangFormatError(body[:e.start].count(b"\n") + 1, "不是有效的 UTF-8 文字") from None
    lines = text.split("\r\n")
    for no, line in enumerate(lines, 1):
        if "\n" in line or "\r" in line:
            raise LangFormatError(no, "換行字元必須是 CRLF")
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
            raise LangFormatError(i + 1, f"這裡應該是旗標行（|| 加 30 位數字），實際是：{flag[:40]!r}")
        p = [int(flag[2 + 2 * k:4 + 2 * k]) for k in range(NFIELDS)]
        if p[0] != 1:
            raise LangFormatError(i + 1, f"旗標第 1 欄應為 01，實際是 {p[0]:02d}")
        n = sum(p)
        block = lines[i + 1:i + 1 + n]
        if len(block) < n:
            raise LangFormatError(i + 1, f"旗標記錄 {n} 行，但檔案只剩 {len(block)} 行")
        for j, line in enumerate(block):
            if line.startswith("||"):
                raise LangFormatError(i + 2 + j, f"旗標記錄 {n} 行，但第 {j + 1} 行就遇到下一筆的旗標（行數少了）")
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
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load(path: Path) -> LangFile:
    return parse(langcrypt.decrypt(Path(path).read_bytes()))


def save(path: Path, lf: LangFile) -> None:
    atomic_write(Path(path), langcrypt.encrypt(serialize(lf)))
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_langfile.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/core/langfile.py tests/core/test_langfile.py
git commit -m "feat(core): 語言檔解析與寫回，14 個檔案逐 byte 相同" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 3: convert 與 validate：簡體字判斷與檢查規則

**Files:**
- Create: `pllangstudio/core/convert.py`、`pllangstudio/core/validate.py`
- Test: `tests/core/test_validate.py`

**Interfaces:**
- Produces: `convert.s2twp(text)->str`、`convert.is_simplified_char(c)->bool`；`validate.Issue(level, code, message)`、`validate.covered(text, words)->set[int]`、`validate.simplified_spans(text, exceptions)->list[tuple[int,int]]`、`validate.check(source, target, exceptions)->list[Issue]`。code 只有 PLACEHOLDER（error）、ACCEL、UNTRANSLATED、SIMPLIFIED、SPACES（warning）。

規則見 ADR-0011。UNTRANSLATED 只在英文含 2 個以上連續小寫字母、且不是網址／路徑／檔名時成立。

- [ ] **Step: 寫測試 `tests/core/test_validate.py`**

```python
from pllangstudio.core import validate


def codes(source, target, exceptions=()):
    return {i.code for i in validate.check(source, target, exceptions)}


def test_ok_translation_has_no_issues():
    assert codes("&Cancel", "&取消") == set()


def test_missing_placeholder_is_error():
    issues = validate.check("%1 records deleted", "條記錄已刪除")
    assert [(i.level, i.code) for i in issues] == [("error", "PLACEHOLDER")]


def test_reordered_placeholders_are_fine():
    assert codes("Copy %1 to %2", "把 %2 複製自 %1") == set()


def test_lost_accelerator_is_warning():
    assert codes("&Cancel", "取消") == {"ACCEL"}


def test_double_ampersand_is_not_accelerator():
    assert codes("Tom && Jerry", "湯姆 && 傑利") == set()


def test_untranslated_word_is_warning():
    assert codes("Tablespace", "Tablespace") == {"UNTRANSLATED"}


def test_acronyms_paths_urls_are_not_untranslated():
    for s in ["DML", "AL32UTF8", "v 1.10 ", "Box1.bmp", r"U:\PLSQLdev\Icons\Box1.bmp",
              "http://www.allroundautomations.com/x.html"]:
        assert "UNTRANSLATED" not in codes(s, s), s


def test_simplified_char_detected_and_exceptions_respected():
    assert codes("Expires in %1 days", "%1 天后過期") == {"SIMPLIFIED"}
    assert validate.simplified_spans("%1 天后過期") == [(4, 5)]
    assert codes("Cursor", "游標", ["游標"]) == set()
    assert codes("Approve", "批准", ["游標", "批准"]) == set()


def test_exception_does_not_hide_other_simplified_chars():
    assert validate.simplified_spans("游標后", ["游標"]) == [(2, 3)]


def test_edge_spaces_warning():
    assert codes(" Logging", "日誌記錄") == {"SPACES"}
    assert codes(" Logging", " 日誌記錄") == set()
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/core/test_validate.py -v`
Expected: FAIL，`ImportError: cannot import name 'validate'`

- [ ] **Step: 實作 `pllangstudio/core/convert.py`**

```python
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
```

- [ ] **Step: 實作 `pllangstudio/core/validate.py`**

```python
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
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_validate.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/core/convert.py pllangstudio/core/validate.py tests/core/test_validate.py
git commit -m "feat(core): 翻譯檢查規則與殘留簡體字判斷" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 4: compare：依識別碼對齊、拆列、狀態

**Files:**
- Create: `pllangstudio/core/compare.py`
- Test: `tests/core/test_compare.py`

**Interfaces:**
- Consumes: `langfile.Field`、`LangFile`、`validate.check`
- Produces: `Status`（值是表格顯示的符號）、`STATUS_LABEL`、`Row(key, field, item, source, m_index, s_index)`（frozen，`.ref == (s_index, field, item)`）、`get_text(lf, index, field, item)->str|None`、`set_text(lf, index, field, item, text)`、`align(master, slave)->list[Row]`、`row_status(row, master, slave, original, exceptions)->tuple[set[Status], list[Issue]]`、`count_differences(a, b)->int`

拆列規則（逐欄位）：英文、SLAVE、MASTER 的行數都相同才逐行拆列，否則 `item=None` 整個欄位一列。只有 MASTER 有的筆，插在它在 MASTER 中前一筆配對成功的 SLAVE 筆後面。

- [ ] **Step: 寫測試 `tests/core/test_compare.py`**

```python
import pytest

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import compare, langfile
from pllangstudio.core.compare import Status
from pllangstudio.core.langfile import Field

pytestmark = needs_lang_dir


@pytest.fixture(scope="module")
def zh():
    return langfile.load(LANG_DIR / "Chinese.lang")


@pytest.fixture(scope="module")
def tw():
    return langfile.load(LANG_DIR / "Taiwan.lang")


@pytest.fixture(scope="module")
def rows(zh, tw):
    return compare.align(zh, tw)


def test_row_counts(rows):
    assert len(rows) == 6672
    assert sum(r.item is None for r in rows) == 49
    assert all(r.m_index is not None and r.s_index is not None for r in rows)


def test_master_and_slave_share_key(rows, zh, tw):
    for r in rows:
        assert zh.entries[r.m_index].key == tw.entries[r.s_index].key == r.key


def test_source_comes_from_master(rows, zh):
    r = next(r for r in rows if r.key[-2:] == ("CancelBtn", "Button") and r.key[0] == "AAMacrosEditDlg")
    assert r.source == "&Cancel" and r.field is Field.CAPTION and r.item == 0
    assert compare.get_text(zh, r.m_index, r.field, r.item) == "&取消"


def test_hungarian_one_sided_rows(zh):
    hu = langfile.load(LANG_DIR / "Hungarian.lang")
    rows = compare.align(zh, hu)
    one = [r for r in rows if r.m_index is None or r.s_index is None]
    assert one and all(compare.row_status(r, zh, hu, None)[0] >= {Status.ONE_SIDED} for r in one)
    assert sum(r.s_index is None for r in rows) > 0  # 只有 MASTER 有的筆也要出現


def test_status_different_and_modified(rows, zh, tw):
    r = next(r for r in rows if compare.get_text(zh, r.m_index, r.field, r.item) == "定义")
    status, _ = compare.row_status(r, zh, tw, original="定義")
    assert status == {Status.DIFFERENT}
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    compare.set_text(lf, r.s_index, r.field, r.item, "定義X")
    status, _ = compare.row_status(r, zh, lf, original="定義")
    assert Status.MODIFIED in status


def test_status_simplified(rows, zh, tw):
    r = next(r for r in rows if compare.get_text(tw, r.s_index, r.field, r.item) == "%1 天后過期")
    status, issues = compare.row_status(r, zh, tw, None, ["游標", "批准"])
    assert {Status.SIMPLIFIED, Status.WARNING} <= status


def test_set_text_multiline_row(rows, tw):
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    r = next(r for r in rows if r.item is None)
    compare.set_text(lf, r.s_index, r.field, r.item, "甲\n乙\n丙")
    assert lf.entries[r.s_index].target[r.field] == ["甲", "乙", "丙"]
    with pytest.raises(ValueError):
        single = next(x for x in rows if x.item is not None)
        compare.set_text(lf, single.s_index, single.field, single.item, "a\nb")


def test_count_differences(zh, tw):
    assert compare.count_differences(tw, tw) == 0
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    lf.set_target(0, Field.CAPTION, ["改"])
    assert compare.count_differences(lf, tw) == 1
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/core/test_compare.py -v`
Expected: FAIL，`ImportError: cannot import name 'compare'`

- [ ] **Step: 實作 `pllangstudio/core/compare.py`**

```python
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
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_compare.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/core/compare.py tests/core/test_compare.py
git commit -m "feat(core): MASTER/SLAVE 依識別碼對齊與狀態判斷" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 5: glossary 與 batch：用語對照表、批次預覽

**Files:**
- Create: `pllangstudio/core/glossary.py`、`pllangstudio/core/batch.py`
- Test: `tests/core/test_glossary_batch.py`

**Interfaces:**
- Consumes: `validate.covered`、`compare.Row`、`compare.get_text`、`convert.s2twp`
- Produces: `Rule(find, replace, exceptions=[], enabled=True)`、`Glossary(rules, simplified_exceptions)`、`apply_rule(text, rule)`、`apply_rules(text, rules)`、`glossary.load(path)`、`glossary.save(path, g)`（JSON 欄位名 `find/replace/except/enabled`）、`glossary.default()`；`Change(row, before, after, checked=True)`、`batch.preview(rows, master, slave, fn)`、`preview_rules(rows, master, slave, rules)`、`preview_replace(rows, master, slave, find, replace, regex=False, case=True)`、`preview_s2twp(rows, master, slave)`

`glossary.default()` 是 2026-10-25～26 手動修正 Taiwan.lang 時確認過的全部規則，順序有意義。`test_default_glossary_reproduces_taiwan` 就是規格的驗收標準 #3。

- [ ] **Step: 寫測試 `tests/core/test_glossary_batch.py`**

```python
from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import batch, compare, convert, glossary, langfile
from pllangstudio.core.glossary import Rule


def test_apply_rule_respects_exceptions():
    rule = Rule("新建", "新增", ["重新建"])
    assert glossary.apply_rule("新建連線；重新建立表", rule) == "新增連線；重新建立表"


def test_apply_rule_disabled():
    assert glossary.apply_rule("新建", Rule("新建", "新增", enabled=False)) == "新建"


def test_pass_count_is_kept():
    rules = glossary.default().rules
    assert glossary.apply_rules("使用&通過計數；可以通過網路", rules) == "使用&通過計數；可以透過網路"
    assert glossary.apply_rules("[通過] 計數", rules) == "[通過] 計數"


def test_longer_rule_first():
    assert glossary.apply_rules("配置文件與配置", glossary.default().rules) == "設定檔與設定"


def test_save_and_load_roundtrip(tmp_path):
    g = glossary.default()
    glossary.save(tmp_path / "g.json", g)
    assert glossary.load(tmp_path / "g.json") == g


@needs_lang_dir
def test_default_glossary_reproduces_taiwan():
    """驗收標準 #3：s2twp(Chinese) 套用預設用語表後，每個字串都跟目前的 Taiwan.lang 相同。"""
    zh = langfile.load(LANG_DIR / "Chinese.lang")
    tw = langfile.load(LANG_DIR / "Taiwan.lang")
    rules = glossary.default().rules
    for r in compare.align(zh, tw):
        m = compare.get_text(zh, r.m_index, r.field, r.item)
        assert glossary.apply_rules(convert.s2twp(m), rules) == compare.get_text(tw, r.s_index, r.field, r.item)


@needs_lang_dir
def test_preview_functions():
    zh = langfile.load(LANG_DIR / "Chinese.lang")
    tw = langfile.load(LANG_DIR / "Taiwan.lang")
    rows = compare.align(zh, tw)
    changes = batch.preview_replace(rows, zh, tw, "巨集", "Macro")
    assert changes and all("巨集" in c.before and "Macro" in c.after for c in changes)
    assert batch.preview_rules(rows, zh, tw, glossary.default().rules) == []
    s2 = batch.preview_s2twp(rows, zh, tw)
    assert any(c.before == "偏好設定" and c.after == "首選項" for c in s2)
    regex = batch.preview_replace(rows, zh, tw, r"%(\d)", r"{\1}", regex=True)
    assert all("{" in c.after for c in regex)
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/core/test_glossary_batch.py -v`
Expected: FAIL，`ImportError: cannot import name 'batch'`

- [ ] **Step: 實作 `pllangstudio/core/glossary.py`**

```python
"""用語對照表（見 ADR-0010）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .validate import covered


@dataclass
class Rule:
    find: str
    replace: str
    exceptions: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Glossary:
    rules: list[Rule]
    simplified_exceptions: list[str]


def apply_rule(text: str, rule: Rule) -> str:
    if not rule.enabled or not rule.find:
        return text
    skip = covered(text, rule.exceptions)
    out, i, n = [], 0, len(rule.find)
    j = text.find(rule.find)
    while j >= 0:
        out.append(text[i:j])
        out.append(text[j:j + n] if skip & set(range(j, j + n)) else rule.replace)
        i = j + n
        j = text.find(rule.find, i)
    out.append(text[i:])
    return "".join(out)


def apply_rules(text: str, rules: list[Rule]) -> str:
    for r in rules:
        text = apply_rule(text, r)
    return text


def load(path: Path) -> Glossary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [Rule(r["find"], r["replace"], r.get("except", []), r.get("enabled", True)) for r in data["rules"]]
    return Glossary(rules, data.get("simplified_exceptions", []))


def save(path: Path, g: Glossary) -> None:
    data = {
        "rules": [{"find": r.find, "replace": r.replace, "except": r.exceptions, "enabled": r.enabled}
                  for r in g.rules],
        "simplified_exceptions": g.simplified_exceptions,
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# 2026-10-25～26 手動修正 Taiwan.lang 時確認過的規則與例外，順序有意義：較長的詞排前面。
_DEFAULT = [
    ("宏", "巨集", []),
    ("配置文件", "設定檔", []), ("配置嚮導", "設定精靈", []), ("配置", "設定", []),
    ("通過", "透過", ["通過計數", "通過]"]),
    ("訪問", "存取", []),
    ("註釋", "註解", []), ("文本", "文字", []), ("嚮導", "精靈", []),
    ("搜索欄", "搜尋列", []), ("搜索", "搜尋", []), ("工具欄", "工具列", []),
    ("自定義", "自訂", []), ("模板", "範本", []), ("新建", "新增", ["重新建"]),
    ("右鍵單擊", "按右鍵", []), ("單擊", "按一下", []), ("雙擊", "按兩下", []),
    ("高亮顯示", "醒目提示", []), ("高亮", "醒目提示", []),
    ("選項卡", "索引標籤", []), ("標籤頁", "分頁", []),
    ("撤銷", "復原", []), ("獲取", "取得", []),
    ("大數據", "大型資料", []), ("數據", "資料", []),
    ("賬戶", "帳戶", []), ("下劃線", "底線", []), ("創建", "建立", []),
    ("回車符", "歸位字元", []), ("回車字元", "歸位字元", []),
    ("匹配項", "相符項目", []), ("不匹配", "不相符", []), ("匹配", "相符", []),
    ("列表", "清單", []),
    ("會話", "工作階段", []), ("事務", "交易", []),
    ("首選項", "偏好設定", []), ("常規", "一般", []),
]


def default() -> Glossary:
    return Glossary([Rule(f, r, list(e)) for f, r, e in _DEFAULT], ["游標", "批准"])
```

- [ ] **Step: 實作 `pllangstudio/core/batch.py`**

```python
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
    """把 MASTER 的文字轉成台灣繁體填入 SLAVE；MASTER 沒有這筆時保持不變。"""
    return preview(rows, master, slave, lambda r, s, m: s if m is None else convert.s2twp(m))
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_glossary_batch.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/core/glossary.py pllangstudio/core/batch.py tests/core/test_glossary_batch.py
git commit -m "feat(core): 用語對照表與批次操作預覽" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 6: workspace：工作區、匯入、存檔、備份、記事本同步、部署

**Files:**
- Create: `pllangstudio/core/workspace.py`
- Test: `tests/core/test_workspace.py`

**Interfaces:**
- Consumes: `langfile`、`langcrypt`、`glossary`
- Produces: `find_plsql_lang_dir()`、`is_writable(d)`、`default_root(app_dir)`、`Settings(plsql_lang_dir, master, slave)`、`LangInfo(name, path, size, mtime, imported, deployed)`、`DeployResult(ok, changed, message, backup)`、`ImportConflict`、`Workspace(root)`：`.lang_dir/.txt_dir/.backup_dir/.settings/.installed_dir`、`save_settings()`、`load_glossary()`、`save_glossary(g)`、`list_installed()`、`list_workspace()`、`txt_path(name)`、`backup(path, prefix='')`、`import_lang(name, overwrite=False)`、`load(name)`、`save(name, lf)`、`write_txt(name, plain)`、`sync_txt(name, lf)`、`txt_changed(name)`、`acknowledge_txt(name)`、`load_txt(name)`、`deploy(name, elevate: Callable[[Path, Path], bool])`

流程見 ADR-0004、0008、0009。`deploy` 的 UAC 函式由呼叫端注入，測試用假的函式，不會真的跳 UAC。

- [ ] **Step: 寫測試 `tests/core/test_workspace.py`**

```python
import shutil

import pytest

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.langfile import Field, LangFormatError
from pllangstudio.core.workspace import ImportConflict, Workspace

pytestmark = needs_lang_dir


@pytest.fixture
def installed(tmp_path):
    """模擬 PL/SQL Developer 的 Languages 目錄（只放兩個檔案）。"""
    d = tmp_path / "Languages"
    d.mkdir()
    for n in ["Chinese.lang", "Taiwan.lang"]:
        shutil.copy(LANG_DIR / n, d / n)
    return d


@pytest.fixture
def ws(tmp_path, installed):
    w = Workspace(tmp_path / "workspace")
    w.settings.plsql_lang_dir = str(installed)
    return w


def test_creates_structure_and_default_glossary(ws):
    assert ws.lang_dir.is_dir() and ws.txt_dir.is_dir() and ws.backup_dir.is_dir()
    assert any(r.find == "會話" for r in ws.load_glossary().rules)


def test_settings_roundtrip(ws, tmp_path):
    ws.settings.slave = "Chinese.lang"
    ws.save_settings()
    assert Workspace(ws.root).settings.slave == "Chinese.lang"


def test_import_creates_lang_and_txt(ws):
    ws.import_lang("Taiwan.lang")
    assert (ws.lang_dir / "Taiwan.lang").read_bytes() == (LANG_DIR / "Taiwan.lang").read_bytes()
    assert ws.txt_path("Taiwan.lang").read_text(encoding="utf-8-sig").startswith(":Taiwan")
    assert [i.name for i in ws.list_installed() if i.imported] == ["Taiwan.lang"]
    assert ws.list_workspace()[0].deployed is True


def test_import_conflict(ws):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    with pytest.raises(ImportConflict):
        ws.import_lang("Taiwan.lang")
    ws.import_lang("Taiwan.lang", overwrite=True)
    assert len(list(ws.backup_dir.glob("Taiwan_*.lang"))) >= 2


def test_save_backs_up_and_regenerates_txt(ws):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    assert ws.load("Taiwan.lang").entries[1].target[Field.CAPTION] == ["改過"]
    assert "改過" in ws.txt_path("Taiwan.lang").read_text(encoding="utf-8-sig")
    assert list(ws.backup_dir.glob("Taiwan_*.lang"))
    assert not ws.txt_changed("Taiwan.lang")


def test_txt_external_edit_detected_and_loaded(ws):
    ws.import_lang("Taiwan.lang")
    ws.sync_txt("Taiwan.lang", ws.load("Taiwan.lang"))
    p = ws.txt_path("Taiwan.lang")
    # 模擬記事本：改一個字並存成 LF 換行
    p.write_bytes(p.read_bytes().replace("&取消".encode(), "&取消X".encode(), 1).replace(b"\r\n", b"\n"))
    assert ws.txt_changed("Taiwan.lang")
    lf = ws.load_txt("Taiwan.lang")
    assert any(e.target[Field.CAPTION] == ["&取消X"] for e in lf.entries)
    assert not ws.txt_changed("Taiwan.lang")


def test_txt_broken_format_rejected(ws):
    ws.import_lang("Taiwan.lang")
    p = ws.txt_path("Taiwan.lang")
    p.write_bytes(p.read_bytes().replace("&取消\r\n".encode(), b"", 1))
    with pytest.raises(LangFormatError):
        ws.load_txt("Taiwan.lang")


def test_txt_non_utf8_rejected(ws):
    ws.import_lang("Taiwan.lang")
    ws.txt_path("Taiwan.lang").write_bytes("中文".encode("big5"))
    with pytest.raises(UnicodeDecodeError):
        ws.load_txt("Taiwan.lang")


def test_deploy_writes_and_verifies(ws, installed):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    res = ws.deploy("Taiwan.lang", elevate=lambda s, d: pytest.fail("不應該需要 UAC"))
    assert res.ok and res.changed and res.backup.exists()
    assert langfile.load(installed / "Taiwan.lang").entries[1].target[Field.CAPTION] == ["改過"]
    assert ws.deploy("Taiwan.lang", elevate=lambda s, d: False).changed is False


def test_deploy_uses_elevation_on_permission_error(ws, installed, monkeypatch):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)

    def deny(path, data):
        raise PermissionError
    monkeypatch.setattr(langfile, "atomic_write", deny)
    calls = []

    def fake_elevate(src, dst):
        calls.append((src, dst))
        shutil.copy(src, dst)
        return True
    assert ws.deploy("Taiwan.lang", elevate=fake_elevate).ok
    assert calls


def test_deploy_cancelled_uac(ws, monkeypatch):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    monkeypatch.setattr(langfile, "atomic_write", lambda p, d: (_ for _ in ()).throw(PermissionError()))
    res = ws.deploy("Taiwan.lang", elevate=lambda s, d: False)
    assert not res.ok and "工作區" in res.message
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/core/test_workspace.py -v`
Expected: FAIL，`ImportError: cannot import name 'Workspace'`

- [ ] **Step: 實作 `pllangstudio/core/workspace.py`**

```python
"""工作區：匯入、存檔、備份、部署、記事本 .txt 同步（見 ADR-0004、0008、0009）。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import glossary, langcrypt, langfile
from .langfile import LangFile

DEFAULT_PLSQL_DIR = Path(r"C:\Program Files\PLSQL Developer 17\Languages")


def find_plsql_lang_dir() -> Path | None:
    if DEFAULT_PLSQL_DIR.is_dir():
        return DEFAULT_PLSQL_DIR
    found = sorted(p for base in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)"))
                   if base.is_dir() for p in base.glob("PLSQL Developer*/Languages") if p.is_dir())
    return found[-1] if found else None


def is_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def default_root(app_dir: Path) -> Path:
    first = app_dir / "workspace"
    if is_writable(first):
        return first
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Documents" / "PLLangStudio" / "workspace"


@dataclass
class Settings:
    plsql_lang_dir: str = ""
    master: str = "Chinese.lang"
    slave: str = "Taiwan.lang"


@dataclass
class LangInfo:
    name: str
    path: Path
    size: int
    mtime: float
    imported: bool = False      # 用於 PL/SQL 清單：工作區是否已有同名檔
    deployed: bool | None = None  # 用於工作區清單：是否與 PL/SQL 目錄裡的同名檔相同


@dataclass
class DeployResult:
    ok: bool
    changed: bool
    message: str
    backup: Path | None = None


class ImportConflict(Exception):
    """工作區已有同名檔而且內容不同。"""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lang_dir = self.root / "lang"
        self.txt_dir = self.root / "txt"
        self.backup_dir = self.root / "backup"
        for d in (self.lang_dir, self.txt_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.glossary_path = self.root / "glossary.json"
        self.settings = self._load_settings()
        if not self.glossary_path.exists():
            glossary.save(self.glossary_path, glossary.default())
        self._txt_hash: dict[str, str] = {}

    # ---------- 設定 ----------

    def _load_settings(self) -> Settings:
        if self.settings_path.exists():
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            s = Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
        else:
            s = Settings()
        if not s.plsql_lang_dir:
            found = find_plsql_lang_dir()
            s.plsql_lang_dir = str(found) if found else ""
        return s

    def save_settings(self) -> None:
        self.settings_path.write_text(json.dumps(asdict(self.settings), ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def installed_dir(self) -> Path:
        return Path(self.settings.plsql_lang_dir)

    def load_glossary(self) -> glossary.Glossary:
        return glossary.load(self.glossary_path)

    def save_glossary(self, g: glossary.Glossary) -> None:
        glossary.save(self.glossary_path, g)

    # ---------- 清單 ----------

    def list_installed(self) -> list[LangInfo]:
        if not self.installed_dir.is_dir():
            return []
        return [LangInfo(p.name, p, p.stat().st_size, p.stat().st_mtime, (self.lang_dir / p.name).exists())
                for p in sorted(self.installed_dir.glob("*.lang"))]

    def list_workspace(self) -> list[LangInfo]:
        out = []
        for p in sorted(self.lang_dir.glob("*.lang")):
            inst = self.installed_dir / p.name
            deployed = inst.exists() and inst.read_bytes() == p.read_bytes()
            out.append(LangInfo(p.name, p, p.stat().st_size, p.stat().st_mtime, True, deployed))
        return out

    def txt_path(self, name: str) -> Path:
        return self.txt_dir / (Path(name).stem + ".txt")

    # ---------- 匯入／存檔 ----------

    def backup(self, path: Path, prefix: str = "") -> Path:
        dst = self.backup_dir / f"{prefix}{path.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}{path.suffix}"
        shutil.copy2(path, dst)
        return dst

    def import_lang(self, name: str, overwrite: bool = False) -> None:
        src, dst = self.installed_dir / name, self.lang_dir / name
        data = src.read_bytes()
        plain = langcrypt.decrypt(data)
        langfile.parse(plain)  # 格式錯誤就拋出 LangFormatError，不匯入
        if dst.exists() and dst.read_bytes() != data:
            if not overwrite:
                raise ImportConflict(name)
            self.backup(dst)
        langfile.atomic_write(dst, data)
        self.write_txt(name, plain)

    def load(self, name: str) -> LangFile:
        return langfile.load(self.lang_dir / name)

    def save(self, name: str, lf: LangFile) -> Path:
        target = self.lang_dir / name
        plain = langfile.serialize(lf)
        if target.exists():
            self.backup(target)
        langfile.atomic_write(target, langcrypt.encrypt(plain))
        self.write_txt(name, plain)
        return target

    # ---------- 記事本 .txt ----------

    def write_txt(self, name: str, plain: bytes) -> None:
        langfile.atomic_write(self.txt_path(name), plain)
        self._txt_hash[name] = _hash(plain)

    def sync_txt(self, name: str, lf: LangFile) -> None:
        """編輯器開啟 SLAVE 時呼叫：讓 .txt 與程式內的正本一致。"""
        self.write_txt(name, langfile.serialize(lf))

    def txt_changed(self, name: str) -> bool:
        p = self.txt_path(name)
        return p.exists() and _hash(p.read_bytes()) != self._txt_hash.get(name)

    def acknowledge_txt(self, name: str) -> None:
        """.txt 讀取失敗時呼叫，避免同一個錯誤每秒都跳出來；使用者再次存檔 .txt 後才會重新偵測。"""
        self._txt_hash[name] = _hash(self.txt_path(name).read_bytes())

    def load_txt(self, name: str) -> LangFile:
        """讀取被記事本修改過的 .txt。非 UTF-8 拋出 UnicodeDecodeError，格式錯誤拋出 LangFormatError。"""
        raw = self.txt_path(name).read_bytes()
        lf = langfile.parse(langcrypt.normalize_text(raw))
        self._txt_hash[name] = _hash(raw)
        return lf

    # ---------- 部署 ----------

    def deploy(self, name: str, elevate: Callable[[Path, Path], bool]) -> DeployResult:
        src, dst = self.lang_dir / name, self.installed_dir / name
        data = src.read_bytes()
        backup = None
        if dst.exists():
            if dst.read_bytes() == data:
                return DeployResult(True, False, "PL/SQL Developer 裡的檔案已經是最新的")
            backup = self.backup(dst, prefix="installed_")
        try:
            langfile.atomic_write(dst, data)
        except PermissionError:
            if not elevate(src, dst):
                return DeployResult(False, False, "沒有寫入：使用者取消了 UAC，或系統管理員複製失敗。修改仍保留在工作區。", backup)
        if not dst.exists() or dst.read_bytes() != data:
            return DeployResult(False, False, f"寫入後讀回的內容不一致。原檔備份在：{backup}", backup)
        return DeployResult(True, True, "已部署，重新啟動 PL/SQL Developer 後生效。", backup)
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/core/test_workspace.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/core/workspace.py tests/core/test_workspace.py
git commit -m "feat(core): 工作區匯入、存檔、記事本同步與部署" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 7: 表格 model、篩選、復原指令、淺色主題

**Files:**
- Create: `pllangstudio/ui/theme.py`、`pllangstudio/ui/compare_model.py`、`pllangstudio/ui/commands.py`
- Test: `tests/ui/test_compare_model.py`

**Interfaces:**
- Consumes: `compare.align/get_text/set_text/row_status`、`Status`、`STATUS_LABEL`、`FIELD_LABEL`
- Produces: `apply_light_theme(app)`；`COLUMNS`、`COL_NO…COL_SLAVE`；`CompareModel(undo_stack)`：`.load(master, slave, exceptions, baseline=None)`、`.rows/.status/.issues/.original/.exceptions/.master/.slave`、`master_text(i)`、`slave_text(i)`、`row_of_key(key)`、`row_of_ref(ref)`、`counts()`（含 `'ALL'`）、`modified_count()`、`has_errors()`、`is_editable(i)`、`request_edit([(列, 新文字)], label)`、`apply_text(i, text)`、`mark_saved()`、signal `countsChanged`；`CompareFilter`：`SCOPES`、`set_status(Status|None)`、`set_search(text, scope)`；`EditCommand(model, [(列, 舊, 新)], label)`

所有修改（格子、詳細區、批次）都經過 `request_edit`，整批是一個復原步驟。MASTER 欄與多行列的格子不可編輯。篩選用 `beginFilterChange()`／`endFilterChange(Direction.Rows)`（PySide6 6.12 已不建議用 `invalidateFilter()`）。

- [ ] **Step: 寫測試 `tests/ui/test_compare_model.py`**

```python
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.compare import Status
from pllangstudio.ui.compare_model import COL_MASTER, COL_SLAVE, CompareFilter, CompareModel

pytestmark = needs_lang_dir


@pytest.fixture
def model(qtbot):
    m = CompareModel(QUndoStack())
    m.load(langfile.load(LANG_DIR / "Chinese.lang"), langfile.load(LANG_DIR / "Taiwan.lang"), ["游標", "批准"])
    return m


def find_row(model, slave_text):
    return next(i for i in range(model.rowCount()) if model.slave_text(i) == slave_text)


def test_row_count_and_counts(model):
    assert model.rowCount() == 6672
    c = model.counts()
    assert c["ALL"] == 6672 and c[Status.SIMPLIFIED] == 1 and c[Status.MODIFIED] == 0


def test_master_not_editable_slave_editable(model):
    i = find_row(model, "&取消")
    assert not model.flags(model.index(i, COL_MASTER)) & Qt.ItemIsEditable
    assert model.flags(model.index(i, COL_SLAVE)) & Qt.ItemIsEditable
    assert not model.setData(model.index(i, COL_MASTER), "改")


def test_edit_marks_modified_and_undo_restores(model):
    i = find_row(model, "&取消")
    assert model.setData(model.index(i, COL_SLAVE), "&取消X")
    assert model.slave_text(i) == "&取消X" and Status.MODIFIED in model.status[i]
    assert model.modified_count() == 1
    model.undo_stack.undo()
    assert model.slave_text(i) == "&取消" and Status.MODIFIED not in model.status[i]


def test_placeholder_error_flagged(model):
    i = next(i for i in range(model.rowCount()) if "%1" in (model.slave_text(i) or ""))
    model.request_edit([(i, model.slave_text(i).replace("%1", ""))], "測試")
    assert Status.ERROR in model.status[i] and model.has_errors() == [i]


def test_batch_is_single_undo_step(model):
    rows = [find_row(model, "&取消"), find_row(model, "定義")]
    model.request_edit([(rows[0], "A"), (rows[1], "B")], "批次")
    assert model.undo_stack.count() == 1
    model.undo_stack.undo()
    assert model.slave_text(rows[0]) == "&取消" and model.slave_text(rows[1]) == "定義"


def test_mark_saved_clears_modified(model):
    i = find_row(model, "&取消")
    model.request_edit([(i, "改")], "測試")
    model.mark_saved()
    assert model.modified_count() == 0 and model.undo_stack.isClean()


def test_filter_by_status_and_search(model):
    f = CompareFilter()
    f.setSourceModel(model)
    f.set_status(Status.SIMPLIFIED)
    assert f.rowCount() == 1
    f.set_status(None)
    f.set_search("tablespace", "英文")
    assert 0 < f.rowCount() < 200
    f.set_search("天后", "SLAVE")
    assert f.rowCount() == 1
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/ui/test_compare_model.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pllangstudio.ui.compare_model'`

- [ ] **Step: 實作 `pllangstudio/ui/theme.py`**

```python
"""固定使用淺色主題：表格的狀態底色是淺色系，深色模式下白字會看不見。"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    for role, color in ((QPalette.Window, "#f3f3f3"), (QPalette.WindowText, "#1a1a1a"),
                        (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f5f7fa"),
                        (QPalette.Text, "#1a1a1a"), (QPalette.Button, "#ececec"),
                        (QPalette.ButtonText, "#1a1a1a"), (QPalette.ToolTipBase, "#ffffdc"),
                        (QPalette.ToolTipText, "#1a1a1a"), (QPalette.Highlight, "#3874d8"),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.PlaceholderText, "#888888")):
        p.setColor(role, QColor(color))
    app.setPalette(p)
```

- [ ] **Step: 實作 `pllangstudio/ui/commands.py`**

```python
"""可復原的編輯步驟（見 ADR-0010：整批算一個步驟）。"""

from PySide6.QtGui import QUndoCommand


class EditCommand(QUndoCommand):
    def __init__(self, model, edits: list[tuple[int, str, str]], label: str):
        super().__init__(f"{label}（{len(edits)} 個字串）")
        self.model = model
        self.edits = edits  # (列, 修改前, 修改後)

    def redo(self):
        for i, _old, new in self.edits:
            self.model.apply_text(i, new)

    def undo(self):
        for i, old, _new in reversed(self.edits):
            self.model.apply_text(i, old)
```

- [ ] **Step: 實作 `pllangstudio/ui/compare_model.py`**

```python
"""對照表格的 model 與篩選（見 ADR-0007）。"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtGui import QUndoStack

from ..core import compare
from ..core.compare import STATUS_LABEL, Row, Status
from ..core.langfile import FIELD_LABEL, LangFile

COLUMNS = ["#", "狀態", "識別碼", "欄位", "英文", "MASTER", "SLAVE"]
COL_NO, COL_STATUS, COL_KEY, COL_FIELD, COL_SOURCE, COL_MASTER, COL_SLAVE = range(7)
STATUS_ORDER = [Status.ERROR, Status.MODIFIED, Status.SIMPLIFIED, Status.UNTRANSLATED,
                Status.ONE_SIDED, Status.WARNING, Status.DIFFERENT]
COLORS = {
    Status.ERROR: "#f8d0d0", Status.MODIFIED: "#d6e6ff", Status.SIMPLIFIED: "#ffd6d6",
    Status.UNTRANSLATED: "#ffe2bf", Status.ONE_SIDED: "#e4e4e4", Status.DIFFERENT: "#fff6c8",
}
GROUP_SHADE = ("#ffffff", "#f5f7fa")


def one_line(text: str | None) -> str:
    return "" if text is None else text.replace("\n", " ⏎ ")


class CompareModel(QAbstractTableModel):
    countsChanged = Signal()

    def __init__(self, undo_stack: QUndoStack, parent=None):
        super().__init__(parent)
        self.undo_stack = undo_stack
        self.master: LangFile | None = None
        self.slave: LangFile | None = None
        self.rows: list[Row] = []
        self.original: list[str | None] = []
        self.status: list[set[Status]] = []
        self.issues: list[list] = []
        self.exceptions: list[str] = []
        self._by_ref: dict = {}
        self._by_key: dict = {}
        self._entry_rows: dict[int, list[int]] = {}

    # ---------- 載入 ----------

    def load(self, master: LangFile, slave: LangFile, exceptions: list[str],
             baseline: LangFile | None = None) -> None:
        """baseline：判斷「已修改」的比較基準（預設就是 slave 本身）。
        從記事本 .txt 載入時，傳入工作區裡的 .lang，修改過的字串才會標成 ✎。"""
        self.beginResetModel()
        self.master, self.slave, self.exceptions = master, slave, list(exceptions)
        self.rows = compare.align(master, slave)
        if baseline is None:
            self.original = [self.slave_text(i) for i in range(len(self.rows))]
        else:
            b_by_key = {e.key: k for k, e in enumerate(baseline.entries)}
            self.original = [compare.get_text(baseline, b_by_key.get(r.key), r.field, r.item) for r in self.rows]
        self._by_ref = {r.ref: i for i, r in enumerate(self.rows) if r.s_index is not None}
        self._by_key, self._entry_rows = {}, {}
        for i, r in enumerate(self.rows):
            self._by_key.setdefault(r.key, i)
            if r.s_index is not None:
                self._entry_rows.setdefault(r.s_index, []).append(i)
        self.status, self.issues = [], []
        for i in range(len(self.rows)):
            s, iss = self._compute(i)
            self.status.append(s)
            self.issues.append(iss)
        self.undo_stack.clear()
        self.endResetModel()
        self.countsChanged.emit()

    def _compute(self, i: int):
        return compare.row_status(self.rows[i], self.master, self.slave, self.original[i], self.exceptions)

    # ---------- 查詢 ----------

    def master_text(self, i: int) -> str | None:
        r = self.rows[i]
        return compare.get_text(self.master, r.m_index, r.field, r.item)

    def slave_text(self, i: int) -> str | None:
        r = self.rows[i]
        return compare.get_text(self.slave, r.s_index, r.field, r.item)

    def row_of_key(self, key) -> int | None:
        return self._by_key.get(key)

    def row_of_ref(self, ref) -> int | None:
        return self._by_ref.get(ref)

    def counts(self) -> Counter:
        c = Counter()
        for s in self.status:
            c.update(s)
        c["ALL"] = len(self.rows)
        return c

    def modified_count(self) -> int:
        return sum(Status.MODIFIED in s for s in self.status)

    def has_errors(self) -> list[int]:
        return [i for i, s in enumerate(self.status) if Status.ERROR in s]

    def is_editable(self, i: int) -> bool:
        return self.rows[i].s_index is not None

    # ---------- 修改 ----------

    def request_edit(self, edits: list[tuple[int, str]], label: str) -> None:
        """所有修改都經過這裡，包成一個可以復原的步驟。"""
        from .commands import EditCommand
        real = [(i, self.slave_text(i), new) for i, new in edits if self.slave_text(i) != new]
        if real:
            self.undo_stack.push(EditCommand(self, real, label))

    def apply_text(self, i: int, text: str) -> None:
        r = self.rows[i]
        compare.set_text(self.slave, r.s_index, r.field, r.item, text)
        # 同一個欄位的其他列也可能受影響（多行欄位），一起重算
        for j in self._entry_rows[r.s_index]:
            self.status[j], self.issues[j] = self._compute(j)
            self.dataChanged.emit(self.index(j, 0), self.index(j, len(COLUMNS) - 1))
        self.countsChanged.emit()

    def mark_saved(self) -> None:
        self.original = [self.slave_text(i) for i in range(len(self.rows))]
        for i in range(len(self.rows)):
            self.status[i], self.issues[i] = self._compute(i)
        self.undo_stack.setClean()
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))
        self.countsChanged.emit()

    # ---------- Qt model 介面 ----------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        i, col = index.row(), index.column()
        r, st = self.rows[i], self.status[i]
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == COL_NO:
                return i + 1
            if col == COL_STATUS:
                return "".join(s.value for s in STATUS_ORDER if s in st)
            if col == COL_KEY:
                return ".".join(r.key)
            if col == COL_FIELD:
                label = FIELD_LABEL[r.field]
                return f"{label}（多行）" if r.item is None else (f"{label} {r.item + 1}" if r.field.name == "ITEMS" else label)
            text = {COL_SOURCE: r.source, COL_MASTER: self.master_text(i), COL_SLAVE: self.slave_text(i)}[col]
            return text if role == Qt.EditRole else one_line(text)
        if role == Qt.ToolTipRole:
            if col == COL_STATUS:
                lines = [STATUS_LABEL[s] for s in STATUS_ORDER if s in st] + [i_.message for i_ in self.issues[i]]
                return "\n".join(lines) or None
            if col in (COL_SOURCE, COL_MASTER, COL_SLAVE):
                return {COL_SOURCE: r.source, COL_MASTER: self.master_text(i), COL_SLAVE: self.slave_text(i)}[col]
        if role == Qt.BackgroundRole:
            if col in (COL_STATUS, COL_SLAVE):
                for s in STATUS_ORDER:
                    if s in st and s in COLORS:
                        return QBrush(QColor(COLORS[s]))
            key_index = r.s_index if r.s_index is not None else r.m_index
            return QBrush(QColor(GROUP_SHADE[key_index % 2]))
        if role == Qt.ForegroundRole and col == COL_MASTER:
            return QBrush(QColor("#555555"))
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == COL_SLAVE and self.rows[index.row()].item is not None and self.is_editable(index.row()):
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not (self.flags(index) & Qt.ItemIsEditable):
            return False
        text = str(value)
        if "\n" in text:
            return False
        self.request_edit([(index.row(), text)], "編輯字串")
        return True


class CompareFilter(QSortFilterProxyModel):
    SCOPES = {"全部": (COL_KEY, COL_SOURCE, COL_MASTER, COL_SLAVE), "英文": (COL_SOURCE,),
              "MASTER": (COL_MASTER,), "SLAVE": (COL_SLAVE,), "識別碼": (COL_KEY,)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_filter: Status | None = None
        self.text = ""
        self.scope = "全部"

    def set_status(self, status: Status | None) -> None:
        self.beginFilterChange()
        self.status_filter = status
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_search(self, text: str, scope: str) -> None:
        self.beginFilterChange()
        self.text, self.scope = text.lower(), scope
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row, source_parent):
        m: CompareModel = self.sourceModel()
        if self.status_filter is not None and self.status_filter not in m.status[source_row]:
            return False
        if self.text:
            for col in self.SCOPES[self.scope]:
                v = m.data(m.index(source_row, col), Qt.EditRole)
                if v and self.text in str(v).lower():
                    return True
            return False
        return True
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/ui/test_compare_model.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/ui/theme.py pllangstudio/ui/commands.py pllangstudio/ui/compare_model.py tests/ui/test_compare_model.py
git commit -m "feat(ui): 對照表格 model、篩選與復原" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 8: 畫面元件：詳細區、檔案清單、批次預覽、用語表編輯器

**Files:**
- Create: `pllangstudio/ui/detail_panel.py`、`pllangstudio/ui/file_panel.py`、`pllangstudio/ui/batch_dialog.py`、`pllangstudio/ui/glossary_dialog.py`
- Test: `tests/ui/test_widgets.py`

**Interfaces:**
- Consumes: `CompareModel`（`rows/master/slave/original/exceptions/is_editable/master_text/slave_text`）、`batch.Change`、`Glossary/Rule`、`LangInfo`、`validate.simplified_spans`
- Produces: `diff_html(master, slave, exceptions)->str`、`DetailPanel`（`show_row(model, i)`、signal `applyRequested(int, str)`）；`FilePanel`（`refresh(installed, workspace, master, slave)`、signals `setMaster/setSlave/importRequested/openTxt/openFolder`）；`PreviewDialog(title, changes)`（`.table`、`.summary`、`checked()`）、`ReplaceDialog`（`.find/.replace/.regex/.case`）；`GlossaryDialog(g)`（`glossary()`、`_move(step)`）、常數 `APPLY = 2`

- [ ] **Step: 寫測試 `tests/ui/test_widgets.py`**

```python
from PySide6.QtCore import Qt

from pllangstudio.core.batch import Change
from pllangstudio.core.compare import Row
from pllangstudio.core.glossary import Glossary, Rule
from pllangstudio.core.langfile import Field
from pllangstudio.ui.batch_dialog import PreviewDialog
from pllangstudio.ui.detail_panel import diff_html
from pllangstudio.ui.glossary_dialog import GlossaryDialog


def test_diff_html_marks_changes_and_simplified():
    h = diff_html("定义", "定后", [])
    assert "定" in h and "ff8080" in h  # 「后」是簡體字，標紅底
    assert "ffd7d7" in h  # MASTER 的「义」被標成差異


def test_preview_dialog_unchecked_rows_are_excluded(qtbot):
    row = Row(("W", "Btn", "Button"), Field.CAPTION, 0, "Save", 0, 0)
    changes = [Change(row, "儲存", "存檔"), Change(row, "取消", "取消X")]
    dlg = PreviewDialog("測試", changes)
    qtbot.addWidget(dlg)
    dlg.table.item(1, 0).setCheckState(Qt.Unchecked)
    assert dlg.checked() == [changes[0]]
    assert "勾選 1 個" in dlg.summary.text()


def test_glossary_dialog_roundtrip_and_move(qtbot):
    g = Glossary([Rule("配置", "設定"), Rule("新建", "新增", ["重新建"], enabled=False)], ["游標"])
    dlg = GlossaryDialog(g)
    qtbot.addWidget(dlg)
    assert dlg.glossary() == g
    dlg.table.setCurrentCell(1, 1)
    dlg._move(-1)
    assert [r.find for r in dlg.glossary().rules] == ["新建", "配置"]
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/ui/test_widgets.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pllangstudio.ui.batch_dialog'`

- [ ] **Step: 實作 `pllangstudio/ui/detail_panel.py`**

```python
"""下方詳細區：元件路徑、說明註解、字元級差異、SLAVE 多行編輯。"""

from __future__ import annotations

import difflib
import html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core.langfile import FIELD_LABEL
from ..core.validate import simplified_spans


def diff_html(master: str, slave: str, exceptions: list[str]) -> str:
    """MASTER 與 SLAVE 的字元級差異；SLAVE 的殘留簡體字標紅底。"""
    red = {a for a, _ in simplified_spans(slave, exceptions)}
    m_out, s_out = [], []
    sm = difflib.SequenceMatcher(None, master, slave, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        m_part = html.escape(master[a1:a2])
        m_out.append(m_part if op == "equal" else f'<span style="background:#ffd7d7">{m_part}</span>')
        for k in range(b1, b2):
            ch = html.escape(slave[k])
            if k in red:
                s_out.append(f'<span style="background:#ff8080;color:white">{ch}</span>')
            elif op != "equal":
                s_out.append(f'<span style="background:#d7f5d7">{ch}</span>')
            else:
                s_out.append(ch)
    br = lambda s: "".join(s).replace("\n", "<br>")
    return (f"<b>MASTER：</b>{br(m_out)}<br><b>SLAVE&nbsp;&nbsp;：</b>{br(s_out)}")


class DetailPanel(QWidget):
    applyRequested = Signal(int, str)  # (列, 新文字)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row: int | None = None
        self.path = QLabel()
        self.path.setWordWrap(True)
        self.comments = QLabel()
        self.comments.setWordWrap(True)
        self.comments.setStyleSheet("color:#666")
        self.diff = QTextBrowser()
        self.diff.setMaximumHeight(90)
        self.editor = QPlainTextEdit()
        self.editor.setMaximumHeight(90)
        self.apply_btn = QPushButton("套用")
        self.revert_btn = QPushButton("還原")
        self.apply_btn.clicked.connect(self._apply)
        self.revert_btn.clicked.connect(self._revert)

        buttons = QVBoxLayout()
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.revert_btn)
        buttons.addStretch()
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.editor)
        edit_row.addLayout(buttons)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        for w in (self.path, self.comments, self.diff):
            lay.addWidget(w)
        lay.addLayout(edit_row)
        self.show_row(None, None)

    def show_row(self, model, i: int | None) -> None:
        self.model, self.row = model, i
        enabled = i is not None and model.is_editable(i)
        self.editor.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.revert_btn.setEnabled(enabled)
        if i is None:
            self.path.setText("（未選取）")
            self.comments.clear()
            self.diff.clear()
            self.editor.clear()
            return
        r = model.rows[i]
        lf = model.slave if r.s_index is not None else model.master
        e = lf.entries[r.s_index if r.s_index is not None else r.m_index]
        self.path.setText(f"<b>{' &gt; '.join(html.escape(x) for x in r.key)}</b>　欄位：{FIELD_LABEL[r.field]}")
        self.comments.setText("說明：" + (" / ".join(c for c in e.comments if c) or "（無）"))
        self.diff.setHtml(diff_html(model.master_text(i) or "", model.slave_text(i) or "", model.exceptions))
        self.editor.setPlainText(model.slave_text(i) or "")

    def _apply(self) -> None:
        if self.row is not None:
            text = self.editor.toPlainText()
            if self.model.rows[self.row].item is not None:
                text = text.replace("\n", " ")  # 單行字串不能有換行
            self.applyRequested.emit(self.row, text)

    def _revert(self) -> None:
        if self.row is not None:
            self.applyRequested.emit(self.row, self.model.original[self.row] or "")
```

- [ ] **Step: 實作 `pllangstudio/ui/file_panel.py`**

```python
"""左側檔案清單：PL/SQL 語言檔、工作區兩個分頁。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTabWidget, QTreeWidget, QTreeWidgetItem

from ..core.workspace import LangInfo


def _tree(headers: list[str]) -> QTreeWidget:
    t = QTreeWidget()
    t.setHeaderLabels(headers)
    t.setRootIsDecorated(False)
    t.setContextMenuPolicy(Qt.CustomContextMenu)
    return t


class FilePanel(QTabWidget):
    setMaster = Signal(str)
    setSlave = Signal(str)
    importRequested = Signal(str)
    openTxt = Signal(str)
    openFolder = Signal(str)  # 檔案的完整路徑

    def __init__(self, parent=None):
        super().__init__(parent)
        self.installed = _tree(["PL/SQL 語言檔", "大小", "日期", "已匯入"])
        self.workspace = _tree(["工作區語言檔", "角色", "已部署"])
        self.addTab(self.installed, "PL/SQL 語言檔")
        self.addTab(self.workspace, "工作區")
        self.installed.customContextMenuRequested.connect(lambda p: self._menu(self.installed, p, installed=True))
        self.workspace.customContextMenuRequested.connect(lambda p: self._menu(self.workspace, p, installed=False))
        self.workspace.itemDoubleClicked.connect(lambda item, _c: self.setSlave.emit(item.text(0)))

    def refresh(self, installed: list[LangInfo], workspace: list[LangInfo], master: str, slave: str) -> None:
        self.installed.clear()
        for info in installed:
            item = QTreeWidgetItem([info.name, f"{info.size // 1024:,} KB",
                                    datetime.fromtimestamp(info.mtime).strftime("%Y-%m-%d"), "✓" if info.imported else ""])
            item.setData(0, Qt.UserRole, str(info.path))
            self.installed.addTopLevelItem(item)
        self.workspace.clear()
        for info in workspace:
            role = "M" if info.name == master else ("S" if info.name == slave else "")
            item = QTreeWidgetItem([info.name, role, "✓" if info.deployed else "未部署"])
            item.setData(0, Qt.UserRole, str(info.path))
            self.workspace.addTopLevelItem(item)
        for t in (self.installed, self.workspace):
            t.resizeColumnToContents(0)

    def _menu(self, tree: QTreeWidget, pos, installed: bool) -> None:
        item = tree.itemAt(pos)
        if not item:
            return
        name, path = item.text(0), item.data(0, Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("設為 MASTER", lambda: self.setMaster.emit(name))
        menu.addAction("設為 SLAVE", lambda: self.setSlave.emit(name))
        if installed:
            menu.addAction("匯入工作區", lambda: self.importRequested.emit(name))
        else:
            menu.addAction("用記事本開 .txt", lambda: self.openTxt.emit(name))
        menu.addAction("開啟所在資料夾", lambda: self.openFolder.emit(path))
        menu.exec(tree.viewport().mapToGlobal(pos))
```

- [ ] **Step: 實作 `pllangstudio/ui/batch_dialog.py`**

```python
"""批次操作：尋找取代輸入框，以及共用的「預覽並勾選」對話框（見 ADR-0010）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.batch import Change


class PreviewDialog(QDialog):
    """列出所有會被修改的字串，每一列可以取消勾選。"""

    def __init__(self, title: str, changes: list[Change], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} — 預覽")
        self.resize(1000, 600)
        self.changes = changes
        self.table = QTableWidget(len(changes), 4)
        self.table.setHorizontalHeaderLabels(["識別碼", "英文", "修改前", "修改後"])
        for r, c in enumerate(changes):
            key = QTableWidgetItem(".".join(c.row.key))
            key.setFlags(key.flags() | Qt.ItemIsUserCheckable)
            key.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, key)
            for col, text in ((1, c.row.source), (2, c.before), (3, c.after)):
                self.table.setItem(r, col, QTableWidgetItem(text.replace("\n", " ⏎ ")))
        self.table.resizeColumnsToContents()
        self.summary = QLabel()
        all_btn, none_btn = QPushButton("全選"), QPushButton("全不選")
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.table.itemChanged.connect(self._update_summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("套用")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        top = QHBoxLayout()
        top.addWidget(self.summary)
        top.addStretch()
        top.addWidget(all_btn)
        top.addWidget(none_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addWidget(buttons)
        self._update_summary()

    def _set_all(self, state) -> None:
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)

    def _update_summary(self, *_):
        self.summary.setText(f"共 {len(self.changes)} 個字串，勾選 {len(self.checked())} 個")

    def checked(self) -> list[Change]:
        return [c for r, c in enumerate(self.changes) if self.table.item(r, 0).checkState() == Qt.Checked]


class ReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("在 SLAVE 中尋找取代")
        self.find = QLineEdit()
        self.replace = QLineEdit()
        self.regex = QCheckBox("規則運算式")
        self.case = QCheckBox("區分大小寫")
        self.case.setChecked(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("預覽")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("尋找：", self.find)
        form.addRow("取代為：", self.replace)
        form.addRow(self.regex)
        form.addRow(self.case)
        form.addRow(buttons)
```

- [ ] **Step: 實作 `pllangstudio/ui/glossary_dialog.py`**

```python
"""用語對照表編輯器。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.glossary import Glossary, Rule

APPLY = 2  # 自訂的 done() 結果：儲存並套用到 SLAVE


class GlossaryDialog(QDialog):
    def __init__(self, g: Glossary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("用語對照表")
        self.resize(760, 560)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["啟用", "尋找", "取代為", "例外（以 , 分隔）"])
        for rule in g.rules:
            self._add(rule)
        self.exceptions = QLineEdit(", ".join(g.simplified_exceptions))

        add, delete = QPushButton("新增"), QPushButton("刪除")
        up, down = QPushButton("上移"), QPushButton("下移")
        add.clicked.connect(lambda: self._add(Rule("", "")))
        delete.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        side = QVBoxLayout()
        for b in (add, delete, up, down):
            side.addWidget(b)
        side.addStretch()
        body = QHBoxLayout()
        body.addWidget(self.table)
        body.addLayout(side)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("儲存")
        apply_btn = buttons.addButton("儲存並套用到 SLAVE…", QDialogButtonBox.ActionRole)
        apply_btn.clicked.connect(lambda: self.done(APPLY))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("規則依清單順序套用，較長的詞請排在前面（例如「配置文件」在「配置」前面）。"))
        lay.addLayout(body)
        lay.addWidget(QLabel("殘留簡體字的例外詞（以 , 分隔）："))
        lay.addWidget(self.exceptions)
        lay.addWidget(buttons)

    def _add(self, rule: Rule) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._fill(r, rule)

    def _fill(self, r: int, rule: Rule) -> None:
        on = QTableWidgetItem()
        on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        on.setCheckState(Qt.Checked if rule.enabled else Qt.Unchecked)
        self.table.setItem(r, 0, on)
        for col, text in ((1, rule.find), (2, rule.replace), (3, ", ".join(rule.exceptions))):
            self.table.setItem(r, col, QTableWidgetItem(text))

    def _rule(self, r: int) -> Rule:
        text = lambda c: (self.table.item(r, c).text() if self.table.item(r, c) else "").strip()
        return Rule(text(1), text(2), [x.strip() for x in text(3).split(",") if x.strip()],
                    self.table.item(r, 0).checkState() == Qt.Checked)

    def _move(self, step: int) -> None:
        r = self.table.currentRow()
        t = r + step
        if r < 0 or not 0 <= t < self.table.rowCount():
            return
        a, b = self._rule(r), self._rule(t)
        self._fill(r, b)
        self._fill(t, a)
        self.table.setCurrentCell(t, 1)

    def glossary(self) -> Glossary:
        rules = [self._rule(r) for r in range(self.table.rowCount())]
        return Glossary([x for x in rules if x.find],
                        [x.strip() for x in self.exceptions.text().split(",") if x.strip()])
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/ui/test_widgets.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/ui/detail_panel.py pllangstudio/ui/file_panel.py pllangstudio/ui/batch_dialog.py pllangstudio/ui/glossary_dialog.py tests/ui/test_widgets.py
git commit -m "feat(ui): 詳細區、檔案清單、批次預覽與用語表編輯器" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 9: 主視窗、UAC、程式設定與進入點

**Files:**
- Create: `pllangstudio/elevate.py`、`pllangstudio/appconfig.py`、`pllangstudio/ui/main_window.py`、`pllangstudio/__main__.py`
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: Task 2～8 的全部介面
- Produces: `elevated_copy(src, dst)->bool`；`appconfig.app_dir()`、`last_workspace()`、`remember_workspace(root)`；`MainWindow(workspace_root, elevate_fn=elevated_copy, ask=None, info=None)`：`open_workspace(root)`、`choose_plsql_dir()`、`set_pair(master, slave, confirm=True)`、`select_row(i)`、`current_row()`、`save()->bool`、`deploy()`、`open_notepad(name=None)`、`poll_txt()`、`find_replace()`、`convert_s2twp()`、`edit_glossary()`、`jump_different(step)`、`.filter_buttons`、`.model`、`.proxy`、`.ws`、`.master_name/.slave_name`；`python -m pllangstudio` 啟動。

`ask` 與 `info` 都由建構子注入，可以在測試中替換，測試不會跳出任何對話框；測試把 `APPDATA` 指到 `tmp_path`，不會改到真正的 `%APPDATA%`。

- [ ] **Step: 寫測試 `tests/ui/test_main_window.py`**

```python
import json
import shutil

import pytest
from PySide6.QtWidgets import QMessageBox

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.compare import Status
from pllangstudio.core.langfile import Field
from pllangstudio.ui.compare_model import COL_SLAVE
from pllangstudio.ui.main_window import MainWindow

pytestmark = needs_lang_dir


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    installed = tmp_path / "Languages"
    installed.mkdir()
    for n in ["Chinese.lang", "Taiwan.lang", "Japanese.lang"]:
        shutil.copy(LANG_DIR / n, installed / n)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "settings.json").write_text(json.dumps({"plsql_lang_dir": str(installed)}), encoding="utf-8")
    return root, installed


@pytest.fixture
def win(qtbot, env, monkeypatch):
    root, _ = env
    answers = []
    w = MainWindow(root, elevate_fn=lambda s, d: False, info=lambda *a, **k: None,
                   ask=lambda *a, **k: answers.pop(0) if answers else QMessageBox.Yes)
    w.answers = answers
    qtbot.addWidget(w)
    return w


def row_of(win, text):
    return next(i for i in range(win.model.rowCount()) if win.model.slave_text(i) == text)


def test_opens_default_pair_with_auto_import(win, env):
    root, _ = env
    assert (win.master_name, win.slave_name) == ("Chinese.lang", "Taiwan.lang")
    assert win.model.rowCount() == 6672
    assert (root / "lang" / "Taiwan.lang").exists() and (root / "txt" / "Taiwan.txt").exists()
    assert win.filter_buttons[None].text() == "全部 6,672"


def test_switch_slave_keeps_selected_key(win):
    i = row_of(win, "&取消")
    key = win.model.rows[i].key
    win.select_row(i)
    win.set_pair("Chinese.lang", "Japanese.lang")  # 會詢問是否匯入，ask 預設回答「是」
    assert win.slave_name == "Japanese.lang"
    assert win.model.rows[win.current_row()].key == key


def test_edit_save_and_deploy(win, env):
    root, installed = env
    i = row_of(win, "&取消")
    win.model.setData(win.model.index(i, COL_SLAVE), "&取消X")
    assert win.save()
    assert win.model.modified_count() == 0
    saved = langfile.load(root / "lang" / "Taiwan.lang")
    assert any(e.target[Field.CAPTION] == ["&取消X"] for e in saved.entries)
    win.deploy()
    assert (installed / "Taiwan.lang").read_bytes() == (root / "lang" / "Taiwan.lang").read_bytes()


def test_save_blocked_by_placeholder_error(win, env):
    root, _ = env
    before = (root / "lang" / "Taiwan.lang").read_bytes()
    i = next(i for i in range(win.model.rowCount()) if "%1" in (win.model.slave_text(i) or ""))
    win.model.request_edit([(i, win.model.slave_text(i).replace("%1", ""))], "測試")
    assert not win.save()
    assert (root / "lang" / "Taiwan.lang").read_bytes() == before


def test_notepad_edit_is_reloaded_and_marked(win, env):
    root, _ = env
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    win.poll_txt()
    i = row_of(win, "&取消N")
    assert Status.MODIFIED in win.model.status[i]


def test_conflict_keeps_table_when_user_says_no(win, env):
    root, _ = env
    i = row_of(win, "定義")
    win.model.request_edit([(i, "表格改")], "測試")
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    win.answers.append(QMessageBox.No)
    win.poll_txt()
    assert win.model.slave_text(i) == "表格改"
    assert "表格改" in txt.read_text(encoding="utf-8-sig")


def test_asks_for_plsql_dir_when_missing(qtbot, env, monkeypatch):
    root, installed = env
    (root / "settings.json").write_text(json.dumps({"plsql_lang_dir": str(root / "沒有這個目錄")}), encoding="utf-8")
    monkeypatch.setattr("pllangstudio.ui.main_window.QFileDialog.getExistingDirectory", lambda *a, **k: str(installed))
    w = MainWindow(root, info=lambda *a, **k: None, ask=lambda *a, **k: QMessageBox.Yes)
    qtbot.addWidget(w)
    assert w.ws.installed_dir == installed
    assert w.model.rowCount() == 6672
```

- [ ] **Step: 執行測試，確認失敗**

Run: `uv run pytest tests/ui/test_main_window.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'pllangstudio.ui.main_window'`

- [ ] **Step: 實作 `pllangstudio/elevate.py`**

```python
"""以系統管理員身分複製檔案（寫入 Program Files 時使用 UAC）。"""

import ctypes
from ctypes import wintypes
from pathlib import Path


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def elevated_copy(src: Path, dst: Path) -> bool:
    """跳出 UAC，以系統管理員身分執行 copy。使用者按「否」或複製失敗時回傳 False。"""
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "cmd.exe"
    info.lpParameters = f'/c copy /y "{src}" "{dst}"'
    info.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return False
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return code.value == 0
```

- [ ] **Step: 實作 `pllangstudio/appconfig.py`**

```python
"""程式本身的設定（記住上次用的工作區），存在 %APPDATA%\\PLLangStudio\\app.json。"""

import json
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _config_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "PLLangStudio" / "app.json"


def last_workspace() -> Path | None:
    p = _config_path()
    if p.exists():
        value = json.loads(p.read_text(encoding="utf-8")).get("workspace")
        return Path(value) if value else None
    return None


def remember_workspace(root: Path) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"workspace": str(root)}, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step: 實作 `pllangstudio/ui/main_window.py`**

```python
"""主視窗：工具列、檔案清單、對照表格、詳細區、狀態列。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QButtonGroup, QComboBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QSplitter, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import appconfig, elevate
from ..core import batch, compare, langfile
from ..core.compare import STATUS_LABEL, Status
from ..core.langfile import LangFormatError
from ..core.workspace import ImportConflict, Workspace
from .batch_dialog import PreviewDialog, ReplaceDialog
from .compare_model import COL_FIELD, COL_KEY, COL_MASTER, COL_NO, COL_SLAVE, COL_SOURCE, COL_STATUS, \
    CompareFilter, CompareModel
from .detail_panel import DetailPanel
from .file_panel import FilePanel
from .glossary_dialog import APPLY, GlossaryDialog

FILTERS = [(None, "全部"), (Status.DIFFERENT, None), (Status.SIMPLIFIED, None), (Status.UNTRANSLATED, None),
           (Status.ONE_SIDED, None), (Status.ERROR, None), (Status.WARNING, None), (Status.MODIFIED, None)]


class CompareTable(QTableView):
    """Enter 存入後自動跳到下一列。"""

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if hint == QAbstractItemDelegate.SubmitModelCache:
            cur = self.currentIndex()
            nxt = cur.sibling(cur.row() + 1, cur.column())
            if nxt.isValid():
                self.setCurrentIndex(nxt)


class MainWindow(QMainWindow):
    def __init__(self, workspace_root: Path, elevate_fn=elevate.elevated_copy, ask=None, info=None):
        super().__init__()
        self.elevate_fn = elevate_fn
        self.ask = ask or self._ask  # 測試時可以換掉對話框
        self.info = info or self._info
        self.undo_stack = QUndoStack(self)
        self.model = CompareModel(self.undo_stack, self)
        self.proxy = CompareFilter(self)
        self.proxy.setSourceModel(self.model)
        self.master_name = self.slave_name = ""
        self.resize(1400, 860)
        self._build_ui()
        self.open_workspace(workspace_root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_txt)
        self.timer.start(1000)

    # ---------- 畫面 ----------

    def _build_ui(self) -> None:
        tb = self.addToolBar("主要")
        tb.setMovable(False)
        self.ws_label = QLabel()
        tb.addWidget(self.ws_label)
        tb.addAction("切換…", self.choose_workspace)
        tb.addAction("PL/SQL 目錄…", self.choose_plsql_dir)
        tb.addSeparator()
        self._action(tb, "💾 加密存檔", self.save, QKeySequence.Save)
        self._action(tb, "🚀 部署", self.deploy)
        self._action(tb, "📝 記事本", self.open_notepad)
        tb.addSeparator()
        undo = self.undo_stack.createUndoAction(self, "復原")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.undo_stack.createRedoAction(self, "重做")
        redo.setShortcut(QKeySequence("Ctrl+Y"))
        tb.addAction(undo)
        tb.addAction(redo)
        tb.addSeparator()
        self._action(tb, "🔍 尋找取代", self.find_replace, QKeySequence("Ctrl+H"))
        self._action(tb, "簡→繁", self.convert_s2twp)
        self._action(tb, "📖 用語表", self.edit_glossary)

        self.files = FilePanel()
        self.files.setMaster.connect(lambda n: self.set_pair(n, self.slave_name))
        self.files.setSlave.connect(lambda n: self.set_pair(self.master_name, n))
        self.files.importRequested.connect(self.import_lang)
        self.files.openTxt.connect(lambda n: self.open_notepad(n))
        self.files.openFolder.connect(lambda p: subprocess.Popen(["explorer", "/select,", p]))

        self.master_combo, self.slave_combo = QComboBox(), QComboBox()
        self.master_combo.activated.connect(lambda: self.set_pair(self.master_combo.currentText(), self.slave_name))
        self.slave_combo.activated.connect(lambda: self.set_pair(self.master_name, self.slave_combo.currentText()))
        pick = QHBoxLayout()
        pick.addWidget(QLabel("MASTER"))
        pick.addWidget(self.master_combo)
        pick.addWidget(QLabel("🔒 唯讀"))
        pick.addSpacing(30)
        pick.addWidget(QLabel("SLAVE"))
        pick.addWidget(self.slave_combo)
        pick.addStretch()

        self.filter_group = QButtonGroup(self)
        self.filter_buttons: dict = {}
        flt = QHBoxLayout()
        for status, label in FILTERS:
            b = QToolButton()
            b.setCheckable(True)
            b.setProperty("label", label or STATUS_LABEL[status])
            self.filter_group.addButton(b)
            b.clicked.connect(lambda _=False, s=status: self.proxy.set_status(s))
            self.filter_buttons[status] = b
            flt.addWidget(b)
        self.filter_buttons[None].setChecked(True)
        flt.addSpacing(20)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋（Ctrl+F）")
        self.scope = QComboBox()
        self.scope.addItems(list(CompareFilter.SCOPES))
        self.search.textChanged.connect(self._apply_search)
        self.scope.currentTextChanged.connect(self._apply_search)
        find_act = QAction(self)
        find_act.setShortcut(QKeySequence.Find)
        find_act.triggered.connect(self.search.setFocus)
        self.addAction(find_act)
        for key, step in (("F3", 1), ("Shift+F3", -1)):
            a = QAction(self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, s=step: self.jump_different(s))
            self.addAction(a)
        flt.addWidget(self.search, 1)
        flt.addWidget(self.scope)

        self.table = CompareTable()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(22)
        for col, w in ((COL_NO, 50), (COL_STATUS, 50), (COL_KEY, 260), (COL_FIELD, 70),
                       (COL_SOURCE, 260), (COL_MASTER, 260), (COL_SLAVE, 260)):
            self.table.setColumnWidth(col, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self._show_detail())

        self.detail = DetailPanel()
        self.detail.applyRequested.connect(lambda i, t: self.model.request_edit([(i, t)], "編輯字串"))
        self.undo_stack.indexChanged.connect(lambda *_: self._show_detail())
        self.model.countsChanged.connect(self._update_counts)

        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(pick)
        lay.addLayout(flt)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(self.table)
        vsplit.addWidget(self.detail)
        vsplit.setStretchFactor(0, 4)
        lay.addWidget(vsplit)
        hsplit = QSplitter()
        hsplit.addWidget(self.files)
        hsplit.addWidget(center)
        hsplit.setSizes([300, 1100])
        self.setCentralWidget(hsplit)

        self.st_unsaved, self.st_issues, self.st_pos, self.st_deploy = QLabel(), QLabel(), QLabel(), QLabel()
        for w in (self.st_unsaved, self.st_issues, self.st_pos, self.st_deploy):
            self.statusBar().addWidget(w)
            self.statusBar().addWidget(QLabel("｜"))

    def _action(self, tb, text, slot, shortcut=None) -> QAction:
        a = tb.addAction(text, slot)
        if shortcut:
            a.setShortcut(shortcut)
        return a

    def _ask(self, title: str, text: str, buttons=QMessageBox.Yes | QMessageBox.No,
             default=QMessageBox.No) -> QMessageBox.StandardButton:
        return QMessageBox.question(self, title, text, buttons, default)

    def _info(self, title: str, text: str, error: bool = False) -> None:
        (QMessageBox.warning if error else QMessageBox.information)(self, title, text)

    # ---------- 工作區 ----------

    def open_workspace(self, root: Path) -> None:
        self.ws = Workspace(root)
        appconfig.remember_workspace(self.ws.root)
        self.ws_label.setText(f" 工作區：{self.ws.root} ")
        if not self.ws.installed_dir.is_dir():
            self.info("找不到 PL/SQL Developer", "找不到 PL/SQL Developer 的 Languages 目錄，請手動選擇。")
            self.choose_plsql_dir()
        names = {i.name for i in self.ws.list_workspace()}
        for n in (self.ws.settings.master, self.ws.settings.slave):  # 第一次使用：自動匯入預設的兩個檔案
            if n not in names and (self.ws.installed_dir / n).exists():
                self.ws.import_lang(n)
        self.master_name = self.slave_name = ""
        self.set_pair(self.ws.settings.master, self.ws.settings.slave, confirm=False)

    def choose_workspace(self) -> None:
        if not self.confirm_discard():
            return
        d = QFileDialog.getExistingDirectory(self, "選擇工作區資料夾", str(self.ws.root))
        if d:
            self.open_workspace(Path(d))

    def choose_plsql_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "選擇 PL/SQL Developer 的 Languages 目錄",
                                             self.ws.settings.plsql_lang_dir or "C:\\")
        if d:
            self.ws.settings.plsql_lang_dir = d
            self.ws.save_settings()
            self.refresh_files()

    def refresh_files(self) -> None:
        names = [i.name for i in self.ws.list_workspace()]
        for combo, cur in ((self.master_combo, self.master_name), (self.slave_combo, self.slave_name)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.setCurrentText(cur)
            combo.blockSignals(False)
        self.files.refresh(self.ws.list_installed(), self.ws.list_workspace(), self.master_name, self.slave_name)
        deployed = next((i.deployed for i in self.ws.list_workspace() if i.name == self.slave_name), None)
        self.st_deploy.setText("已部署" if deployed else "工作區有尚未部署的修改")

    def import_lang(self, name: str) -> None:
        try:
            self.ws.import_lang(name)
        except ImportConflict:
            if self.ask("工作區已有同名檔", f"工作區的 {name} 跟 PL/SQL Developer 裡的不同。\n要覆蓋嗎？（舊檔會先備份）") \
                    != QMessageBox.Yes:
                return
            self.ws.import_lang(name, overwrite=True)
        except (LangFormatError, ValueError) as e:
            self.info("無法匯入", f"{name}\n\n{e}", error=True)
            return
        self.refresh_files()

    def _ensure_imported(self, name: str) -> bool:
        if (self.ws.lang_dir / name).exists():
            return True
        if not (self.ws.installed_dir / name).exists():
            self.info("找不到檔案", name, error=True)
            return False
        if self.ask("尚未匯入", f"{name} 還沒匯入工作區，要現在匯入嗎？") != QMessageBox.Yes:
            return False
        self.import_lang(name)
        return (self.ws.lang_dir / name).exists()

    # ---------- MASTER／SLAVE ----------

    def confirm_discard(self) -> bool:
        if self.model.modified_count() == 0:
            return True
        return self.ask("尚未存檔", f"有 {self.model.modified_count()} 個字串修改還沒存檔，確定要捨棄嗎？") == QMessageBox.Yes

    def current_row(self) -> int | None:
        idx = self.table.currentIndex()
        return self.proxy.mapToSource(idx).row() if idx.isValid() else None

    def set_pair(self, master: str, slave: str, confirm: bool = True) -> None:
        if not master or not slave:
            return
        if (master, slave) == (self.master_name, self.slave_name):
            return
        if slave != self.slave_name and confirm and not self.confirm_discard():
            self.refresh_files()
            return
        if not (self._ensure_imported(master) and self._ensure_imported(slave)):
            self.refresh_files()
            return
        cur = self.current_row()
        key = self.model.rows[cur].key if cur is not None else None
        try:
            m, s = self.ws.load(master), self.ws.load(slave)
        except (LangFormatError, ValueError) as e:
            self.info("無法開啟", str(e), error=True)
            return
        self.master_name, self.slave_name = master, slave
        self.ws.settings.master, self.ws.settings.slave = master, slave
        self.ws.save_settings()
        self.model.load(m, s, self.ws.load_glossary().simplified_exceptions)
        self.ws.sync_txt(slave, s)
        self.setWindowTitle(f"PLLangStudio — {master} ↔ {slave}")
        self.refresh_files()
        self.select_row(self.model.row_of_key(key) if key else 0)

    def select_row(self, source_row: int | None) -> None:
        if source_row is None:
            return
        idx = self.proxy.mapFromSource(self.model.index(source_row, COL_NO))
        if idx.isValid():
            self.table.selectionModel().setCurrentIndex(
                idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            self.table.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def _show_detail(self) -> None:
        self.detail.show_row(self.model, self.current_row())
        cur = self.table.currentIndex()
        self.st_pos.setText(f"第 {cur.row() + 1 if cur.isValid() else 0} / {self.proxy.rowCount()} 列")

    def _update_counts(self) -> None:
        c = self.model.counts()
        for status, b in self.filter_buttons.items():
            b.setText(f"{b.property('label')} {c['ALL'] if status is None else c[status]:,}")
        self.st_unsaved.setText(f"✎ {self.model.modified_count()} 個字串未存檔")
        self.st_issues.setText(f"錯誤 {c[Status.ERROR]}／警告 {c[Status.WARNING]}")

    def _apply_search(self) -> None:
        self.proxy.set_search(self.search.text(), self.scope.currentText())

    def jump_different(self, step: int) -> None:
        start = self.table.currentIndex().row()
        n = self.proxy.rowCount()
        r = start + step
        while 0 <= r < n:
            if Status.DIFFERENT in self.model.status[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]:
                self.select_row(self.proxy.mapToSource(self.proxy.index(r, 0)).row())
                return
            r += step

    # ---------- 存檔／部署 ----------

    def save(self) -> bool:
        errors = self.model.has_errors()
        if errors:
            lines = [f"第 {i + 1} 列：{'；'.join(x.message for x in self.model.issues[i] if x.level == 'error')}"
                     for i in errors[:10]]
            self.info("有錯誤，不能存檔", "\n".join(lines) + ("\n…" if len(errors) > 10 else ""), error=True)
            self.proxy.set_status(Status.ERROR)
            self.filter_buttons[Status.ERROR].setChecked(True)
            self.select_row(errors[0])
            return False
        warnings = sum(Status.WARNING in s and Status.MODIFIED in s for s in self.model.status)
        if warnings and self.ask("有警告", f"修改過的字串中有 {warnings} 個有警告（可在「警告」篩選查看）。\n仍要存檔嗎？") \
                != QMessageBox.Yes:
            return False
        self.ws.save(self.slave_name, self.model.slave)
        self.model.mark_saved()
        self.refresh_files()
        self.statusBar().showMessage(f"已加密存檔到工作區：{self.slave_name}", 5000)
        return True

    def deploy(self) -> None:
        if self.model.modified_count() and (self.ask("尚未存檔", "要先存檔再部署嗎？") != QMessageBox.Yes or not self.save()):
            return
        target = self.ws.installed_dir / self.slave_name
        n = compare.count_differences(self.ws.load(self.slave_name), langfile.load(target)) if target.exists() else None
        text = (f"{self.slave_name} 跟 PL/SQL Developer 裡的版本有 {n} 筆不同。" if n is not None
                else f"PL/SQL Developer 裡還沒有 {self.slave_name}。")
        if self.ask("部署到 PL/SQL Developer", f"{text}\n\n要部署到：\n{target}\n嗎？（舊檔會先備份）") != QMessageBox.Yes:
            return
        res = self.ws.deploy(self.slave_name, self.elevate_fn)
        self.info("部署結果", res.message, error=not res.ok)
        self.refresh_files()

    # ---------- 記事本 ----------

    def open_notepad(self, name: str | None = None) -> None:
        name = name or self.slave_name
        if name == self.slave_name and self.model.modified_count():
            self.ws.sync_txt(name, self.model.slave)  # 讓記事本看到表格裡還沒存檔的修改
        subprocess.Popen(["notepad.exe", str(self.ws.txt_path(name))])

    def poll_txt(self) -> None:
        name = self.slave_name
        if not name or not self.ws.txt_changed(name):
            return
        try:
            new = self.ws.load_txt(name)
        except UnicodeDecodeError:
            self.ws.acknowledge_txt(name)
            self.info(".txt 編碼錯誤", "請在記事本用「另存新檔」，編碼選 UTF-8 後再存一次。", error=True)
            return
        except LangFormatError as e:
            self.ws.acknowledge_txt(name)
            self.info(".txt 格式錯誤，沒有載入", f"{e}\n\n請修正後再存一次。", error=True)
            return
        if self.model.modified_count() and self.ask(
                "兩邊都有修改", "表格和記事本都有尚未存檔的修改。\n\n是 → 改用記事本的內容（表格的修改會被捨棄）\n否 → 保留表格的修改（記事本的修改會被覆蓋）") \
                != QMessageBox.Yes:
            self.ws.sync_txt(name, self.model.slave)
            return
        cur = self.current_row()
        key = self.model.rows[cur].key if cur is not None else None
        self.model.load(self.model.master, new, self.model.exceptions, baseline=self.ws.load(name))
        self.select_row(self.model.row_of_key(key) if key else 0)
        self.statusBar().showMessage("已從記事本重新載入", 5000)

    # ---------- 批次 ----------

    def _apply_changes(self, title: str, changes: list[batch.Change]) -> None:
        if not changes:
            self.info(title, "沒有需要修改的字串。")
            return
        dlg = PreviewDialog(title, changes, self)
        if dlg.exec():
            edits = [(self.model.row_of_ref(c.row.ref), c.after) for c in dlg.checked()]
            self.model.request_edit([e for e in edits if e[0] is not None], title)

    def find_replace(self) -> None:
        dlg = ReplaceDialog(self)
        if dlg.exec() and dlg.find.text():
            try:
                changes = batch.preview_replace(self.model.rows, self.model.master, self.model.slave,
                                                dlg.find.text(), dlg.replace.text(), dlg.regex.isChecked(),
                                                dlg.case.isChecked())
            except Exception as e:  # 規則運算式寫錯
                self.info("尋找取代", f"規則運算式有誤：{e}", error=True)
                return
            self._apply_changes("尋找取代", changes)

    def convert_s2twp(self) -> None:
        selected = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        rows = [self.model.rows[i] for i in sorted(selected)] if len(selected) > 1 else self.model.rows
        self._apply_changes("簡轉繁（MASTER → SLAVE）", batch.preview_s2twp(rows, self.model.master, self.model.slave))

    def edit_glossary(self) -> None:
        dlg = GlossaryDialog(self.ws.load_glossary(), self)
        result = dlg.exec()
        if result in (1, APPLY):
            g = dlg.glossary()
            self.ws.save_glossary(g)
            self.model.exceptions = g.simplified_exceptions
            if result == APPLY:
                self._apply_changes("套用用語表",
                                    batch.preview_rules(self.model.rows, self.model.master, self.model.slave, g.rules))

    # ---------- 關閉 ----------

    def closeEvent(self, event) -> None:
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()
```

- [ ] **Step: 實作 `pllangstudio/__main__.py`**

```python
import sys

from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.core.workspace import default_root
from pllangstudio.ui.main_window import MainWindow
from pllangstudio.ui.theme import apply_light_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PLLangStudio")
    apply_light_theme(app)
    root = appconfig.last_workspace() or default_root(appconfig.app_dir())
    win = MainWindow(root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step: 執行測試，確認通過**

Run: `uv run pytest tests/ui/test_main_window.py -v`
Expected: 全部 PASS

- [ ] **Step: Commit**

```bash
git add pllangstudio/elevate.py pllangstudio/appconfig.py pllangstudio/ui/main_window.py pllangstudio/__main__.py tests/ui/test_main_window.py
git commit -m "feat(ui): 主視窗、存檔部署流程與記事本同步" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step: 實際開啟視窗目測**

Run: `uv run python -m pllangstudio`
Expected：標題 `PLLangStudio — Chinese.lang ↔ Taiwan.lang`；篩選按鈕顯示 `全部 6,672`、`殘留簡體 1`；`#` 與「狀態」欄在最左邊可見；Windows 深色模式下文字仍清楚（淺色主題）。關閉視窗。


---

### Task 10: 打包 exe、移除舊程式、文件與人工驗收

**Files:**
- Delete: `app.py`、`LangEditor.spec`（若存在）
- Modify: `README.md`、`.gitignore`

**Interfaces:**
- Consumes: `python -m pllangstudio` 進入點（`pllangstudio/__main__.py`）
- Produces: `dist\PLLangStudio.exe`

- [ ] **Step: 執行全部測試**

Run: `uv run pytest -q`
Expected：全部 PASS（97 個）

- [ ] **Step: 打包**

```bash
uv run pyinstaller --noconfirm --onefile --windowed --collect-all opencc --name PLLangStudio pllangstudio/__main__.py
```

Expected：`dist\PLLangStudio.exe`，約 52 MB。`--collect-all opencc` 不可省略，否則 exe 裡的簡轉繁會找不到設定檔。

- [ ] **Step: 啟動 exe 冒煙測試**

雙擊 `dist\PLLangStudio.exe`。Expected：
1. `dist\workspace\` 自動建立，`lang\` 內有 Chinese.lang、Taiwan.lang。
2. 表格 6,672 列，「殘留簡體」篩選後只有「%1 天后過期」。
3. 選幾列按「簡→繁」→ 預覽對話框出現（按取消，不套用）。

- [ ] **Step: 移除舊的 tkinter 版**

```bash
git rm app.py
rm -f LangEditor.spec
```

`.gitignore` 加一行 `workspace/`。

- [ ] **Step: 改寫 `README.md`**

```markdown
# PLLangStudio

PL/SQL Developer 語言編輯與比對器：MASTER（唯讀）／SLAVE（可編輯）逐字串對照 `.lang` 語言檔，
可以編輯、批次修改、檢查錯誤，加密存回工作區後再部署。

- 規格：docs/superpowers/specs/2026-10-26-pllangstudio-design.md
- 決策紀錄：docs/adr/
- 術語：CONTEXT.md

## 使用
1. 執行 `PLLangStudio.exe`。第一次執行會在 exe 旁建立 `workspace\`，並自動匯入 Chinese.lang、Taiwan.lang。
2. 在表格的 SLAVE 欄雙擊或按 F2 編輯；多行字串在下方詳細區編輯。
3. Ctrl+S 加密存檔（只寫工作區），確認後按「部署」寫回 PL/SQL Developer（會跳 UAC），重新啟動 PL/SQL Developer 生效。

## 開發
    uv run pytest
    uv run python -m pllangstudio
    uv run pyinstaller --noconfirm --onefile --windowed --collect-all opencc --name PLLangStudio pllangstudio/__main__.py
```

- [ ] **Step: Commit**

```bash
git add -A
git commit -m "chore: 打包 PLLangStudio.exe，移除舊的 tkinter 版" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step: 人工驗收（請使用者操作，對應規格第 10 節）**

| # | 操作 | 預期 |
|---|---|---|
| 1 | 開啟 exe | 預設 Chinese ↔ Taiwan，6,672 列，捲動時兩邊同列 |
| 2 | 改一個字串 → Ctrl+S → 部署 → 按 UAC「是」→ 重新啟動 PL/SQL Developer | 介面上看到修改 |
| 3 | 自動測試 `test_default_glossary_reproduces_taiwan` | 已通過 |
| 4 | 刪掉某個字串裡的 `%1` → Ctrl+S | 被擋下，顯示錯誤並跳到該列 |
| 5 | 「殘留簡體」篩選 | 只有「%1 天后過期」，沒有「游標」 |
| 6 | 部署時在 UAC 按「否」 | 顯示「修改仍保留在工作區」，Program Files 的檔案不變 |

