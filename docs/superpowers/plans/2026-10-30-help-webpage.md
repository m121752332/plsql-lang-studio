# 使用說明改為內嵌網頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 F1 改為開啟獨立的說明程式 `PLLangHelp`，以 Qt WebEngine 呈現本機靜態網頁（目錄、搜尋、截圖、跟隨主題、依畫面開對應章節）。

**Architecture:** 章節代號、網址、行程間指令放在不依賴 Qt 的 `core/helpdoc.py`。說明程式 `pllangstudio/helpviewer/` 是另一個行程，內含 `QWebEngineView`，從命令列取得初始章節與主題，之後從 stdin 逐行接收指令，stdin 關閉就結束。主程式端 `ui/help_launcher.py` 用 `QProcess` 啟動或送指令；主程式不 import 任何 WebEngine 模組。

**Tech Stack:** Python 3.14、PySide6 6.12（QtWebEngineWidgets）、pytest + pytest-qt + xdist、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-30-help-webpage-design.md`

## Global Constraints

- 一律用 `uv run …`，不直接呼叫 `python`／`pip`。
- `core/` 不可 import PySide6。主程式（`pllangstudio/ui/`、`pllangstudio/__main__.py`）不可 import `PySide6.QtWebEngine*`。
- 介面文字、網頁內容、註解、ADR 用繁體中文（台灣用語），遵守 CONTEXT.md 用詞（主語系／副語系、語言檔、筆、字串、工作區、部署、錯誤、警告…）。
- 含中文的檔案只用 Write／Edit 工具修改；commit 訊息含中文時，先用 Write 寫到 `temp/commit-msg.txt` 再 `git commit -F temp/commit-msg.txt`，之後刪掉該檔。
- Commit 訊息：Conventional Commits 前綴＋繁體中文描述，結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 測試可平行執行（xdist），暫存檔用 `tmp_path`；不寫入真實的 Languages 目錄、不碰使用者工作區與 `%APPDATA%`。
- 每個 task 結束前 `uv run pytest` 全過。
- 主題值只有 `light`、`dark` 兩種。

## 檔案結構

| 檔案 | 責任 |
|---|---|
| `pllangstudio/core/helpdoc.py`（新） | 章節代號、網址、指令格式、找說明程式 |
| `pllangstudio/resources/help/index.html`、`help.css`、`help.js`、`img/`（新） | 說明網頁 |
| `pllangstudio/helpviewer/__init__.py`、`window.py`、`__main__.py`（新） | 說明程式 |
| `pllangstudio/ui/help_launcher.py`（新） | 主程式端啟動／送指令、對話框 F1 |
| `pllangstudio/ui/main_window.py`（改） | F1 改用 launcher、各對話框掛 F1、關閉時收掉說明程式 |
| `pllangstudio/release.py`（改） | 建置兩支程式、zip 帶 `PLLangHelp\` |
| `tests/core/test_helpdoc.py`、`tests/ui/test_help_launcher.py`、`tests/ui/test_help_viewer.py`（新） | 測試 |
| `tests/conftest.py`、`tests/test_release.py`、`tests/ui/test_main_window.py`（改） | 測試 |
| `docs/adr/0019-help-webpage.md`（新）、`docs/adr/0016-*.md`、`CONTEXT.md`、`README.md`（改） | 文件 |

---

### Task 1: core/helpdoc.py

**Files:**
- Create: `pllangstudio/core/helpdoc.py`
- Test: `tests/core/test_helpdoc.py`

**Interfaces:**
- Produces:
  - `TOPICS: tuple[str, ...]`、`THEMES = ("light", "dark")`
  - `normalize_topic(topic: str | None) -> str | None`（不在 `TOPICS` 內的一律 `None`）
  - `help_url(index: Path, topic: str | None, theme: str) -> str`
  - `@dataclass(frozen=True) Command(action: str, theme: str, topic: str | None = None)`，`action` 為 `"show"` 或 `"theme"`
  - `format_command(cmd: Command) -> str`（不含換行）
  - `parse_command(line: str) -> Command | None`
  - `PROGRAM_DIR = "PLLangHelp"`、`PROGRAM_EXE = "PLLangHelp.exe"`
  - `find_help_program(exe_dir: Path) -> Path | None`

- [ ] **Step 1: 寫失敗的測試** `tests/core/test_helpdoc.py`

```python
from pathlib import Path

import pytest

from pllangstudio.core import helpdoc
from pllangstudio.core.helpdoc import Command


def test_topics_are_unique_and_include_dialog_topics():
    assert len(set(helpdoc.TOPICS)) == len(helpdoc.TOPICS)
    for t in ("replace", "batch", "glossary", "theme-font", "event-log"):
        assert t in helpdoc.TOPICS


def test_normalize_topic():
    assert helpdoc.normalize_topic("glossary") == "glossary"
    assert helpdoc.normalize_topic("nope") is None
    assert helpdoc.normalize_topic("-") is None
    assert helpdoc.normalize_topic(None) is None


def test_help_url_with_topic(tmp_path):
    index = tmp_path / "help" / "index.html"
    url = helpdoc.help_url(index, "glossary", "dark")
    assert url.startswith("file:///")
    assert url.endswith("/help/index.html?theme=dark#glossary")


def test_help_url_unknown_topic_goes_to_top(tmp_path):
    url = helpdoc.help_url(tmp_path / "index.html", "nope", "light")
    assert url.endswith("index.html?theme=light")


@pytest.mark.parametrize("cmd, line", [
    (Command("show", "dark", "glossary"), "show glossary dark"),
    (Command("show", "light", None), "show - light"),
    (Command("theme", "dark"), "theme dark"),
])
def test_command_round_trip(cmd, line):
    assert helpdoc.format_command(cmd) == line
    assert helpdoc.parse_command(line + "\n") == cmd


@pytest.mark.parametrize("line", ["", "show", "show glossary", "show glossary blue", "theme",
                                  "theme blue", "jump glossary dark", "show a b c"])
def test_parse_command_rejects_bad_lines(line):
    assert helpdoc.parse_command(line) is None


def test_parse_command_unknown_topic_shows_top():
    assert helpdoc.parse_command("show nope dark") == Command("show", "dark", None)


