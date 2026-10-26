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
