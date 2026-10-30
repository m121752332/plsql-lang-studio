"""事件檢視器：依等級、期間、關鍵字查詢事件紀錄，看詳細內容、複製與匯出（見 ADR-0017）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import PySide6
from PySide6.QtCore import QEvent, Qt, qVersion
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import eventlog
from ..core import i18n
from ..core.i18n import QT_TRANSLATE_NOOP
from .theme import ThemeManager, colors

PERIODS = [(QT_TRANSLATE_NOOP("EventViewer", "今天"), "today"), (QT_TRANSLATE_NOOP("EventViewer", "最近 7 天"), 7),
           (QT_TRANSLATE_NOOP("EventViewer", "最近 30 天"), 30), (QT_TRANSLATE_NOOP("EventViewer", "全部"), None)]
HEADERS = [QT_TRANSLATE_NOOP("EventViewer", "編號"), QT_TRANSLATE_NOOP("EventViewer", "時間"),
           QT_TRANSLATE_NOOP("EventViewer", "等級"), QT_TRANSLATE_NOOP("EventViewer", "類別"),
           QT_TRANSLATE_NOOP("EventViewer", "訊息")]


class EventViewer(QWidget):
    def __init__(self, theme: ThemeManager | None = None, parent=None,
                 save_path: Callable[[str], str] | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)  # 獨立視窗，可以邊操作主視窗邊看
        self.resize(1000, 600)
        self.save_path = save_path or self._ask_save_path
        self.events: list[eventlog.Event] = []

        top = QHBoxLayout()
        self.level_label, self.period_label = QLabel(), QLabel()
        top.addWidget(self.level_label)
        self.level_boxes: dict[str, QCheckBox] = {}
        for group in eventlog.GROUP_LABEL:
            box = QCheckBox()
            box.setChecked(True)
            box.toggled.connect(self.refresh)
            top.addWidget(box)
            self.level_boxes[group] = box
        top.addSpacing(20)
        top.addWidget(self.period_label)
        self.period = QComboBox()
        for _label, value in PERIODS:
            self.period.addItem("", value)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)
        self.search = QLineEdit()
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        for col, w in enumerate((70, 150, 70, 100)):
            self.table.setColumnWidth(col, w)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)

        bottom = QHBoxLayout()
        self.count_label = QLabel()
        bottom.addWidget(self.count_label, 1)
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_button = QPushButton()
        self.export_button.clicked.connect(self.export)
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.export_button)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)
        if theme is not None:
            theme.changed.connect(self.refresh)
        self._set_texts()
        self.refresh()

    def _set_texts(self) -> None:
        self.setWindowTitle(self.tr("事件檢視器"))
        self.level_label.setText(self.tr("等級"))
        for group, box in self.level_boxes.items():
            box.setText(i18n.translate("eventlog", eventlog.GROUP_LABEL[group]))
        self.period_label.setText(self.tr("期間"))
        for k, (label, _value) in enumerate(PERIODS):
            self.period.setItemText(k, self.tr(label))
        self.search.setPlaceholderText(self.tr("搜尋訊息或類別；輸入 #編號 直接找事件"))
        self.refresh_button.setText(self.tr("重新整理"))
        self.table.setHorizontalHeaderLabels([self.tr(h) for h in HEADERS])
        self.copy_button.setText(self.tr("複製選取"))
        self.export_button.setText(self.tr("匯出篩選結果…"))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.LanguageChange:
            self._set_texts()
            self.refresh()
        super().changeEvent(event)

    def since(self) -> datetime | None:
        value = self.period.currentData()
        now = datetime.now()
        if value == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        return None if value is None else now - timedelta(days=value)

    def refresh(self, *_args) -> None:
        groups = {g for g, b in self.level_boxes.items() if b.isChecked()}
        self.events = eventlog.query(groups, self.since(), self.search.text())
        level_fg = colors().event_level
        self.table.setRowCount(len(self.events))
        for r, e in enumerate(self.events):
            color = level_fg.get(eventlog.GROUP_OF_LEVEL.get(e.level, ""))
            first_line = e.message.splitlines()[0] if e.message else ""
            level = i18n.translate("eventlog", e.level_label)
            for c, text in enumerate((str(e.id), f"{e.time:%Y-%m-%d %H:%M:%S}", level, e.category, first_line)):
                item = QTableWidgetItem(text)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
        self.count_label.setText(self.tr("共 {n:,} 筆").format(n=len(self.events)))
        if self.events:
            self.table.selectRow(0)
        else:
            self.detail.clear()

    def selected_events(self) -> list[eventlog.Event]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.events[r] for r in rows if r < len(self.events)]

    def _show_detail(self) -> None:
        selected = self.selected_events()
        self.detail.setPlainText(eventlog.format_event(selected[0]) if selected else "")

    def copy_selected(self) -> None:
        QApplication.clipboard().setText("\n\n".join(eventlog.format_event(e) for e in self.selected_events()))

    def _ask_save_path(self, name: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, self.tr("匯出事件紀錄"), str(Path.home() / "Desktop" / name),
                                              self.tr("zip 檔 (*.zip)"))
        return path

    def export(self) -> None:
        if not self.events:
            return
        path = self.save_path(eventlog.export_name(datetime.now()))
        if not path:
            return
        try:
            eventlog.export_zip(self.events, Path(path), {"Qt": qVersion(), "PySide6": PySide6.__version__})
        except OSError as e:
            QMessageBox.warning(self, self.tr("匯出失敗"), f"{path}\n\n{e}")
            return
        eventlog.info("事件檢視器", f"匯出 {len(self.events)} 筆事件紀錄到 {path}")
        self.count_label.setText(self.tr("已匯出 {n:,} 筆到 {path}").format(n=len(self.events), path=path))