def test_find_help_program(tmp_path):
    assert helpdoc.find_help_program(tmp_path) is None
    exe = tmp_path / "PLLangHelp" / "PLLangHelp.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    assert helpdoc.find_help_program(tmp_path) == exe
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/core/test_helpdoc.py -q`
Expected: FAIL（`ImportError: cannot import name 'helpdoc'`）

- [ ] **Step 3: 實作** `pllangstudio/core/helpdoc.py`

```python
"""使用說明：章節代號、網址，以及主程式與說明程式之間的指令（見 ADR-0019）。

說明程式是另一個行程，主程式透過它的 stdin 一行送一個指令：
  show <章節代號或 -> <light|dark>   切到章節（- 表示頁首）、套用主題、帶到前面
  theme <light|dark>                 只換主題
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 網頁 index.html 裡每個代號都要有同名的 id（有測試檢查）
TOPICS = (
    "overview", "terms", "quick-start", "screen",
    "edit", "markers", "notepad",
    "batch", "replace", "s2twp", "glossary",
    "save-deploy", "safety",
    "theme-font", "event-log", "files",
    "shortcuts", "faq",
)
THEMES = ("light", "dark")
PROGRAM_DIR = "PLLangHelp"
PROGRAM_EXE = "PLLangHelp.exe"


@dataclass(frozen=True)
class Command:
    action: str  # "show" 或 "theme"
    theme: str
    topic: str | None = None


def normalize_topic(topic: str | None) -> str | None:
    return topic if topic in TOPICS else None


def help_url(index: Path, topic: str | None, theme: str) -> str:
    url = f"{index.resolve().as_uri()}?theme={theme}"
    topic = normalize_topic(topic)
    return f"{url}#{topic}" if topic else url


def format_command(cmd: Command) -> str:
    if cmd.action == "show":
        return f"show {cmd.topic or '-'} {cmd.theme}"
    return f"theme {cmd.theme}"


def parse_command(line: str) -> Command | None:
    """無法解析的行回傳 None，由呼叫端忽略。"""
    parts = line.split()
    if len(parts) == 3 and parts[0] == "show" and parts[2] in THEMES:
        return Command("show", parts[2], normalize_topic(parts[1]))
    if len(parts) == 2 and parts[0] == "theme" and parts[1] in THEMES:
        return Command("theme", parts[1])
    return None


def find_help_program(exe_dir: Path) -> Path | None:
    """打包後說明程式放在主程式旁邊的 PLLangHelp\\ 資料夾。"""
    path = exe_dir / PROGRAM_DIR / PROGRAM_EXE
    return path if path.is_file() else None
```

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/core/test_helpdoc.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`feat: 新增使用說明的章節代號、網址與指令格式（core/helpdoc）`

---

### Task 2: 說明網頁（HTML／CSS／JS）

**Files:**
- Create: `pllangstudio/resources/help/index.html`、`help.css`、`help.js`、`img/.gitkeep`
- Test: `tests/core/test_helpdoc.py`（加網頁結構檢查）

**Interfaces:**
- Consumes: `helpdoc.TOPICS`
- Produces（說明程式依賴的 JS 介面）：
  - `window.setTheme(theme: "light"|"dark")`：設定 `document.documentElement.dataset.theme`
  - `window.helpShow(topic: string|null, theme: "light"|"dark")`：套用主題、把 `location.hash` 換成 `#topic`（`null` 時移除）並捲到該節（`null` 時捲到頂端）
  - 載入時讀 `?theme=`，沒有就依 `prefers-color-scheme`
  - 每個章節是 `<section id="代號">`，全部平鋪在 `<main>` 下

- [ ] **Step 1: 寫失敗的測試**（加在 `tests/core/test_helpdoc.py` 尾端）

```python
from html.parser import HTMLParser

from pllangstudio import resources

INDEX = resources.path("help/index.html")


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.srcs, self.links = set(), [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in ("img", "script") and a.get("src"):
            self.srcs.append(a["src"])
        if tag == "link" and a.get("href"):
            self.links.append(a["href"])
        if tag == "a" and (a.get("href") or "").startswith("#"):
            self.links.append(a["href"])


def _parse() -> _Collect:
    p = _Collect()
    p.feed(INDEX.read_text(encoding="utf-8"))
    return p


def test_every_topic_has_a_section():
    assert set(helpdoc.TOPICS) <= _parse().ids


def test_local_files_exist_and_nothing_remote():
    p = _parse()
    for ref in p.srcs + [h for h in p.links if not h.startswith("#")]:
        assert "://" not in ref, ref  # 不連外、不用 CDN
        assert (INDEX.parent / ref).is_file(), ref


def test_in_page_links_point_to_existing_ids():
    p = _parse()
    for href in (h for h in p.links if h.startswith("#")):
        assert href[1:] in p.ids, href
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/core/test_helpdoc.py -q`
Expected: FAIL（`FileNotFoundError` … `index.html`）

- [ ] **Step 3: 實作網頁**

`index.html` 骨架（章節內文依下表從 README.md 對應段落改寫成網頁版；用 `<kbd>` 標快速鍵、`<table>` 列符號與快速鍵、`<div class="note">`／`<div class="warn">` 標提示與注意；截圖在 Task 6 加入）：

```html
<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PLLangStudio 使用說明</title>
<link rel="stylesheet" href="help.css">
<script src="help.js"></script>
</head>
<body>
<nav id="toc">
  <div class="brand">PLLangStudio 使用說明</div>
  <input id="search" type="search" placeholder="搜尋說明…" autocomplete="off">
  <p id="no-result" hidden>找不到符合的內容。</p>
  <div class="group">入門</div>
  <a href="#overview">這個工具在做什麼</a>
  <a href="#terms">先認識幾個名詞</a>
  <a href="#quick-start">第一次使用</a>
  <a href="#screen">畫面介紹</a>
  <div class="group">修改翻譯</div>
  <a href="#edit">修改一個翻譯</a>
  <a href="#markers">表格符號、錯誤與警告</a>
  <a href="#notepad">用記事本修改</a>
  <div class="group">批次工具</div>
  <a href="#batch">批次工具與預覽</a>
  <a href="#replace">尋找取代</a>
  <a href="#s2twp">簡→繁</a>
  <a href="#glossary">用語對照表</a>
  <div class="group">存檔與部署</div>
  <a href="#save-deploy">存檔和部署</a>
  <a href="#safety">安全機制與備份</a>
  <div class="group">設定與紀錄</div>
  <a href="#theme-font">主題與字型</a>
  <a href="#event-log">事件紀錄</a>
  <a href="#files">檔案放在哪裡</a>
  <div class="group">參考</div>
  <a href="#shortcuts">快速鍵一覽</a>
  <a href="#faq">常見問題</a>
</nav>
<main>
  <section id="overview"><h2>這個工具在做什麼</h2> … README §1 …</section>
  <section id="terms"><h2>先認識幾個名詞</h2> … README §2 …</section>
  <section id="quick-start"><h2>第一次使用</h2> … README §3 …</section>
  <section id="screen"><h2>畫面介紹</h2> … README §4（含右鍵選單）…</section>
  <section id="edit"><h2>修改一個翻譯</h2> … README §5 …</section>
  <section id="markers"><h2>表格符號、錯誤與警告</h2> … README §6 …</section>
  <section id="notepad"><h2>用記事本修改</h2> … README §9 …</section>
  <section id="batch"><h2>批次工具與預覽</h2> … README §7 開頭與預覽說明 …</section>
  <section id="replace"><h2>尋找取代</h2> … README §7「尋找取代」…</section>
  <section id="s2twp"><h2>簡→繁</h2> … README §7「簡→繁」…</section>
  <section id="glossary"><h2>用語對照表</h2> … README §7「用語對照表」…</section>
  <section id="save-deploy"><h2>存檔和部署</h2> … README §8 …</section>
  <section id="safety"><h2>安全機制與備份</h2> … README §12 …</section>
  <section id="theme-font"><h2>主題與字型</h2> … README §10 …</section>
  <section id="event-log"><h2>事件紀錄</h2> … README §11 …</section>
  <section id="files"><h2>檔案放在哪裡</h2> … README §15 …</section>
  <section id="shortcuts"><h2>快速鍵一覽</h2> … README §13 …</section>
  <section id="faq"><h2>常見問題</h2> … README §14 …</section>
</main>
</body>
</html>
```

（`…` 表示該節要寫入的實際內文來源；實作時必須寫成完整內容，不可留 `…`。）

`help.css`：

```css
:root, html[data-theme="light"] {
  --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --nav-bg: #f6f8fa; --border: #d1d9e0;
  --accent: #0969da; --code-bg: #eff2f5; --mark: #fff8c5;
  --note-bg: #ddf4ff; --note-border: #54aeff; --warn-bg: #fff8c5; --warn-border: #d4a72c;
}
html[data-theme="dark"] {  /* 與主程式相同的 GitHub Dark 配色 */
  --bg: #24292e; --fg: #e1e4e8; --muted: #959da5; --nav-bg: #1f2428; --border: #1b1f23;
  --accent: #79b8ff; --code-bg: #2f363d; --mark: #5b5432;
  --note-bg: #234162; --note-border: #79b8ff; --warn-bg: #5b5432; --warn-border: #ffea7f;
}
* { box-sizing: border-box; }
html { scroll-padding-top: 16px; }
body {
  margin: 0; display: flex; background: var(--bg); color: var(--fg);
  font: 15px/1.7 "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI", sans-serif;
}
#toc {
  position: sticky; top: 0; height: 100vh; overflow-y: auto; flex: 0 0 240px;
  padding: 16px 12px; background: var(--nav-bg); border-right: 1px solid var(--border);
}
#toc .brand { font-weight: bold; margin-bottom: 10px; }
#toc .group { margin: 14px 0 4px; font-size: 12px; color: var(--muted); }
#toc a { display: block; padding: 3px 8px; border-radius: 6px; color: var(--fg); text-decoration: none; }
#toc a:hover { background: var(--code-bg); }
#toc a.active { background: var(--accent); color: var(--bg); }
#toc a.hidden { display: none; }
#search {
  width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--fg);
}
#no-result { color: var(--muted); }
main { flex: 1; max-width: 980px; padding: 8px 40px 120px; }
section { padding-top: 8px; border-bottom: 1px solid var(--border); }
section.hidden { display: none; }
h2 { margin-top: 24px; }
a { color: var(--accent); }
kbd, code { background: var(--code-bg); border-radius: 4px; padding: 1px 5px; font-family: Consolas, monospace; }
kbd { border: 1px solid var(--border); }
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid var(--border); padding: 4px 10px; text-align: left; vertical-align: top; }
img { max-width: 100%; border: 1px solid var(--border); border-radius: 6px; }
figure { margin: 12px 0; }
figcaption { color: var(--muted); font-size: 13px; }
.note, .warn { padding: 8px 12px; border-left: 4px solid; border-radius: 4px; margin: 10px 0; }
.note { background: var(--note-bg); border-color: var(--note-border); }
.warn { background: var(--warn-bg); border-color: var(--warn-border); }
mark { background: var(--mark); color: inherit; }
```

`help.js`：

```js
// 使用說明網頁：主題、章節跳轉、搜尋、目錄同步。說明程式透過 setTheme()／helpShow() 控制。
(function () {
  "use strict";
  const root = document.documentElement;

  function setTheme(theme) {
    root.dataset.theme = theme === "dark" ? "dark" : "light";
  }

  function helpShow(topic, theme) {
    setTheme(theme);
    const el = topic ? document.getElementById(topic) : null;
    history.replaceState(null, "", el ? "#" + topic : location.pathname + location.search);
    if (el) el.scrollIntoView(); else window.scrollTo(0, 0);
  }

  window.setTheme = setTheme;
  window.helpShow = helpShow;

  // 在 <head> 就套主題，開啟時不會先閃一下亮色
  const q = new URLSearchParams(location.search).get("theme");
  setTheme(q || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

  function clearMarks(main) {
    main.querySelectorAll("mark").forEach(function (m) {
      m.replaceWith(document.createTextNode(m.textContent));
    });
    main.normalize();
  }

  function markText(section, word) {
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    const hits = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeValue.toLowerCase().includes(word)) hits.push(n);
    }
    hits.forEach(function (node) {
      const text = node.nodeValue, lower = text.toLowerCase(), frag = document.createDocumentFragment();
      let i = 0, j;
      while ((j = lower.indexOf(word, i)) !== -1) {
        frag.append(text.slice(i, j));
        const m = document.createElement("mark");
        m.textContent = text.slice(j, j + word.length);
        frag.append(m);
        i = j + word.length;
      }
      frag.append(text.slice(i));
      node.replaceWith(frag);
    });
  }

  function filter(main, links, word) {
    clearMarks(main);
    let shown = 0;
    main.querySelectorAll("main > section").forEach(function (s) {
      const hit = !word || s.textContent.toLowerCase().includes(word);
      s.classList.toggle("hidden", !hit);
      const link = links[s.id];
      if (link) link.classList.toggle("hidden", !hit);
      if (hit) { shown++; if (word) markText(s, word); }
    });
    document.getElementById("no-result").hidden = shown > 0;
  }

  document.addEventListener("DOMContentLoaded", function () {
    const main = document.querySelector("main");
    const links = {};
    document.querySelectorAll("#toc a[href^='#']").forEach(function (a) { links[a.hash.slice(1)] = a; });

    const search = document.getElementById("search");
    search.addEventListener("input", function () { filter(main, links, search.value.trim().toLowerCase()); });

    // 捲動時標示目前章節
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        Object.values(links).forEach(function (a) { a.classList.remove("active"); });
        const a = links[e.target.id];
        if (a) { a.classList.add("active"); a.scrollIntoView({ block: "nearest" }); }
      });
    }, { rootMargin: "0px 0px -70% 0px" });
    main.querySelectorAll("main > section").forEach(function (s) { observer.observe(s); });
  });
})();
```

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/core/test_helpdoc.py -q` → PASS

- [ ] **Step 5: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`feat: 新增使用說明網頁（目錄、搜尋、亮暗色主題）`

---

### Task 3: 說明程式 helpviewer

**Files:**
- Create: `pllangstudio/helpviewer/__init__.py`、`pllangstudio/helpviewer/window.py`、`pllangstudio/helpviewer/__main__.py`
- Modify: `tests/conftest.py`（建立 QApplication 前設定 `AA_ShareOpenGLContexts`）
- Test: `tests/ui/test_help_viewer.py`

**Interfaces:**
- Consumes: `helpdoc.Command`、`help_url`、`normalize_topic`、`parse_command`；網頁的 `window.helpShow`、`window.setTheme`
- Produces:
  - `HelpPage(QWebEnginePage)`，建構子 `HelpPage(parent=None, open_url=QDesktopServices.openUrl)`；非 `file:` 導覽改交 `open_url`、回傳 `False`
  - `HelpWindow(QWebEngineView)`，建構子 `HelpWindow(index: Path, topic: str | None, theme: str, open_url=QDesktopServices.openUrl)`；屬性 `topic`、`theme`、`ready: bool`；方法 `apply(cmd: Command) -> None`
  - `StdinBridge(QObject)`：signals `received(str)`、`closed()`；方法 `start(stream: BinaryIO) -> None`（daemon 執行緒逐行讀，UTF-8 解碼）
  - `python -m pllangstudio.helpviewer --topic <代號或 -> --theme <light|dark>`

- [ ] **Step 1: conftest 加屬性設定**（`tests/conftest.py`，在 `os.environ.setdefault(...)` 下一行）

```python
from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402

# Qt WebEngine 要求在建立 QApplication 前設定（說明程式的測試會用到）
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
```

- [ ] **Step 2: 寫失敗的測試** `tests/ui/test_help_viewer.py`

```python
import io

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from pllangstudio import resources
from pllangstudio.core.helpdoc import Command
from pllangstudio.helpviewer.window import HelpPage, HelpWindow, StdinBridge

INDEX = resources.path("help/index.html")


def js(view, qtbot, code):
    box = []
    view.page().runJavaScript(code, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=5000)
    return box[0]


@pytest.fixture
def viewer(qtbot):
    w = HelpWindow(INDEX, "glossary", "dark")
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.ready, timeout=20000)
    return w


def test_opens_topic_with_theme(viewer, qtbot):
    assert js(viewer, qtbot, "location.hash") == "#glossary"
    assert js(viewer, qtbot, "document.documentElement.dataset.theme") == "dark"


def test_show_command_switches_topic_and_theme(viewer, qtbot):
    viewer.apply(Command("show", "light", "replace"))
    assert (viewer.topic, viewer.theme) == ("replace", "light")
    qtbot.waitUntil(lambda: js(viewer, qtbot, "location.hash") == "#replace", timeout=5000)
    assert js(viewer, qtbot, "document.documentElement.dataset.theme") == "light"


def test_show_without_topic_goes_to_top(viewer, qtbot):
    viewer.apply(Command("show", "dark", None))
    qtbot.waitUntil(lambda: js(viewer, qtbot, "location.hash") == "", timeout=5000)


def test_theme_command_keeps_topic(viewer, qtbot):
    viewer.apply(Command("theme", "light"))
    qtbot.waitUntil(lambda: js(viewer, qtbot, "document.documentElement.dataset.theme") == "light",
                    timeout=5000)
    assert js(viewer, qtbot, "location.hash") == "#glossary"


def test_external_links_open_in_system_browser(qtbot):
    opened = []
    page = HelpPage(open_url=opened.append)
    ext = QUrl("https://github.com/m121752332/plsql-lang-studio")
    assert not page.acceptNavigationRequest(ext, QWebEnginePage.NavigationTypeLinkClicked, True)
    assert opened == [ext]
    assert page.acceptNavigationRequest(QUrl.fromLocalFile(str(INDEX)),
                                        QWebEnginePage.NavigationTypeLinkClicked, True)


def test_stdin_bridge_emits_lines_then_closed(qtbot):
    bridge = StdinBridge()
    lines = []
    bridge.received.connect(lines.append)
    with qtbot.waitSignal(bridge.closed, timeout=5000):
        bridge.start(io.BytesIO("show glossary dark\ntheme light\n".encode("utf-8")))
    assert lines == ["show glossary dark\n", "theme light\n"]
```

- [ ] **Step 3: 確認失敗**

Run: `uv run pytest -n0 tests/ui/test_help_viewer.py -q`
Expected: FAIL（`ModuleNotFoundError: pllangstudio.helpviewer`）

- [ ] **Step 4: 實作**

`pllangstudio/helpviewer/__init__.py`：

```python
"""說明程式：獨立行程，用 Qt WebEngine 顯示使用說明網頁（見 ADR-0019）。主程式不 import 這個套件。"""
```

`pllangstudio/helpviewer/window.py`：

```python
"""說明視窗、外部連結處理，以及從 stdin 接收主程式指令。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import BinaryIO, Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..core.helpdoc import Command, help_url, normalize_topic


