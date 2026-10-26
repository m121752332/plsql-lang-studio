"""對照表格的 model 與篩選（見 ADR-0007）。"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QUndoStack

from ..core import compare
from ..core.compare import STATUS_LABEL, Status
from ..core.langfile import FIELD_LABEL, LangFile, check_line
from . import theme

COLUMNS = ["#", "狀態", "識別碼", "欄位", "英文", "主語系", "副語系"]
COL_NO, COL_STATUS, COL_KEY, COL_FIELD, COL_SOURCE, COL_MASTER, COL_SLAVE = range(7)
STATUS_ORDER = [Status.ERROR, Status.MODIFIED, Status.SIMPLIFIED, Status.UNTRANSLATED,
                Status.ONE_SIDED, Status.WARNING, Status.DIFFERENT]


def one_line(text: str | None) -> str:
    return "" if text is None else text.replace("\n", " ⏎ ")


class CompareModel(QAbstractTableModel):
    countsChanged = Signal()

    def __init__(self, undo_stack: QUndoStack, parent=None):
        super().__init__(parent)
        self.undo_stack = undo_stack
        self.master: LangFile | None = None
        self.slave: LangFile | None = None
        self.rows: list[compare.Row] = []
        self.original: list[str | None] = []
        self.status: list[set[Status]] = []
        self.issues: list[list] = []
        self.exceptions: list[str] = []
        self._by_ref: dict = {}
        self._by_key: dict = {}
        self._entry_rows: dict[int, list[int]] = {}

    # ---------- 載入 ----------

    def load(self, master: LangFile, slave: LangFile, exceptions: list[str],
             baseline: LangFile | None = None) -> None:
        """baseline：判斷「已修改」的比較基準（預設就是 slave 本身）。
        從記事本 .txt 載入時，傳入工作區裡的 .lang，修改過的字串才會標成 ✎。"""
        self.beginResetModel()
        self.master, self.slave, self.exceptions = master, slave, list(exceptions)
        self.rows = compare.align(master, slave)
        if baseline is None:
            self.original = [self.slave_text(i) for i in range(len(self.rows))]
        else:
            b_by_key = {e.key: k for k, e in enumerate(baseline.entries)}
            self.original = [compare.get_text(baseline, b_by_key.get(r.key), r.field, r.item) for r in self.rows]
        self._by_ref = {r.ref: i for i, r in enumerate(self.rows) if r.s_index is not None}
        self._by_key, self._entry_rows = {}, {}
        for i, r in enumerate(self.rows):
            self._by_key.setdefault(r.key, i)
            if r.s_index is not None:
                self._entry_rows.setdefault(r.s_index, []).append(i)
        self.status, self.issues = [], []
        for i in range(len(self.rows)):
            s, iss = self._compute(i)
            self.status.append(s)
            self.issues.append(iss)
        self.undo_stack.clear()
        self.endResetModel()
        self.countsChanged.emit()

    def _compute(self, i: int):
        return compare.row_status(self.rows[i], self.master, self.slave, self.original[i], self.exceptions)

    # ---------- 查詢 ----------

    def master_text(self, i: int) -> str | None:
        r = self.rows[i]
        return compare.get_text(self.master, r.m_index, r.field, r.item)

    def slave_text(self, i: int) -> str | None:
        r = self.rows[i]
        return compare.get_text(self.slave, r.s_index, r.field, r.item)

    def row_of_key(self, key) -> int | None:
        return self._by_key.get(key)

    def row_of_ref(self, ref) -> int | None:
        return self._by_ref.get(ref)

    def counts(self) -> Counter:
        c = Counter()
        for s in self.status:
            c.update(s)
        c["ALL"] = len(self.rows)
        return c

    def modified_count(self) -> int:
        return sum(Status.MODIFIED in s for s in self.status)

    def has_errors(self) -> list[int]:
        return [i for i, s in enumerate(self.status) if Status.ERROR in s]

    def is_editable(self, i: int) -> bool:
        return self.rows[i].s_index is not None

    # ---------- 修改 ----------

    def request_edit(self, edits: list[tuple[int, str]], label: str) -> None:
        """所有修改都經過這裡，包成一個可以復原的步驟。整批先驗證，有一筆不合法就什麼都不做。"""
        from .commands import EditCommand
        for i, new in edits:
            r = self.rows[i]
            if r.s_index is None:
                raise ValueError(f"第 {i + 1} 列不能修改：沒有副語系的翻譯")
            try:
                if r.item is None:
                    for line in (new.split("\n") if new else []):
                        check_line(line)
                else:
                    if "\n" in new:
                        raise ValueError("這一列是單行字串，不能包含換行")
                    check_line(new)
            except ValueError as e:
                raise ValueError(f"第 {i + 1} 列不能修改：{e}") from None
        real = [(i, self.slave_text(i), new) for i, new in edits if self.slave_text(i) != new]
        if real:
            self.undo_stack.push(EditCommand(self, real, label))

    def apply_texts(self, pairs: list[tuple[int, str]]) -> None:
        """一次套用多列文字，只發出一次 dataChanged 與 countsChanged。"""
        if not pairs:
            return
        touched: set[int] = set()
        for i, text in pairs:
            r = self.rows[i]
            compare.set_text(self.slave, r.s_index, r.field, r.item, text)
            # 同一個副語系條目的其他列也可能受影響（多行欄位），一起重算
            touched.update(self._entry_rows[r.s_index])
        for j in touched:
            self.status[j], self.issues[j] = self._compute(j)
        self.dataChanged.emit(self.index(min(touched), 0), self.index(max(touched), len(COLUMNS) - 1))
        self.countsChanged.emit()

    def apply_text(self, i: int, text: str) -> None:
        self.apply_texts([(i, text)])

    def mark_saved(self) -> None:
        self.original = [self.slave_text(i) for i in range(len(self.rows))]
        for i in range(len(self.rows)):
            self.status[i], self.issues[i] = self._compute(i)
        self.undo_stack.setClean()
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))
        self.countsChanged.emit()

    # ---------- Qt model 介面 ----------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        i, col = index.row(), index.column()
        r, st = self.rows[i], self.status[i]
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == COL_NO:
                return i + 1
            if col == COL_STATUS:
                return "".join(s.value for s in STATUS_ORDER if s in st)
            if col == COL_KEY:
                return ".".join(r.key)
            if col == COL_FIELD:
                label = FIELD_LABEL[r.field]
                return f"{label}（多行）" if r.item is None else (f"{label} {r.item + 1}" if r.field.name == "ITEMS" else label)
            text = {COL_SOURCE: r.source, COL_MASTER: self.master_text(i), COL_SLAVE: self.slave_text(i)}[col]
            return text if role == Qt.EditRole else one_line(text)
        if role == Qt.ToolTipRole:
            if col == COL_STATUS:
                lines = [STATUS_LABEL[s] for s in STATUS_ORDER if s in st] + [i_.message for i_ in self.issues[i]]
                return "\n".join(lines) or None
            if col in (COL_SOURCE, COL_MASTER, COL_SLAVE):
                return {COL_SOURCE: r.source, COL_MASTER: self.master_text(i), COL_SLAVE: self.slave_text(i)}[col]
        if role == Qt.BackgroundRole:
            c = theme.colors()
            if col in (COL_STATUS, COL_SLAVE):
                for s in STATUS_ORDER:
                    if s in st and s in c.status:
                        return QBrush(QColor(c.status[s]))
            key_index = r.s_index if r.s_index is not None else r.m_index
            return QBrush(QColor(c.group[key_index % 2]))
        if role == Qt.ForegroundRole and col == COL_MASTER:
            return QBrush(QColor(theme.colors().master_fg))
        return None

    def refresh_colors(self) -> None:
        """主題切換後重畫所有列。"""
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == COL_SLAVE and self.rows[index.row()].item is not None and self.is_editable(index.row()):
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not (self.flags(index) & Qt.ItemIsEditable):
            return False
        try:
            self.request_edit([(index.row(), str(value))], "編輯字串")
        except ValueError:
            return False
        return True


class CompareFilter(QSortFilterProxyModel):
    SCOPES = {"全部": (COL_KEY, COL_SOURCE, COL_MASTER, COL_SLAVE), "英文": (COL_SOURCE,),
              "主語系": (COL_MASTER,), "副語系": (COL_SLAVE,), "識別碼": (COL_KEY,)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_filter: Status | None = None
        self.text = ""
        self.scope = "全部"

    def set_status(self, status: Status | None) -> None:
        self.beginFilterChange()
        self.status_filter = status
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_search(self, text: str, scope: str) -> None:
        self.beginFilterChange()
        self.text, self.scope = text.lower(), scope
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row, source_parent):
        m: CompareModel = self.sourceModel()
        if self.status_filter is not None and self.status_filter not in m.status[source_row]:
            return False
        if self.text:
            for col in self.SCOPES[self.scope]:
                v = m.data(m.index(source_row, col), Qt.EditRole)
                if v and self.text in str(v).lower():
                    return True
            return False
        return True
