"""提示訊息（toast）：在視窗右下角滑入的圓角卡片，幾秒後自動消失。

成功與一般資訊用提示訊息，不必按「確定」；錯誤與詢問仍用對話框，避免使用者沒看到（見 ADR-0015）。
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QStatusBar,
                               QToolButton, QVBoxLayout, QWidget)

from .theme import colors

KINDS = {"success": "✓", "info": "ℹ", "warning": "⚠"}  # 種類 → 圖示
DURATION = {"success": 4000, "info": 4000, "warning": 6000}  # 毫秒


class Toast(QFrame):
    """單一則提示訊息；滑鼠停在上面時暫停倒數。"""

    dismissed = Signal(object)

    def __init__(self, kind: str, title: str, text: str, duration: int, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_StyledBackground)
        c = colors()
        accent = c.toast_accent[kind]
        self.setStyleSheet(f"#toast {{ background: {c.toast_bg}; border: 1px solid {c.toast_border}; border-radius: 8px; }}"
                           f" #accent {{ background: {accent}; border-radius: 2px; }}"
                           f" QLabel, QToolButton {{ color: {c.toast_fg}; background: transparent; border: none; }}")
        bar = QFrame()
        bar.setObjectName("accent")
        bar.setFixedWidth(4)
        icon = QLabel(KINDS[kind])
        icon.setStyleSheet(f"color: {accent}; font-size: 16pt;")
        icon.setAlignment(Qt.AlignTop)
        self.title_label = QLabel(title)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setWordWrap(True)
        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setVisible(bool(text))
        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.dismiss)

        body = QVBoxLayout()
        body.setSpacing(2)
        body.addWidget(self.title_label)
        body.addWidget(self.text_label)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 10, 8, 10)
        row.setSpacing(10)
        row.addWidget(bar)
        row.addWidget(icon)
        row.addLayout(body, 1)
        row.addWidget(self.close_button, 0, Qt.AlignTop)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.slide.setDuration(180)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self._closing = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(duration)
        self.timer.timeout.connect(self.dismiss)

    def start(self) -> None:
        self._animate_opacity(0.0, 1.0, 150)
        self.timer.start()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        self.dismissed.emit(self)
        self._animate_opacity(self._opacity.opacity(), 0.0, 200)
        self._fade.finished.connect(self.deleteLater)

    def _animate_opacity(self, start: float, end: float, ms: int) -> None:
        self._fade.stop()
        self._fade.setDuration(ms)
        self._fade.setStartValue(start)
        self._fade.setEndValue(end)
        self._fade.start()

    def enterEvent(self, event):
        self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._closing:
            self.timer.start()
        super().leaveEvent(event)


class ToastHost(QObject):
    """在父視窗右下角由下往上堆疊提示訊息，父視窗縮放時跟著移動。"""

    MAX = 3
    WIDTH = 360
    MARGIN = 16
    SPACING = 8

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.target = parent
        self.toasts: list[Toast] = []
        parent.installEventFilter(self)

    def show(self, kind: str, title: str, text: str = "", duration: int | None = None) -> Toast:
        t = Toast(kind, title, text, duration or DURATION[kind], self.target)
        t.dismissed.connect(self._remove)
        self.toasts.append(t)
        while len(self.toasts) > self.MAX:
            self.toasts[0].dismiss()
        t.show()
        t.raise_()
        self._layout()
        end = t.pos()
        t.slide.setStartValue(end + QPoint(0, 24))
        t.slide.setEndValue(end)
        t.slide.start()
        t.start()
        return t

    def _remove(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
            self._layout()

    def _layout(self) -> None:
        p = self.target
        width = max(1, min(self.WIDTH, p.width() - 2 * self.MARGIN))
        bottom = p.height() - self.MARGIN
        bar = p.findChild(QStatusBar) if isinstance(p, QMainWindow) else None
        if bar is not None and bar.isVisible():  # 不要蓋住狀態列
            bottom -= bar.height()
        for t in reversed(self.toasts):
            t.slide.stop()
            h = t.heightForWidth(width) if t.hasHeightForWidth() else t.sizeHint().height()
            t.setGeometry(p.width() - self.MARGIN - width, bottom - h, width, h)
            bottom -= h + self.SPACING

    def eventFilter(self, obj, event):
        if obj is self.target and event.type() == QEvent.Resize:
            self._layout()
        return False
