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
        self.setWindowTitle(self.tr("{title} — 預覽").format(title=title))
        self.resize(1000, 600)
        self.changes = changes
        self.table = QTableWidget(len(changes), 4)
        self.table.setHorizontalHeaderLabels([self.tr("識別碼"), self.tr("英文"), self.tr("修改前"), self.tr("修改後")])
        for r, c in enumerate(changes):
            key = QTableWidgetItem(".".join(c.row.key))
            key.setFlags(key.flags() | Qt.ItemIsUserCheckable)
            key.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, key)
            for col, text in ((1, c.row.source), (2, c.before), (3, c.after)):
                self.table.setItem(r, col, QTableWidgetItem(text.replace("\n", " ⏎ ")))
        self.table.resizeColumnsToContents()
        self.summary = QLabel()
        all_btn, none_btn = QPushButton(self.tr("全選")), QPushButton(self.tr("全不選"))
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.table.itemChanged.connect(self._update_summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("套用"))
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
        # itemChanged 由 model 的 dataChanged 轉發，只擋 table 本身擋不住，要擋 model。
        model = self.table.model()
        model.blockSignals(True)
        try:
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setCheckState(state)
        finally:
            model.blockSignals(False)
        self.table.viewport().update()
        self._update_summary()

    def _update_summary(self, *_):
        self.summary.setText(self.tr("共 {total} 個字串，勾選 {checked} 個").format(total=len(self.changes),
                                                                              checked=len(self.checked())))

    def checked(self) -> list[Change]:
        return [c for r, c in enumerate(self.changes) if self.table.item(r, 0).checkState() == Qt.Checked]


class ReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("在副語系中尋找取代"))
        self.find = QLineEdit()
        self.replace = QLineEdit()
        self.regex = QCheckBox(self.tr("規則運算式"))
        self.case = QCheckBox(self.tr("區分大小寫"))
        self.case.setChecked(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("預覽"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow(self.tr("尋找："), self.find)
        form.addRow(self.tr("取代為："), self.replace)
        form.addRow(self.regex)
        form.addRow(self.case)
        form.addRow(buttons)
