"""程式本身的設定（上次用的工作區、主題、字型、介面語言、事件紀錄保留天數），存在 %APPDATA%\\PLLangStudio\\app.json。"""

import json
import os
import sys
from pathlib import Path

from .core import langfile

THEME_MODES = ("light", "dark", "system")
LANGUAGES = ("zh_TW", "zh_CN", "en", "ja")  # 介面語言，第一個是預設（也是程式原文）
LOG_RETENTION_DEFAULT = {"info": 90, "warning": 90, "error": 30}  # 事件紀錄保留天數：資訊／警告／錯誤
LOG_DAYS_RANGE = (1, 3650)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def data_dir() -> Path:
    """程式自己的資料（app.json、events.db）放在 %APPDATA%\\PLLangStudio。"""
    return Path(os.environ.get("APPDATA", Path.home())) / "PLLangStudio"


def _config_path() -> Path:
    return data_dir() / "app.json"


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


def font_family() -> str:
    """使用者選的介面字型；空字串表示用系統預設。"""
    value = _load().get("font_family")
    return value if isinstance(value, str) else ""


def font_size() -> int:
    """使用者選的字體大小（pt）；0 表示用系統預設。"""
    value = _load().get("font_size")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def remember_font(family: str, size: int) -> None:
    _update(font_family=family, font_size=size)


def log_retention() -> dict[str, int]:
    """事件紀錄各等級群組的保留天數；沒設定或不合法時用預設值。"""
    data = _load()
    result = {}
    for group, default in LOG_RETENTION_DEFAULT.items():
        value = data.get(f"log_days_{group}")
        ok = isinstance(value, int) and not isinstance(value, bool) and LOG_DAYS_RANGE[0] <= value <= LOG_DAYS_RANGE[1]
        result[group] = value if ok else default
    return result


def remember_log_retention(retention: dict[str, int]) -> None:
    _update(**{f"log_days_{group}": int(retention[group]) for group in LOG_RETENTION_DEFAULT})


def language() -> str:
    """介面語言（見 ADR-0020）；沒設定或不認得時用繁體中文。"""
    value = _load().get("language")
    return value if value in LANGUAGES else LANGUAGES[0]


def remember_language(code: str) -> None:
    _update(language=code)
