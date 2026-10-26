"""程式本身的設定（記住上次用的工作區），存在 %APPDATA%\\PLLangStudio\\app.json。"""

import json
import os
import sys
from pathlib import Path

from .core import langfile


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


def last_workspace() -> Path | None:
    p = _config_path()
    if p.exists():
        try:
            value = json.loads(p.read_text(encoding="utf-8")).get("workspace")
            return Path(value) if value else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            quarantine(p)
    return None


def remember_workspace(root: Path) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    langfile.atomic_write(p, json.dumps({"workspace": str(root)}, ensure_ascii=False).encode("utf-8"))
