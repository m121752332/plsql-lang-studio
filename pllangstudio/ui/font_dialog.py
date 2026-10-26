"""字型與大小對話框：選好按「確定」才套用，「還原預設」立即回到系統字型。"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFontComboBox, QFormLayout, QLabel, QPushButton, QSpinBox,
                               QVBoxLayout)

from .fonts import MAX_SIZE, MIN_SIZE, FontManager

SAMPLE = "The quick brown fox 永和九年，歲在癸丑 0123456789"


class FontDialog(QDialog):
    def __init__(self, manager: FontManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("字型與大小")
        self.family = QFontComboBox()
        self.family.setCurrentFont(QFont(manager.family()))
        self.size = QSpinBox()
        self.size.setRange(MIN_SIZE, MAX_SIZE)
        self.size.setSuffix(" pt")
        self.size.setValue(manager.size())
        self.sample = QLabel(SAMPLE)
        self.sample.setWordWrap(True)
        self.family.currentFontChanged.connect(self._preview)
        self.size.valueChanged.connect(self._preview)
        self._preview()

        self.reset_button = QPushButton("還原預設")
        self.reset_button.clicked.connect(self._reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.addButton(self.reset_button, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("字型", self.family)
        form.addRow("大小", self.size)
        form.addRow("預覽", self.sample)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _preview(self, *_args) -> None:
        font = QFont(self.family.currentFont())
        font.setPointSize(self.size.value())
        self.sample.setFont(font)

    def _reset(self) -> None:
        self.manager.reset()
        super().accept()

    def accept(self) -> None:
        self.manager.set_font(self.family.currentFont().family(), self.size.value())
        super().accept()