class HelpPage(QWebEnginePage):
    """只在視窗內顯示本機網頁，其他連結（GitHub 等）交給系統瀏覽器。"""

    def __init__(self, parent=None, open_url: Callable[[QUrl], object] = QDesktopServices.openUrl):
        super().__init__(parent)
        self.open_url = open_url

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:
        if url.scheme() == "file":
            return True
        self.open_url(url)
        return False


class HelpWindow(QWebEngineView):
    def __init__(self, index: Path, topic: str | None, theme: str,
                 open_url: Callable[[QUrl], object] = QDesktopServices.openUrl):
        super().__init__()
        self.setPage(HelpPage(self, open_url))
        self.setWindowTitle("PLLangStudio 使用說明")
        self.resize(1100, 760)
        self.topic, self.theme = normalize_topic(topic), theme
        self.ready = False
        self.loadFinished.connect(self._on_loaded)
        self.load(QUrl(help_url(index, self.topic, theme)))

    def _on_loaded(self, ok: bool) -> None:
        self.ready = ok

    def apply(self, cmd: Command) -> None:
        self.theme = cmd.theme
        if cmd.action == "show":
            self.topic = cmd.topic
            self.page().runJavaScript(f"helpShow({json.dumps(self.topic)}, {json.dumps(self.theme)})")
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
        else:
            self.page().runJavaScript(f"setTheme({json.dumps(self.theme)})")


