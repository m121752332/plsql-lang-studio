"""左側檔案清單：PL/SQL 語言檔、工作區兩個分頁。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTabWidget, QTreeWidget, QTreeWidgetItem

from ..core.workspace import LangInfo


def _tree(headers: list[str]) -> QTreeWidget:
    t = QTreeWidget()
    t.setHeaderLabels(headers)
    t.setRootIsDecorated(False)
    t.setContextMenuPolicy(Qt.CustomContextMenu)
    return t


class FilePanel(QTabWidget):
    setMaster = Signal(str)
    setSlave = Signal(str)
    importRequested = Signal(str)
    openTxt = Signal(str)
    openFolder = Signal(str)  # 檔案的完整路徑

    def __init__(self, parent=None):
        super().__init__(parent)
        self.installed = _tree(["PL/SQL 語言檔", "大小", "日期", "已匯入"])
        self.workspace = _tree(["工作區語言檔", "角色", "已部署"])
        self.addTab(self.installed, "PL/SQL 語言檔")
        self.addTab(self.workspace, "工作區")
        self.installed.customContextMenuRequested.connect(lambda p: self._menu(self.installed, p, installed=True))
        self.workspace.customContextMenuRequested.connect(lambda p: self._menu(self.workspace, p, installed=False))
        self.workspace.itemDoubleClicked.connect(lambda item, _c: self.setSlave.emit(item.text(0)))

    def refresh(self, installed: list[LangInfo], workspace: list[LangInfo], master: str, slave: str) -> None:
        self.installed.clear()
        for info in installed:
            item = QTreeWidgetItem([info.name, f"{info.size // 1024:,} KB",
                                    datetime.fromtimestamp(info.mtime).strftime("%Y-%m-%d"), "✓" if info.imported else ""])
            item.setData(0, Qt.UserRole, str(info.path))
            self.installed.addTopLevelItem(item)
        self.workspace.clear()
        for info in workspace:
            role = "M" if info.name == master else ("S" if info.name == slave else "")
            item = QTreeWidgetItem([info.name, role, "✓" if info.deployed else "未部署"])
            item.setData(0, Qt.UserRole, str(info.path))
            self.workspace.addTopLevelItem(item)
        for t in (self.installed, self.workspace):
            t.resizeColumnToContents(0)

    def _menu(self, tree: QTreeWidget, pos, installed: bool) -> None:
        item = tree.itemAt(pos)
        if not item:
            return
        name, path = item.text(0), item.data(0, Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("設為 MASTER", lambda: self.setMaster.emit(name))
        menu.addAction("設為 SLAVE", lambda: self.setSlave.emit(name))
        if installed:
            menu.addAction("匯入工作區", lambda: self.importRequested.emit(name))
        else:
            menu.addAction("用記事本開 .txt", lambda: self.openTxt.emit(name))
        menu.addAction("開啟所在資料夾", lambda: self.openFolder.emit(path))
        menu.exec(tree.viewport().mapToGlobal(pos))
