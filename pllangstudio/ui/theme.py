"""亮色／暗色／跟隨系統主題。

表格的狀態底色與差異標色必須跟著主題換：亮色的淺色底配上暗色主題的白字會看不見（見 ADR-0005）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .. import appconfig
from ..core.compare import Status

MODE_LABEL = {"light": "亮色", "dark": "暗色", "system": "跟隨系統"}


@dataclass(frozen=True)
class Colors:
    status: dict  # Status → 底色
    group: tuple[str, str]  # 同一筆的列交替底色
    master_fg: str  # 主語系欄的文字（唯讀，稍淡）
    comment_fg: str  # 說明註解
    diff_removed: str  # 主語系有、副語系沒有的字
    diff_added: str  # 副語系新增或改過的字
    simplified_bg: str  # 殘留簡體字
    simplified_fg: str
    toast_bg: str  # 提示訊息卡片
    toast_border: str
    toast_fg: str
    toast_accent: dict  # 提示訊息種類 → 左側色條與圖示的顏色
    event_level: dict  # 事件檢視器：等級群組 → 文字顏色（資訊用預設色）
    palette: dict  # QPalette.ColorRole → 顏色


LIGHT = Colors(
    status={Status.ERROR: "#f8d0d0", Status.MODIFIED: "#d6e6ff", Status.SIMPLIFIED: "#ffd6d6",
            Status.UNTRANSLATED: "#ffe2bf", Status.ONE_SIDED: "#e4e4e4", Status.DIFFERENT: "#fff6c8"},
    group=("#ffffff", "#f5f7fa"), master_fg="#555555", comment_fg="#666666",
    diff_removed="#ffd7d7", diff_added="#d7f5d7", simplified_bg="#ff8080", simplified_fg="#ffffff",
    toast_bg="#ffffff", toast_border="#d0d0d0", toast_fg="#1a1a1a",
    toast_accent={"success": "#2e8b3e", "info": "#1a5fb4", "warning": "#c77c02"},
    event_level={"warning": "#b26a00", "error": "#c0392b"},
    palette={QPalette.Window: "#f3f3f3", QPalette.WindowText: "#1a1a1a", QPalette.Base: "#ffffff",
             QPalette.AlternateBase: "#f5f7fa", QPalette.Text: "#1a1a1a", QPalette.Button: "#ececec",
             QPalette.ButtonText: "#1a1a1a", QPalette.ToolTipBase: "#ffffdc", QPalette.ToolTipText: "#1a1a1a",
             QPalette.Highlight: "#3874d8", QPalette.HighlightedText: "#ffffff",
             QPalette.PlaceholderText: "#888888", QPalette.Link: "#1a5fb4"},
)

DARK = Colors(
    status={Status.ERROR: "#6a2c2c", Status.MODIFIED: "#24466b", Status.SIMPLIFIED: "#73303a",
            Status.UNTRANSLATED: "#664a1f", Status.ONE_SIDED: "#3c3d40", Status.DIFFERENT: "#4d4720"},
    group=("#1e1f22", "#26282c"), master_fg="#a8a8a8", comment_fg="#9a9a9a",
    diff_removed="#6e3434", diff_added="#2f5c37", simplified_bg="#d9534f", simplified_fg="#ffffff",
    toast_bg="#2d2f33", toast_border="#45484e", toast_fg="#e6e6e6",
    toast_accent={"success": "#5cc26b", "info": "#6ea8ff", "warning": "#f0b429"},
    event_level={"warning": "#f0b429", "error": "#ff6b6b"},
    palette={QPalette.Window: "#202124", QPalette.WindowText: "#e6e6e6", QPalette.Base: "#1b1c1f",
             QPalette.AlternateBase: "#26282c", QPalette.Text: "#e6e6e6", QPalette.Button: "#2d2f33",
             QPalette.ButtonText: "#e6e6e6", QPalette.ToolTipBase: "#2d2f33", QPalette.ToolTipText: "#e6e6e6",
             QPalette.Highlight: "#3874d8", QPalette.HighlightedText: "#ffffff",
             QPalette.PlaceholderText: "#8a8a8a", QPalette.Link: "#6ea8ff"},
)

_DISABLED_TEXT = {False: "#a0a0a0", True: "#6f7175"}
_current: Colors = LIGHT


def colors() -> Colors:
    """目前使用中的顏色，表格與詳細區每次繪製時讀取。"""
    return _current


def _qt_system_dark() -> bool:
    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, app: QApplication, system_dark: Callable[[], bool] | None = None, parent=None):
        super().__init__(parent)
        self.app = app
        self.system_dark = system_dark or _qt_system_dark
        self.mode = appconfig.theme_mode()
        # 直接連到方法：ThemeManager 被刪除時 Qt 會自動斷開，不會呼叫到已刪除的物件
        app.styleHints().colorSchemeChanged.connect(self.on_system_changed)
        self._apply()

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_LABEL:
            raise ValueError(f"未知的主題：{mode}")
        self.mode = mode
        appconfig.remember_theme(mode)
        self._apply()

    def on_system_changed(self, *_scheme) -> None:
        if self.mode == "system":
            self._apply()

    def is_dark(self) -> bool:
        return self.mode == "dark" or (self.mode == "system" and self.system_dark())

    def _apply(self) -> None:
        global _current
        hints = self.app.styleHints()
        # 讓 Windows 的視窗標題列也跟著換深淺色；「跟隨系統」時交回給系統決定
        if self.mode == "system":
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(Qt.ColorScheme.Dark if self.mode == "dark" else Qt.ColorScheme.Light)
        dark = self.is_dark()
        _current = DARK if dark else LIGHT
        self.app.setStyle("Fusion")
        p = QPalette()
        for role, color in _current.palette.items():
            p.setColor(role, QColor(color))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            p.setColor(QPalette.Disabled, role, QColor(_DISABLED_TEXT[dark]))
        self.app.setPalette(p)
        self.changed.emit()