class StdinBridge(QObject):
    """背景執行緒逐行讀 stdin，透過 signal 交回主執行緒；讀到結尾（主程式關閉）時送出 closed。

    用 daemon 執行緒而不是 QThread：使用者先關掉視窗時，卡在讀取的執行緒會隨程式結束，不會拖住關閉。
    """
    received = Signal(str)
    closed = Signal()

    def start(self, stream: BinaryIO) -> None:
        threading.Thread(target=self._run, args=(stream,), daemon=True).start()

    def _run(self, stream: BinaryIO) -> None:
        for raw in stream:
            self.received.emit(raw.decode("utf-8", "replace"))
        self.closed.emit()
```

`pllangstudio/helpviewer/__main__.py`（用絕對 import，PyInstaller 會把它當腳本執行）：

```python
import argparse
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pllangstudio import resources
from pllangstudio.core.helpdoc import THEMES, parse_command
from pllangstudio.helpviewer.window import HelpWindow, StdinBridge


def main() -> int:
    parser = argparse.ArgumentParser(prog="PLLangHelp")
    parser.add_argument("--topic", default="-")
    parser.add_argument("--theme", choices=THEMES, default="light")
    args = parser.parse_args()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PLLangStudio.Help")
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # Qt WebEngine 要求在建立 QApplication 前設定
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PLLangHelp")
    app.setWindowIcon(QIcon(str(resources.path("app.ico"))))
    win = HelpWindow(resources.path("help/index.html"), args.topic, args.theme)
    win.show()
    bridge = StdinBridge()
    if sys.stdin is not None:  # 由主程式啟動時 stdin 是管線；直接執行時可能沒有
        def on_line(line: str) -> None:
            cmd = parse_command(line)
            if cmd is not None:
                win.apply(cmd)
        bridge.received.connect(on_line)
        bridge.closed.connect(app.quit)  # 主程式關閉，說明視窗跟著關
        bridge.start(sys.stdin.buffer)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 確認通過**

