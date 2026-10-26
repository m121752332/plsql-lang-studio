"""程式本身的設定（上次用的工作區、主題），存在 %APPDATA%\\PLLangStudio\\app.json。"""

import json
import os
import sys
from pathlib import Path

from .core import langfile

THEME_MODES = ("light", "dark", "system")


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _config_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "PLLangStudio" / "app.json"


def quarantine(p: Path) -> None:
    """設定檔壞了：改名成 .corrupt 保留，讓程式用預設值繼續。"""
    try:
        os.replace(p, p.with_name(p.name + ".corrupt"))
    except OSError:
        pass


def _load() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    quarantine(p)
    return {}


def _update(**values) -> None:
    """只更新指定的欄位，其他設定保留。"""
    p = _config_path()
    data = _load()
    data.update(values)
    p.parent.mkdir(parents=True, exist_ok=True)
    langfile.atomic_write(p, json.dumps(data, ensure_ascii=False).encode("utf-8"))


def last_workspace() -> Path | None:
    value = _load().get("workspace")
    return Path(value) if isinstance(value, str) and value else None


def remember_workspace(root: Path) -> None:
    _update(workspace=str(root))


def theme_mode() -> str:
    mode = _load().get("theme")
    return mode if mode in THEME_MODES else "system"


def remember_theme(mode: str) -> None:
    _update(theme=mode)
