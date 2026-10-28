"""配置視窗：左側頁籤清單、右側內容。「外觀」管主題與字型，「紀錄事件」管保留天數（見 ADR-0017）。

按「確定」或「套用」才生效；「還原預設字型」與紀錄事件頁的維護按鈕（刪除、清除、初始化）立即生效。
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFontComboBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton, QRadioButton, QSpinBox, QStackedWidget,
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
        self.ask = self._ask  # 測試時可以換掉對話框與開資料夾
        self.warn = self._warn
        self.open_folder = os.startfile
        retention = appconfig.log_retention()
        self.days: dict[str, QSpinBox] = {}
        keep = QFormLayout()
        for group, label in (("info", "資訊"), ("warning", "警告"), ("error", "錯誤（含嚴重錯誤）")):
            box = QSpinBox()
            box.setRange(*appconfig.LOG_DAYS_RANGE)
            box.setSuffix(" 天")
            box.setValue(retention[group])
            keep.addRow(f"{label}保留", box)
            self.days[group] = box
        keep_box = QGroupBox("保留天數（超過會自動清除）")
        keep_box.setLayout(keep)

        self.stats = QLabel()
        self.stats.setWordWrap(True)
        stats_box = QGroupBox("目前紀錄")
        QVBoxLayout(stats_box).addWidget(self.stats)

        self.delete_days = QSpinBox()
        self.delete_days.setRange(*appconfig.LOG_DAYS_RANGE)
        self.delete_days.setSuffix(" 天")
        self.delete_days.setValue(30)
        self.delete_button = QPushButton("刪除")
        self.delete_button.clicked.connect(self.delete_old)
        delete_row = QHBoxLayout()
        delete_row.addWidget(QLabel("刪除"))
        delete_row.addWidget(self.delete_days)
        delete_row.addWidget(QLabel("前的紀錄（不分等級，事件編號不重設）"))
        delete_row.addWidget(self.delete_button)
        delete_row.addStretch()
        self.purge_button = QPushButton("立即清除過期紀錄")
        self.purge_button.clicked.connect(self.purge_now)
        self.viewer_button = QPushButton("開啟事件檢視器")
        self.viewer_button.clicked.connect(self.viewerRequested)
        self.folder_button = QPushButton("開啟紀錄資料夾")
        self.folder_button.clicked.connect(lambda: self.open_folder(str(eventlog.log_dir())))
        tools_row = QHBoxLayout()
        for b in (self.purge_button, self.viewer_button, self.folder_button):
            tools_row.addWidget(b)
        tools_row.addStretch()
        tools_box = QGroupBox("維護")
        tools = QVBoxLayout(tools_box)
        tools.addLayout(delete_row)
        tools.addLayout(tools_row)

        self.reset_button = QPushButton("初始化事件紀錄…")
        self.reset_button.clicked.connect(self.reset_log)
        reset_box = QGroupBox("初始化")
        reset = QHBoxLayout(reset_box)
        reset.addWidget(self.reset_button)
        reset.addWidget(QLabel("清空全部紀錄，事件編號從 #1 重新開始；刪除前會自動備份。"), 1)

        self.message = QLabel()  # 最近一次維護的結果
        self.message.setWordWrap(True)
        lay = QVBoxLayout(self)
        for w in (keep_box, stats_box, tools_box, reset_box, self.message):
            lay.addWidget(w)
        lay.addStretch()
        self.refresh_stats()

    def _ask(self, title: str, text: str) -> QMessageBox.StandardButton:
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

    def _warn(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def retention(self) -> dict[str, int]:
        return {g: b.value() for g, b in self.days.items()}

    def refresh_stats(self) -> None:
        s = eventlog.summary()
        groups = "｜".join(f"{eventlog.GROUP_LABEL[g]} {n:,}" for g, n in s.counts.items())
        oldest = f"，最舊 {s.oldest:%Y-%m-%d}" if s.oldest else ""
        self.stats.setText(f"共 {s.total:,} 筆（{groups}）{oldest}，佔 {s.size / 1024 / 1024:.1f} MB")

    def _done(self, text: str) -> None:
        self.message.setText(text)
        self.refresh_stats()

    def apply(self) -> None:
        new = self.retention()
        if new != appconfig.log_retention():
            appconfig.remember_log_retention(new)
            eventlog.info("配置", "保留天數改為 " + "、".join(f"{eventlog.GROUP_LABEL[g]} {d} 天" for g, d in new.items()))
        removed = eventlog.purge(new)
        if removed:
            self.message.setText(f"已清除 {removed:,} 筆過期紀錄。")
        self.refresh_stats()

    def purge_now(self) -> None:
        """依已儲存的天數清除；畫面上還沒套用的數字不算。"""
        removed = eventlog.purge(appconfig.log_retention())
        if removed:
            eventlog.compact()
        self._done(f"已清除 {removed:,} 筆過期紀錄。" if removed else "沒有過期的紀錄。")

    def delete_old(self) -> None:
        days = self.delete_days.value()
        n = eventlog.count_older_than(days)
        if n == 0:
            self._done(f"沒有 {days} 天前的紀錄。")
            return
        if self.ask("刪除紀錄", f"要刪除 {days} 天前的 {n:,} 筆紀錄嗎？\n（不分等級，事件編號不會重設）") != QMessageBox.Yes:
            return
        removed = eventlog.delete_older_than(days)
        eventlog.compact()
        eventlog.info("事件紀錄", f"手動刪除 {days} 天前的紀錄 {removed:,} 筆")
        self._done(f"已刪除 {removed:,} 筆。")

    def reset_log(self) -> None:
        total = eventlog.summary().total
        if self.ask("初始化事件紀錄", f"將刪除全部 {total:,} 筆紀錄，事件編號從 #1 重新開始。\n"
                    f"刪除前會先備份到：\n{eventlog.backup_dir()}\n\n確定要初始化嗎？") != QMessageBox.Yes:
            return
        try:
            n, backup = eventlog.reset()
        except (OSError, RuntimeError) as e:
            eid = eventlog.error("事件紀錄", f"初始化失敗：{e}", e)
            self.warn("初始化失敗", eventlog.with_event_id(f"沒有刪除任何紀錄。\n\n{e}", eid))
            return
        self._done(f"已初始化，刪除 {n:,} 筆；備份在：{backup}")


class SettingsDialog(QDialog):
    def __init__(self, theme: ThemeManager, fonts: FontManager, open_viewer: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置")
        self.resize(640, 520)
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