Run: `uv run pytest -n0 tests/ui/test_help_viewer.py -q` → PASS。
若 offscreen 下 WebEngine 載不起來（`ready` 一直是 False），先用 `uv run pytest -n0 … -s` 看 Chromium 錯誤，必要時在 `tests/conftest.py` 加 `os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")` 再試；不可把測試改成略過。

- [ ] **Step 6: 手動冒煙**

Run: `uv run python -m pllangstudio.helpviewer --topic glossary --theme dark`
預期：開出暗色說明視窗、停在「用語對照表」。關掉視窗程式結束。

- [ ] **Step 7: 全部測試 + commit**

Run: `uv run pytest -q` → 全過（記下總時間，與原本約 11 秒比較並回報）。
Commit 訊息：`feat: 新增說明程式（Qt WebEngine 顯示使用說明，從 stdin 接收指令）`

---

### Task 4: 主程式端 HelpLauncher

**Files:**
- Create: `pllangstudio/ui/help_launcher.py`
- Test: `tests/ui/test_help_launcher.py`

**Interfaces:**
- Consumes: `helpdoc.Command`、`format_command`、`help_url`、`normalize_topic`、`find_help_program`；`ThemeManager` 的 `changed` signal 與 `is_dark()`；`eventlog.error(category, message, exc=None)`
- Produces:
  - `default_program() -> list[str] | None`
  - `HelpLauncher(QObject)`，建構子 `HelpLauncher(theme, program: list[str] | None = <未指定>, open_url=QDesktopServices.openUrl, parent=None)`；`program` 未指定時用 `default_program()`，明確傳 `None` 表示沒有說明程式（直接用瀏覽器）
  - `HelpLauncher.show(topic: str | None = None) -> None`、`running() -> bool`、`close() -> None`
  - `install_help(widget: QWidget, topic: str | None, show: Callable[[str | None], None]) -> QShortcut`

- [ ] **Step 1: 寫失敗的測試** `tests/ui/test_help_launcher.py`

```python
import sys

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QDialog

from pllangstudio.ui import help_launcher
from pllangstudio.ui.help_launcher import HelpLauncher, install_help

# 假的說明程式：第一行記命令列參數，之後把 stdin 收到的每一行照抄
FAKE = """
import pathlib, sys
out = pathlib.Path(sys.argv[1])
out.write_text(" ".join(sys.argv[2:]) + "\\n", encoding="utf-8")
for line in sys.stdin:
    with out.open("a", encoding="utf-8") as f:
        f.write(line)
"""


class FakeTheme(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.dark = False

    def is_dark(self):
        return self.dark


@pytest.fixture
def fake(tmp_path, qtbot):
    script = tmp_path / "fake_help.py"
    script.write_text(FAKE, encoding="utf-8")
    out = tmp_path / "out.txt"
    theme = FakeTheme()
    opened = []
    launcher = HelpLauncher(theme, program=[sys.executable, str(script), str(out)], open_url=opened.append)
    launcher.out, launcher.fake_theme, launcher.opened = out, theme, opened
    yield launcher
    launcher.close()


def lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_first_show_starts_program_with_topic_and_theme(fake, qtbot):
    fake.show("glossary")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--topic glossary --theme light"], timeout=10000)
    assert fake.running()


def test_second_show_sends_command_instead_of_restarting(fake, qtbot):
    fake.show(None)
    qtbot.waitUntil(lambda: bool(lines(fake.out)), timeout=10000)
    fake.fake_theme.dark = True
    fake.show("replace")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--topic - --theme light", "show replace dark"], timeout=10000)


def test_theme_change_sent_only_while_running(fake, qtbot):
    fake.fake_theme.changed.emit()  # 還沒啟動，不應有任何動作
    assert not fake.running()
    fake.show(None)
    qtbot.waitUntil(lambda: bool(lines(fake.out)), timeout=10000)
    fake.fake_theme.dark = True
    fake.fake_theme.changed.emit()
    qtbot.waitUntil(lambda: lines(fake.out)[1:] == ["theme dark"], timeout=10000)


def test_unknown_topic_starts_at_top(fake, qtbot):
    fake.show("nope")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--topic - --theme light"], timeout=10000)


def test_without_program_opens_system_browser(qtbot):
    opened = []
    launcher = HelpLauncher(FakeTheme(), program=None, open_url=opened.append)
    launcher.show("glossary")
    assert len(opened) == 1
    url = opened[0].toString()
    assert url.startswith("file:///") and url.endswith("index.html?theme=light#glossary")


def test_start_failure_falls_back_to_browser(qtbot, tmp_path, events_db):
    opened = []
    launcher = HelpLauncher(FakeTheme(), program=[str(tmp_path / "missing.exe")], open_url=opened.append)
    launcher.show("faq")
    assert len(opened) == 1 and opened[0].toString().endswith("#faq")
    assert not launcher.running()


def test_default_program_from_source_runs_module(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert help_launcher.default_program() == [sys.executable, "-m", "pllangstudio.helpviewer"]


def test_default_program_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PLLangStudio.exe"))
    assert help_launcher.default_program() is None
    exe = tmp_path / "PLLangHelp" / "PLLangHelp.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    assert help_launcher.default_program() == [str(exe)]


def test_install_help_adds_f1_shortcut(qtbot):
    dlg = QDialog()
    qtbot.addWidget(dlg)
    shown = []
    sc = install_help(dlg, "glossary", shown.append)
    assert isinstance(sc, QShortcut) and sc.key().toString() == "F1"
    sc.activated.emit()
    assert shown == ["glossary"]
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/ui/test_help_launcher.py -q`
Expected: FAIL（`ImportError … help_launcher`）

