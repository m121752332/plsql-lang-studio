import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 畫面測試時不顯示視窗

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402

# Qt WebEngine 要求在建立 QApplication 前設定（說明程式的測試會用到）
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

from langdata import LANG_DIR  # noqa: E402


@pytest.fixture
def lang_copy(tmp_path):
    """把真實語言檔複製到暫存資料夾，測試只能改副本。"""
    def _copy(name: str):
        dst = tmp_path / name
        dst.write_bytes((LANG_DIR / name).read_bytes())
        return dst
    return _copy


@pytest.fixture
def events_db(tmp_path):
    """在暫存資料夾啟用事件紀錄，測試結束時關閉，不碰真實的 %APPDATA%。"""
    from pllangstudio import eventlog
    db = tmp_path / "events.db"
    eventlog.setup(db)
    yield db
    eventlog.shutdown()
