"""測試共用：PL/SQL Developer 的真實語言檔（見 ADR-0012）。"""

from pathlib import Path

import pytest

LANG_DIR = Path(r"C:\Program Files\PLSQL Developer 17\Languages")
LANG_FILES = sorted(LANG_DIR.glob("*.lang"))

needs_lang_dir = pytest.mark.skipif(not LANG_FILES, reason="找不到 PL/SQL Developer 的 Languages 目錄")