- [ ] **Step 3: 實作** `pllangstudio/ui/help_launcher.py`

```python
"""使用說明：啟動說明程式或送指令給它（見 ADR-0019）。

說明程式是另一個行程，主程式不載入 Qt WebEngine；找不到或啟動失敗時改用系統瀏覽器開網頁。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from .. import eventlog, resources
from ..core.helpdoc import Command, find_help_program, format_command, help_url, normalize_topic

_DEFAULT = object()


def default_program() -> list[str] | None:
    if getattr(sys, "frozen", False):
        exe = find_help_program(Path(sys.executable).parent)
        return [str(exe)] if exe else None
    return [sys.executable, "-m", "pllangstudio.helpviewer"]


class HelpLauncher(QObject):
    def __init__(self, theme, program: list[str] | None = _DEFAULT,
                 open_url: Callable[[QUrl], object] = QDesktopServices.openUrl, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.program = default_program() if program is _DEFAULT else program
        self.open_url = open_url
        self.proc: QProcess | None = None
        theme.changed.connect(self._send_theme)

    def _theme(self) -> str:
        return "dark" if self.theme.is_dark() else "light"

    def running(self) -> bool:
        return self.proc is not None and self.proc.state() == QProcess.Running

    def show(self, topic: str | None = None) -> None:
        topic = normalize_topic(topic)
        if self.running():
            self._allow_foreground()
            self._send(Command("show", self._theme(), topic))
            return
        if not self.program:
            self._open_in_browser(topic)
            return
        proc = QProcess(self)
        proc.start(self.program[0], self.program[1:] + ["--topic", topic or "-", "--theme", self._theme()])
        if not proc.waitForStarted(5000):
            eventlog.error("使用說明", f"無法啟動說明程式：{proc.errorString()}，改用瀏覽器開啟")
            proc.deleteLater()
            self._open_in_browser(topic)
            return
        self.proc = proc
        self._allow_foreground()

    def close(self) -> None:
        """關閉 stdin，說明程式讀到結尾就會自己結束；等不到才強制結束。"""
        if not self.running():
            return
        self.proc.closeWriteChannel()
        if not self.proc.waitForFinished(3000):
            self.proc.kill()
            self.proc.waitForFinished(1000)

    def _send_theme(self) -> None:
        if self.running():
            self._send(Command("theme", self._theme()))

    def _send(self, cmd: Command) -> None:
        self.proc.write((format_command(cmd) + "\n").encode("utf-8"))

    def _allow_foreground(self) -> None:
        # Windows 不讓背景行程自己搶到前景，要由目前在前景的主程式授權
        if sys.platform == "win32" and self.running():
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(self.proc.processId())

    def _open_in_browser(self, topic: str | None) -> None:
        self.open_url(QUrl(help_url(resources.path("help/index.html"), topic, self._theme())))


def install_help(widget: QWidget, topic: str | None, show: Callable[[str | None], None]) -> QShortcut:
    """在視窗或對話框上按 F1 開對應章節的說明。"""
    sc = QShortcut(QKeySequence("F1"), widget)
    sc.activated.connect(lambda: show(topic))
    return sc
```

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/ui/test_help_launcher.py -q` → PASS

- [ ] **Step 5: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`feat(ui): 新增 HelpLauncher，用獨立行程開啟使用說明`

---

### Task 5: 主視窗與各對話框接上 F1

**Files:**
- Modify: `pllangstudio/ui/main_window.py`（建構子、`show_help`、`open_settings`、`show_events`、`_apply_changes`、`find_replace`、`edit_glossary`、`closeEvent`）
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `HelpLauncher`、`install_help`
- Produces: `MainWindow(..., help_launcher=None)`；屬性 `self.help`（有 `show(topic)`、`close()`）

- [ ] **Step 1: 寫失敗的測試**（加在 `tests/ui/test_main_window.py` 尾端）

```python
from PySide6.QtGui import QShortcut

from pllangstudio.ui import main_window as mw_module


class FakeHelp:
    def __init__(self):
        self.shown, self.closed = [], False

    def show(self, topic=None):
        self.shown.append(topic)

    def close(self):
        self.closed = True


@pytest.fixture
def help_win(qtbot, env):
    root, _ = env
    fake = FakeHelp()
    w = MainWindow(root, elevate_fn=lambda s, d: False, info=lambda *a, **k: None,
                   ask=lambda *a, **k: QMessageBox.Yes, toast=lambda *a, **k: None, help_launcher=fake)
    qtbot.addWidget(w)
    w.fake_help = fake
    return w


def press_f1_in_exec(monkeypatch, cls):
    """把對話框的 exec 換成「按 F1 後取消」，用來確認對話框掛了哪個章節。"""
    def fake_exec(self):
        sc = next(s for s in self.findChildren(QShortcut) if s.key().toString() == "F1")
        sc.activated.emit()
        return 0
    monkeypatch.setattr(cls, "exec", fake_exec)


def test_f1_in_main_window_opens_help_top(help_win):
    help_win.act["help"].trigger()
    assert help_win.fake_help.shown == [None]


@pytest.mark.parametrize("cls_name, action, topic", [
    ("ReplaceDialog", "replace", "replace"),
    ("GlossaryDialog", "glossary", "glossary"),
    ("SettingsDialog", "settings", "theme-font"),
])
def test_f1_in_dialog_opens_its_topic(help_win, monkeypatch, cls_name, action, topic):
    press_f1_in_exec(monkeypatch, getattr(mw_module, cls_name))
    help_win.act[action].trigger()
    assert help_win.fake_help.shown == [topic]


