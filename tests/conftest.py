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
