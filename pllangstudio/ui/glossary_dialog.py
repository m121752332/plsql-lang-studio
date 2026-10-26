"""用語對照表編輯器。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.glossary import Glossary, Rule

APPLY = 2  # 自訂的 done() 結果：儲存並套用到副語系


class GlossaryDialog(QDialog):
    def __init__(self, g: Glossary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("用語對照表")
        self.resize(760, 560)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["啟用", "尋找", "取代為", "例外（以 , 分隔）"])
        for rule in g.rules:
            self._add(rule)
        self.exceptions = QLineEdit(", ".join(g.simplified_exceptions))

        add, delete = QPushButton("新增"), QPushButton("刪除")
        up, down = QPushButton("上移"), QPushButton("下移")
        add.clicked.connect(lambda: self._add(Rule("", "")))
        delete.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        side = QVBoxLayout()
        for b in (add, delete, up, down):
            side.addWidget(b)
        side.addStretch()
        body = QHBoxLayout()
        body.addWidget(self.table)
        body.addLayout(side)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("儲存")
        apply_btn = buttons.addButton("儲存並套用到副語系…", QDialogButtonBox.ActionRole)
        apply_btn.clicked.connect(lambda: self.done(APPLY))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("規則依清單順序套用，較長的詞請排在前面（例如「配置文件」在「配置」前面）。"))
        lay.addLayout(body)
        lay.addWidget(QLabel("殘留簡體字的例外詞（以 , 分隔）："))
        lay.addWidget(self.exceptions)
        lay.addWidget(buttons)

    def _add(self, rule: Rule) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._fill(r, rule)

    def _fill(self, r: int, rule: Rule) -> None:
        on = QTableWidgetItem()
        on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        on.setCheckState(Qt.Checked if rule.enabled else Qt.Unchecked)
        self.table.setItem(r, 0, on)
        for col, text in ((1, rule.find), (2, rule.replace), (3, ", ".join(rule.exceptions))):
            self.table.setItem(r, col, QTableWidgetItem(text))

    def _rule(self, r: int) -> Rule:
        text = lambda c: (self.table.item(r, c).text() if self.table.item(r, c) else "").strip()
        return Rule(text(1), text(2), [x.strip() for x in text(3).split(",") if x.strip()],
                    self.table.item(r, 0).checkState() == Qt.Checked)

    def _move(self, step: int) -> None:
        r = self.table.currentRow()
        t = r + step
        if r < 0 or not 0 <= t < self.table.rowCount():
            return
        a, b = self._rule(r), self._rule(t)
        self._fill(r, b)
        self._fill(t, a)
        self.table.setCurrentCell(t, 1)

    def glossary(self) -> Glossary:
        rules = [self._rule(r) for r in range(self.table.rowCount())]
        return Glossary([x for x in rules if x.find],
                        [x.strip() for x in self.exceptions.text().split(",") if x.strip()])