def test_f1_in_preview_opens_batch(help_win, monkeypatch):
    press_f1_in_exec(monkeypatch, mw_module.PreviewDialog)
    row = help_win.model.rows[0]
    help_win._apply_changes("測試", [mw_module.batch.Change(row, "舊", "新")])
    assert help_win.fake_help.shown == ["batch"]


def test_f1_in_event_viewer_opens_event_log(help_win, events_db):
    help_win.show_events()
    sc = next(s for s in help_win.event_viewer.findChildren(QShortcut) if s.key().toString() == "F1")
    sc.activated.emit()
    assert help_win.fake_help.shown == ["event-log"]


def test_closing_main_window_closes_help(help_win):
    help_win.close()
    assert help_win.fake_help.closed
```

實作前先確認 `batch.Change` 的實際欄位（`grep -n "class Change" -A8 pllangstudio/core/batch.py`），依實際建構方式調整 `test_f1_in_preview_opens_batch` 中建立 `Change` 的那一行；若主視窗 fixture 載入後 `model.rows` 為空，改用 fixture 既有的開檔方式（參考同檔中呼叫 `_apply_changes` 或 `find_replace` 的既有測試）。

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/ui/test_main_window.py -q -k "f1 or closing_main_window_closes_help"`
Expected: FAIL（`TypeError: … unexpected keyword argument 'help_launcher'`）

- [ ] **Step 3: 實作**（`pllangstudio/ui/main_window.py`）

import 區加：

```python
from .help_launcher import HelpLauncher, install_help
```

建構子參數加 `help_launcher=None`，在 `self.fonts = …` 下一行加：

```python
        self.help = help_launcher or HelpLauncher(self.theme, parent=self)
```

`show_help` 整段換成：

```python
    def show_help(self) -> None:
        self.help.show(None)
```

各對話框建立後、`exec()` 前掛 F1：

```python
            dlg = SettingsDialog(self.theme, self.fonts, self.show_events, self)
            install_help(dlg, "theme-font", self.help.show)
```

```python
            self.event_viewer = EventViewer(self.theme, self)
            install_help(self.event_viewer, "event-log", self.help.show)
```

```python
            dlg = PreviewDialog(title, changes, self)
            install_help(dlg, "batch", self.help.show)
```

```python
            dlg = ReplaceDialog(self)
            install_help(dlg, "replace", self.help.show)
```

```python
            dlg = GlossaryDialog(self.ws.load_glossary(), self)
            install_help(dlg, "glossary", self.help.show)
```

`closeEvent` 改成：

