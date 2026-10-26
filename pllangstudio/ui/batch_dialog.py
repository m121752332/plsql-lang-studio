"""批次操作：尋找取代輸入框，以及共用的「預覽並勾選」對話框（見 ADR-0010）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.batch import Change


class PreviewDialog(QDialog):
    """列出所有會被修改的字串，每一列可以取消勾選。"""

    def __init__(self, title: str, changes: list[Change], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} — 預覽")
        self.resize(1000, 600)
        self.changes = changes
        self.table = QTableWidget(len(changes), 4)
        self.table.setHorizontalHeaderLabels(["識別碼", "英文", "修改前", "修改後"])
        for r, c in enumerate(changes):
            key = QTableWidgetItem(".".join(c.row.key))
            key.setFlags(key.flags() | Qt.ItemIsUserCheckable)
            key.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, key)
            for col, text in ((1, c.row.source), (2, c.before), (3, c.after)):
                self.table.setItem(r, col, QTableWidgetItem(text.replace("\n", " ⏎ ")))
        self.table.resizeColumnsToContents()
        self.summary = QLabel()
        all_btn, none_btn = QPushButton("全選"), QPushButton("全不選")
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.table.itemChanged.connect(self._update_summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("套用")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        top = QHBoxLayout()
        top.addWidget(self.summary)
        top.addStretch()
        top.addWidget(all_btn)
        top.addWidget(none_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addWidget(buttons)
        self._update_summary()

    def _set_all(self, state) -> None:
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)

    def _update_summary(self, *_):
        self.summary.setText(f"共 {len(self.changes)} 個字串，勾選 {len(self.checked())} 個")

    def checked(self) -> list[Change]:
        return [c for r, c in enumerate(self.changes) if self.table.item(r, 0).checkState() == Qt.Checked]


class ReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("在 SLAVE 中尋找取代")
        self.find = QLineEdit()
        self.replace = QLineEdit()
        self.regex = QCheckBox("規則運算式")
        self.case = QCheckBox("區分大小寫")
        self.case.setChecked(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("預覽")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("尋找：", self.find)
        form.addRow("取代為：", self.replace)
        form.addRow(self.regex)
        form.addRow(self.case)
        form.addRow(buttons)
