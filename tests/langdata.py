"""測試共用：PL/SQL Developer 的真實語言檔（見 ADR-0012）。"""

from pathlib import Path

import pytest

from pllangstudio.core.workspace import bundled_lang

LANG_DIR = Path(r"C:\Program Files\PLSQL Developer 17\Languages")
LANG_FILES = sorted(LANG_DIR.glob("*.lang"))

needs_lang_dir = pytest.mark.skipif(not LANG_FILES, reason="找不到 PL/SQL Developer 的 Languages 目錄")


def lang_path(name: str) -> Path:
    """真實語言檔；PL/SQL Developer 沒附的（例如 Taiwan.lang）改用程式內附的版本（ADR-0022）。"""
    p = LANG_DIR / name
    return p if p.exists() else bundled_lang(name) or p
