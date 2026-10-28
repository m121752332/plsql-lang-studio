"""配置視窗：左側頁籤清單、右側內容。「外觀」管主題與字型，「紀錄事件」管保留天數（見 ADR-0017）。

按「確定」或「套用」才生效；「還原預設字型」立即生效。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFontComboBox, QFormLayout, QHBoxLayout,
                               QLabel, QListWidget, QPushButton, QRadioButton, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import appconfig, eventlog
from .fonts import MAX_SIZE, MIN_SIZE, FontManager
from .theme import MODE_LABEL, ThemeManager

SAMPLE = "The quick brown fox 永和九年，歲在癸丑 0123456789"


class AppearancePage(QWidget):
    def __init__(self, theme: ThemeManager, fonts: FontManager, parent=None):
        super().__init__(parent)
        self.theme, self.fonts = theme, fonts
        self.theme_buttons: dict[str, QRadioButton] = {}
        group = QButtonGroup(self)
        modes = QHBoxLayout()
        for mode, label in MODE_LABEL.items():
            b = QRadioButton(label)
            b.setChecked(theme.mode == mode)
            group.addButton(b)
            modes.addWidget(b)
            self.theme_buttons[mode] = b
        modes.addStretch()

        self.family = QFontComboBox()
        self.size = QSpinBox()
        self.size.setRange(MIN_SIZE, MAX_SIZE)
        self.size.setSuffix(" pt")
        self.sample = QLabel(SAMPLE)
        self.sample.setWordWrap(True)
        self._load_font()
        self.family.currentFontChanged.connect(self._preview)
        self.size.valueChanged.connect(self._preview)
        self.reset_button = QPushButton("還原預設字型")
        self.reset_button.clicked.connect(self._reset_font)

        form = QFormLayout(self)
        form.addRow("主題", modes)
        form.addRow("字型", self.family)
        form.addRow("大小", self.size)
        form.addRow("預覽", self.sample)
        form.addRow("", self.reset_button)

    def _load_font(self) -> None:
        self.family.setCurrentFont(QFont(self.fonts.family()))
        self.size.setValue(self.fonts.size())
        # 記下畫面一開始的值：offscreen 測試或缺字型時，下拉選單顯示的字型可能跟管理員回報的不同
        self._initial_font = (self.family.currentFont().family(), self.size.value())
        self._preview()

    def _preview(self, *_args) -> None:
        font = QFont(self.family.currentFont())
        font.setPointSize(self.size.value())
        self.sample.setFont(font)

    def _reset_font(self) -> None:
        self.fonts.reset()
        self._load_font()

    def apply(self) -> None:
        mode = next(m for m, b in self.theme_buttons.items() if b.isChecked())
        if mode != self.theme.mode:
            self.theme.set_mode(mode)
        choice = (self.family.currentFont().family(), self.size.value())
        if choice != self._initial_font:  # 沒改就維持「系統預設」，不寫死目前的字型
            self._initial_font = choice
            self.fonts.set_font(*choice)


class LogPage(QWidget):
    viewerRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        retention = appconfig.log_retention()
        self.days: dict[str, QSpinBox] = {}
        form = QFormLayout()
        for group, label in (("info", "資訊"), ("warning", "警告"), ("error", "錯誤（含嚴重錯誤）")):
            box = QSpinBox()
            box.setRange(*appconfig.LOG_DAYS_RANGE)
            box.setSuffix(" 天")
            box.setValue(retention[group])
            form.addRow(f"{label}保留", box)
            self.days[group] = box
        self.stats = QLabel()
        self.viewer_button = QPushButton("開啟事件檢視器")
        self.viewer_button.clicked.connect(self.viewerRequested)
        self.purge_button = QPushButton("立即清除過期紀錄")
        self.purge_button.clicked.connect(self.purge_now)
        buttons = QHBoxLayout()
        buttons.addWidget(self.viewer_button)
        buttons.addWidget(self.purge_button)
        buttons.addStretch()
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.stats)
        lay.addLayout(buttons)
        lay.addStretch()
        self.refresh_stats()

    def retention(self) -> dict[str, int]:
        return {g: b.value() for g, b in self.days.items()}

    def refresh_stats(self, removed: int | None = None) -> None:
        count, size = eventlog.stats()
        text = f"目前共 {count:,} 筆，佔 {size / 1024 / 1024:.1f} MB"
        self.stats.setText(text if removed is None else f"已清除 {removed:,} 筆。{text}")

    def apply(self) -> None:
        new = self.retention()
        if new != appconfig.log_retention():
            appconfig.remember_log_retention(new)
            eventlog.info("配置", "保留天數改為 " + "、".join(f"{eventlog.GROUP_LABEL[g]} {d} 天" for g, d in new.items()))
        self.refresh_stats(eventlog.purge(new))

    def purge_now(self) -> None:
        """依已儲存的天數清除；畫面上還沒套用的數字不算。"""
        self.refresh_stats(eventlog.purge(appconfig.log_retention()))


class SettingsDialog(QDialog):
    def __init__(self, theme: ThemeManager, fonts: FontManager, open_viewer: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置")
        self.resize(560, 360)
        self.open_viewer = open_viewer
        self.appearance = AppearancePage(theme, fonts)
        self.log_page = LogPage()
        self.log_page.viewerRequested.connect(self._open_viewer)
        self.pages_list = QListWidget()
        self.pages_list.setFixedWidth(120)
        self.stack = QStackedWidget()
        for label, page in (("外觀", self.appearance), ("紀錄事件", self.log_page)):
            self.pages_list.addItem(label)
            self.stack.addWidget(page)
        self.pages_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.pages_list.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        body = QHBoxLayout()
        body.addWidget(self.pages_list)
        body.addWidget(self.stack, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(body)
        lay.addWidget(buttons)

    def apply(self) -> None:
        self.appearance.apply()
        self.log_page.apply()

    def accept(self) -> None:
        self.apply()
        super().accept()

    def _open_viewer(self) -> None:
        """先套用並關閉配置視窗：強制回應的對話框開著時，事件檢視器無法操作。"""
        self.accept()
        self.open_viewer()
