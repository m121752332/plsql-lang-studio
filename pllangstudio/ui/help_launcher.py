"""使用說明：啟動說明程式或送指令給它（見 ADR-0019）。

說明程式是另一個行程，主程式不載入 Qt WebEngine；找不到或啟動失敗時改用系統瀏覽器開網頁。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from .. import eventlog, resources
from ..core.helpdoc import Command, find_help_program, format_command, help_url, normalize_topic

_DEFAULT = object()


def default_program() -> list[str] | None:
    if getattr(sys, "frozen", False):
        exe = find_help_program(Path(sys.executable).parent)
        return [str(exe)] if exe else None
    return [sys.executable, "-m", "pllangstudio.helpviewer"]


class HelpLauncher(QObject):
    def __init__(self, theme, program: list[str] | None = _DEFAULT,
                 open_url: Callable[[QUrl], object] = QDesktopServices.openUrl, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.program = default_program() if program is _DEFAULT else program  # None：沒有說明程式
        self.open_url = open_url
        self.proc: QProcess | None = None
        theme.changed.connect(self._send_theme)

    def _theme(self) -> str:
        return "dark" if self.theme.is_dark() else "light"

    def running(self) -> bool:
        return self.proc is not None and self.proc.state() == QProcess.Running

    def show(self, topic: str | None = None) -> None:
        topic = normalize_topic(topic)
        if self.running():
            self._allow_foreground()
            self._send(Command("show", self._theme(), topic))
            return
        if not self.program:
            self._open_in_browser(topic)
            return
        proc = QProcess(self)
        proc.start(self.program[0],
                   self.program[1:] + ["--listen", "--topic", topic or "-", "--theme", self._theme()])
        if not proc.waitForStarted(5000):
            eventlog.error("使用說明", f"無法啟動說明程式：{proc.errorString()}，改用瀏覽器開啟")
            proc.deleteLater()
            self._open_in_browser(topic)
            return
        self.proc = proc
        self._allow_foreground()

    def close(self) -> None:
        """關閉 stdin，說明程式讀到結尾就會自己結束；等不到才強制結束。"""
        if not self.running():
            return
        self.proc.closeWriteChannel()
        if not self.proc.waitForFinished(3000):
            self.proc.kill()
            self.proc.waitForFinished(1000)

    def _send_theme(self) -> None:
        if self.running():
            self._send(Command("theme", self._theme()))

    def _send(self, cmd: Command) -> None:
        self.proc.write((format_command(cmd) + "\n").encode("utf-8"))

    def _allow_foreground(self) -> None:
        # Windows 不讓背景行程自己搶到前景，要由目前在前景的主程式授權
        if sys.platform == "win32" and self.running():
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(self.proc.processId())

    def _open_in_browser(self, topic: str | None) -> None:
        self.open_url(QUrl(help_url(resources.path("help/index.html"), topic, self._theme())))


def install_help(widget: QWidget, topic: str | None, show: Callable[[str | None], None]) -> QShortcut:
    """在視窗或對話框上按 F1 開對應章節的說明。"""
    sc = QShortcut(QKeySequence("F1"), widget)
    sc.activated.connect(lambda: show(topic))
    return sc
