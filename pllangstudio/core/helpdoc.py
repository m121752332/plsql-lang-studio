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
