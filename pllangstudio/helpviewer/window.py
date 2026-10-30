"""說明視窗、外部連結處理，以及從 stdin 接收主程式指令。"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..core.helpdoc import Command, help_url, normalize_topic


def chromium_flags(existing: str, dpr: float) -> str:
    """說明程式要加給 Chromium 的參數。

    - 縮放比例固定成 Qt 的值：Windows「協助工具 ▸ 文字大小」不是 100% 時，Chromium 會把它算進縮放比例，
      Qt 卻不會，Chromium 畫出的畫面被 Qt 用最近鄰縮小，每隔十幾列就掉一列，細的橫筆畫和框線會消失。
      文字大小改由 HelpWindow 的 zoom 補回來。
    - 關閉視窗遮蔽偵測：被主程式蓋住後帶到前面，可能一直是黑畫面或舊畫面。
    """
    ours = f"--force-device-scale-factor={dpr:g} --disable-features=CalculateNativeWinOcclusion"
    return f"{existing} {ours}".strip()


def _read_text_scale() -> int:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as key:
        return winreg.QueryValueEx(key, "TextScaleFactor")[0]


def text_scale_factor() -> float:
    """Windows「協助工具 ▸ 文字大小」，1.0 表示沒有放大；沒有這個設定（或不是 Windows）時為 1.0。"""
    try:
        return _read_text_scale() / 100
    except (OSError, ImportError):
        return 1.0


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
                 open_url: Callable[[QUrl], object] = QDesktopServices.openUrl, zoom: float = 1.0):
        super().__init__()
        self.setPage(HelpPage(self, open_url))
        self.setZoomFactor(zoom)  # 依 Windows 文字大小放大，見 chromium_flags
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
    直接用 os.read 讀檔案描述元，不經過 sys.stdin：卡在 sys.stdin 讀取的 daemon 執行緒
    會讓程式結束時出現 Fatal Python error（拿不到 BufferedReader 的鎖）。
    """
    received = Signal(str)
    closed = Signal()

    def start(self, fd: int) -> None:
        threading.Thread(target=self._run, args=(fd,), daemon=True).start()

    def _run(self, fd: int) -> None:
        pending = b""
        while chunk := os.read(fd, 4096):
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for line in lines:
                self.received.emit(line.decode("utf-8", "replace").rstrip("\r"))
        self.closed.emit()
