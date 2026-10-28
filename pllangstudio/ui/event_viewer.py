"""事件檢視器：依等級、期間、關鍵字查詢事件紀錄，看詳細內容、複製與匯出（見 ADR-0017）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import eventlog
from .theme import ThemeManager, colors

PERIODS = [("今天", "today"), ("最近 7 天", 7), ("最近 30 天", 30), ("全部", None)]
HEADERS = ["編號", "時間", "等級", "類別", "訊息"]


class EventViewer(QWidget):
    def __init__(self, theme: ThemeManager | None = None, parent=None,
                 save_path: Callable[[str], str] | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)  # 獨立視窗，可以邊操作主視窗邊看
        self.setWindowTitle("事件檢視器")
        self.resize(1000, 600)
        self.save_path = save_path or self._ask_save_path
        self.events: list[eventlog.Event] = []

        top = QHBoxLayout()
        top.addWidget(QLabel("等級"))
        self.level_boxes: dict[str, QCheckBox] = {}
        for group, label in eventlog.GROUP_LABEL.items():
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self.refresh)
            top.addWidget(box)
            self.level_boxes[group] = box
        top.addSpacing(20)
        top.addWidget(QLabel("期間"))
        self.period = QComboBox()
        for label, value in PERIODS:
            self.period.addItem(label, value)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋訊息或類別；輸入 #編號 直接找事件")
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1)
        refresh_button = QPushButton("重新整理")
        refresh_button.clicked.connect(self.refresh)
        top.addWidget(refresh_button)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
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
        copy_button = QPushButton("複製選取")
        copy_button.clicked.connect(self.copy_selected)
        export_button = QPushButton("匯出篩選結果…")
        export_button.clicked.connect(self.export)
        bottom.addWidget(copy_button)
        bottom.addWidget(export_button)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)
        if theme is not None:
            theme.changed.connect(self.refresh)
        self.refresh()

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
            for c, text in enumerate((str(e.id), f"{e.time:%Y-%m-%d %H:%M:%S}", e.level_label, e.category, first_line)):
                item = QTableWidgetItem(text)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
        self.count_label.setText(f"共 {len(self.events):,} 筆")
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
        path, _ = QFileDialog.getSaveFileName(self, "匯出事件紀錄", str(Path.home() / "Desktop" / name), "zip 檔 (*.zip)")
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
            QMessageBox.warning(self, "匯出失敗", f"{path}\n\n{e}")
            return
        eventlog.info("事件檢視器", f"匯出 {len(self.events)} 筆事件紀錄到 {path}")
        self.count_label.setText(f"已匯出 {len(self.events):,} 筆到 {path}")
