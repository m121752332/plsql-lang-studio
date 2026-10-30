"""說明視窗、外部連結處理，以及從 stdin 接收主程式指令。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import BinaryIO, Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..core.helpdoc import Command, help_url, normalize_topic


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
                 open_url: Callable[[QUrl], object] = QDesktopServices.openUrl):
        super().__init__()
        self.setPage(HelpPage(self, open_url))
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
    """
    received = Signal(str)
    closed = Signal()

    def start(self, stream: BinaryIO) -> None:
        threading.Thread(target=self._run, args=(stream,), daemon=True).start()

    def _run(self, stream: BinaryIO) -> None:
        for raw in stream:
            self.received.emit(raw.decode("utf-8", "replace"))
        self.closed.emit()
