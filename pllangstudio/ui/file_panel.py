"""左側檔案清單：上方是工作區語言檔，下方是 PL/SQL Developer 的語言檔，中間可拖曳調整高度。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QMenu, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..core.workspace import LangInfo


def _tree(headers: list[str]) -> QTreeWidget:
    t = QTreeWidget()
    t.setHeaderLabels(headers)
    t.setRootIsDecorated(False)
    t.setContextMenuPolicy(Qt.CustomContextMenu)
    return t


def _section(title: str, tree: QTreeWidget) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    label = QLabel(f"<b>{title}</b>")
    label.setContentsMargins(4, 4, 4, 0)
    lay.addWidget(label)
    lay.addWidget(tree)
    return box


class FilePanel(QSplitter):
    setMaster = Signal(str)
    setSlave = Signal(str)
    importRequested = Signal(str)
    openTxt = Signal(str)
    openFolder = Signal(str)  # 檔案的完整路徑
    removeRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.master = self.slave = ""
        self.workspace = _tree(["語言檔", "角色", "已部署"])
        self.installed = _tree(["語言檔", "大小", "日期", "已匯入"])
        self.addWidget(_section("工作區", self.workspace))
        self.addWidget(_section("PL/SQL 語言檔", self.installed))
        self.setSizes([300, 400])
        self.setChildrenCollapsible(False)
        self.installed.customContextMenuRequested.connect(lambda p: self._menu(self.installed, p, installed=True))
        self.workspace.customContextMenuRequested.connect(lambda p: self._menu(self.workspace, p, installed=False))
        self.workspace.itemDoubleClicked.connect(lambda item, _c: self.setSlave.emit(item.text(0)))
        self.installed.itemDoubleClicked.connect(lambda item, _c: self.importRequested.emit(item.text(0)))

    def refresh(self, installed: list[LangInfo], workspace: list[LangInfo], master: str, slave: str) -> None:
        self.master, self.slave = master, slave
        self.workspace.clear()
        for info in workspace:
            role = "🔒 主語系" if info.name == master else ("副語系" if info.name == slave else "")
            item = QTreeWidgetItem([info.name, role, "✓" if info.deployed else "未部署"])
            if info.name == master:
                item.setToolTip(1, "唯讀，只作為比對基準")
            item.setData(0, Qt.UserRole, str(info.path))
            self.workspace.addTopLevelItem(item)
        self.installed.clear()
        for info in installed:
            item = QTreeWidgetItem([info.name, f"{info.size // 1024:,} KB",
                                    datetime.fromtimestamp(info.mtime).strftime("%Y-%m-%d"), "✓" if info.imported else ""])
            item.setData(0, Qt.UserRole, str(info.path))
            self.installed.addTopLevelItem(item)
        for t in (self.workspace, self.installed):
            for col in range(t.columnCount()):
                t.resizeColumnToContents(col)

    def _menu(self, tree: QTreeWidget, pos, installed: bool) -> None:
        item = tree.itemAt(pos)
        if not item:
            return
        name, path = item.text(0), item.data(0, Qt.UserRole)
        menu = QMenu(self)
        # 主語系和副語系不能是同一個檔案
        menu.addAction("設為主語系", lambda: self.setMaster.emit(name)).setEnabled(name != self.slave)
        menu.addAction("設為副語系", lambda: self.setSlave.emit(name)).setEnabled(name != self.master)
        if installed:
            menu.addAction("匯入工作區", lambda: self.importRequested.emit(name))
        else:
            menu.addAction("用記事本開 .txt", lambda: self.openTxt.emit(name))
            menu.addAction("從工作區移除…", lambda: self.removeRequested.emit(name)).setEnabled(
                name not in (self.master, self.slave))
        menu.addAction("開啟所在資料夾", lambda: self.openFolder.emit(path))
        menu.exec(tree.viewport().mapToGlobal(pos))