```python
    def closeEvent(self, event) -> None:
        if self.confirm_discard():
            self.help.close()
            event.accept()
        else:
            event.ignore()
```

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/ui/test_main_window.py -q` → PASS

- [ ] **Step 5: 用 MCP 實際驗證**（不按部署、不存檔、不改使用者工作區）

`launch_app(cwd="D:/GITLocal/plsql-lang-studio", script="pllangstudio/__main__.py")` → `press_key F1` → 確認說明視窗出現；開「配置…」後按 F1 → 說明切到「主題與字型」且可操作；在配置中切暗色 → 說明跟著變暗；`stop_app` 後確認說明程式也結束（`tasklist | grep -i python` 前後比較）。若啟動說明程式時跳出主控台黑窗，改用 `pythonw.exe`（與 `sys.executable` 同資料夾）並補測試。

- [ ] **Step 6: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`feat(ui): F1 改開說明程式，各對話框按 F1 開對應章節`

---

### Task 6: 介面截圖

**Files:**
- Create: `pllangstudio/resources/help/img/*.png`（刪除 `img/.gitkeep`）
- Modify: `pllangstudio/resources/help/index.html`

- [ ] **Step 1: 準備暫存工作區**

在 `temp/help-shots/workspace`（`temp/` 已存在；若被 git 追蹤則改用系統暫存資料夾）建立工作區，`settings.json` 的 `plsql_lang_dir` 指向一份複製出來的 Languages（`temp/help-shots/Languages`，從真實目錄**複製** `Chinese.lang`、`Taiwan.lang`）。用 `APPDATA` 環境變數指向 `temp/help-shots/appdata` 啟動，避免讀寫使用者真實設定：`launch_app` 不支援環境變數時，改用 `eval_python` 在程式內呼叫 `win.open_workspace(Path(...))` 切換到暫存工作區，並在結束前切回原本的工作區。

- [ ] **Step 2: 截圖**（亮色、視窗 1400×860）

| 檔名 | 畫面 | 用在章節 |
|---|---|---|
| `main-window.png` | 主視窗全貌（選一筆有差異的字串） | `screen` |
| `file-menu.png` | 檔案清單右鍵選單 | `screen` |
| `detail.png` | 詳細區（多行字串） | `edit` |
| `replace.png` | 尋找取代對話框 | `replace` |
| `preview.png` | 批次預覽 | `batch` |
| `glossary.png` | 用語對照表 | `glossary` |
| `settings.png` | 配置 | `theme-font` |
| `event-viewer.png` | 事件檢視器 | `event-log` |

截圖後用 Read 工具檢視每張圖，確認沒有使用者個人路徑以外的敏感資訊；工作區路徑出現在畫面上沒關係（是暫存路徑）。單張超過 400 KB 時用 Qt 縮到寬 1200 px 再存。

- [ ] **Step 3: 插入網頁**

在對應 `<section>` 中加入：

```html
<figure><img src="img/main-window.png" alt="主視窗"><figcaption>主視窗：左側檔案清單，右側比對表格與詳細區</figcaption></figure>
```

（每張圖一個 `<figure>`，說明文字依畫面撰寫。）

- [ ] **Step 4: 驗證**

Run: `uv run pytest -n0 tests/core/test_helpdoc.py -q` → PASS（圖片檔都存在）。
`uv run python -m pllangstudio.helpviewer --topic screen` 目視確認圖片正常顯示。

- [ ] **Step 5: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`docs: 使用說明網頁加入介面截圖`

---

### Task 7: 打包兩支程式

**Files:**
- Modify: `pllangstudio/release.py`
- Test: `tests/test_release.py`

**Interfaces:**
- Produces: `pyinstaller_args()`（主程式，多了 `--exclude-module`）、`help_pyinstaller_args() -> list[str]`、`make_zip(exe, out_dir, ver, help_dir: Path | None = None) -> Path`

- [ ] **Step 1: 寫失敗的測試**（加在 `tests/test_release.py`）

```python
def test_main_program_excludes_webengine():
    args = release.pyinstaller_args()
    excluded = {args[i + 1] for i, a in enumerate(args) if a == "--exclude-module"}
    assert {"PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"} <= excluded


def test_help_program_args():
    args = release.help_pyinstaller_args()
    assert "--onedir" in args and "--onefile" not in args
    assert args[args.index("--name") + 1] == "PLLangHelp"
    src = args[args.index("--add-data") + 1].rsplit(";", 1)[0]
    assert (Path(src) / "help" / "index.html").is_file()
    assert Path(args[-1]).is_file() and Path(args[-1]).parent.name == "helpviewer"


def test_make_zip_includes_help_folder(tmp_path):
    exe = tmp_path / "PLLangStudio.exe"
    exe.write_bytes(b"MZ")
    help_dir = tmp_path / "PLLangHelp"
    (help_dir / "_internal").mkdir(parents=True)
    (help_dir / "PLLangHelp.exe").write_bytes(b"MZ help")
    (help_dir / "_internal" / "a.dll").write_bytes(b"dll")
    out = release.make_zip(exe, tmp_path / "bin", "9.9.9", help_dir)
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    assert {"PLLangStudio.exe", "README.md", "LICENSE",
            "PLLangHelp/PLLangHelp.exe", "PLLangHelp/_internal/a.dll"} <= names
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/test_release.py -q`
Expected: FAIL（`AttributeError: … help_pyinstaller_args`）

- [ ] **Step 3: 實作**（`pllangstudio/release.py`）

`pyinstaller_args()` 在 `"--collect-all", "opencc",` 後加：

```python
        # Qt WebEngine 只給說明程式用，主程式不能帶進去（見 ADR-0019）
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.QtWebChannel",
```

新增：

```python
HELP_NAME = "PLLangHelp"


def help_pyinstaller_args() -> list[str]:
    """說明程式用資料夾形式（onedir），Chromium 很大，每次啟動都解壓太慢。"""
    res = ROOT / "pllangstudio" / "resources"
    return [
        "--noconfirm", "--onedir", "--windowed",
        "--add-data", f"{res};pllangstudio/resources",
        "--icon", str(res / "app.ico"),
        "--name", HELP_NAME,
        "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build"),
        "--distpath", str(ROOT / "dist"),
        str(ROOT / "pllangstudio" / "helpviewer" / "__main__.py"),
    ]
```

`make_zip` 改成：

```python
def make_zip(exe: Path, out_dir: Path, ver: str, help_dir: Path | None = None) -> Path:
    """把 exe、說明程式資料夾、README.md、LICENSE 壓成發行用 zip。先寫 .tmp 再換檔，不會留下壞掉的一半。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}-v{ver}-win64.zip"
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, exe.name)
        if help_dir is not None:
            for f in sorted(help_dir.rglob("*")):
                if f.is_file():
                    z.write(f, f"{help_dir.name}/{f.relative_to(help_dir).as_posix()}")
        for name in ("README.md", "LICENSE"):
            z.write(ROOT / name, name)
    os.replace(tmp, out)
    return out
```

`build()` 改成依序建兩份：

```python
def build() -> int:
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args())
    PyInstaller.__main__.run(help_pyinstaller_args())
    print(f"完成：{ROOT / 'dist' / (NAME + '.exe')}、{ROOT / 'dist' / HELP_NAME}")
    return 0
```

`package()` 的 `make_zip(...)` 加第四個參數 `ROOT / "dist" / HELP_NAME`。

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/test_release.py -q` → PASS

- [ ] **Step 5: 實際打包驗證**

Run: `uv run package`（時間較長，用背景執行）
檢查：
- `ls -la dist/PLLangStudio.exe`、`du -sh dist/PLLangHelp`、`ls -la bin/*.zip` 記下大小。
- 執行 `dist/PLLangStudio.exe`（會開使用者真實工作區：**只按 F1，不做其他操作**），確認說明視窗出現；關掉主程式後說明程式也結束。
- 若打包後說明程式收不到指令（`--windowed` 下 `sys.stdin` 為 `None`），在 `helpviewer/__main__.py` 改從 `os.fdopen(0, "rb")` 讀取並補說明註解，重新打包驗證。

- [ ] **Step 6: 全部測試 + commit**

Run: `uv run pytest -q` → 全過。
Commit 訊息：`chore: 打包時另建說明程式 PLLangHelp，發行 zip 一併帶入`

---

### Task 8: 文件

**Files:**
- Create: `docs/adr/0019-help-webpage.md`
- Modify: `docs/adr/0016-build-and-package-commands.md`、`CONTEXT.md`、`README.md`、`AGENTS.md`（目錄樹與 ADR 範圍 0001～0019）

- [ ] **Step 1: ADR-0019**（格式比照 `docs/adr/0018-event-log-maintenance.md`，`status: accepted`）

內容：背景（F1 只有 QMessageBox）、決策（網頁＋Qt WebEngine；不用 CEF 的原因：cefpython3 不支援 Python 3.14；拆成獨立說明程式的原因：`Qt6WebEngineCore.dll` 194 MB 由載入它的行程使用，主程式維持 onefile 約 53 MB；stdin 指令格式；找不到時退回系統瀏覽器）、後果（Task 7 量到的實際大小、兩份網頁內容與 README 需同步維護、主程式不可 import WebEngine）。

- [ ] **Step 2: ADR-0016** 補一段：發行 zip 另含 `PLLangHelp\` 資料夾，見 ADR-0019。

- [ ] **Step 3: CONTEXT.md** 依既有格式補兩個詞：
  - **使用說明**：按 F1 開啟的網頁版說明，內容與 README 對應。
  - **說明程式**：顯示使用說明的獨立程式 `PLLangHelp`，放在主程式旁的 `PLLangHelp\` 資料夾。

- [ ] **Step 4: README.md**：開頭目錄前加一句「程式內按 F1 可以看圖文版的使用說明」；§15「檔案放在哪裡」補 `PLLangHelp\` 資料夾用途（不能刪，刪了 F1 會改用瀏覽器開）；§17 技術架構補 `helpviewer/`。

- [ ] **Step 5: 驗證與 commit**

確認改過的檔案仍是合法 UTF-8：`uv run python -c "import pathlib,sys;[pathlib.Path(p).read_text(encoding='utf-8') for p in sys.argv[1:]]" README.md CONTEXT.md AGENTS.md docs/adr/0016-build-and-package-commands.md docs/adr/0019-help-webpage.md`
Run: `uv run pytest -q` → 全過。
Commit 訊息：`docs: 新增 ADR-0019 使用說明網頁，更新 README、CONTEXT.md、ADR-0016`
