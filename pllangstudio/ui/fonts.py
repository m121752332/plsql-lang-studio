"""介面字型與字體大小：套用到整個程式，設定存在 app.json，下次啟動沿用。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .. import appconfig

MIN_SIZE, MAX_SIZE = 7, 32
_FALLBACK_SIZE = 9
_system_font: QFont | None = None  # 程式第一次建立管理員時的系統字型，「還原預設」用


class FontManager(QObject):
    changed = Signal()

    def __init__(self, app: QApplication, parent=None):
        super().__init__(parent)
        global _system_font
        if _system_font is None:
            _system_font = QFont(app.font())
        self.app = app
        self.default_family = _system_font.family()
        self.default_size = _system_font.pointSize() if _system_font.pointSize() > 0 else _FALLBACK_SIZE
        self._family = appconfig.font_family()
        self._size = self._clamp(appconfig.font_size()) if appconfig.font_size() else 0
        self._apply()

    @staticmethod
    def _clamp(size: int) -> int:
        return max(MIN_SIZE, min(MAX_SIZE, size))

    def family(self) -> str:
        return self._family or self.default_family

    def size(self) -> int:
        return self._size or self.default_size

    def set_font(self, family: str, size: int) -> None:
        self._family, self._size = family, self._clamp(size)
        appconfig.remember_font(self._family, self._size)
        self._apply()

    def step(self, delta: int) -> None:
        self.set_font(self._family, self.size() + delta)

    def reset(self) -> None:
        self._family, self._size = "", 0
        appconfig.remember_font("", 0)
        self._apply()

    def _apply(self) -> None:
        font = QFont(_system_font)
        if self._family:
            font.setFamily(self._family)
        font.setPointSize(self.size())
        self.app.setFont(font)
        self.changed.emit()
