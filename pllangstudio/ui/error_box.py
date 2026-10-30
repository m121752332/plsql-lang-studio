"""有事件編號的錯誤對話框：多「複製事件編號」與「開啟事件檢視器」兩個按鈕，回報問題時不用自己抄編號（見 ADR-0018）。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox


def error_box(parent, title: str, text: str, event_id: int | None,
              open_viewer: Callable[[int], None] | None = None, icon=QMessageBox.Warning) -> QMessageBox:
    """建立對話框，由呼叫端 exec()。沒有事件編號時只有「確定」。按任何按鈕都會關閉對話框。"""
    box = QMessageBox(icon, title, text, QMessageBox.Ok, parent)
    if event_id is None:
        return box
    copy = box.addButton(QCoreApplication.translate("error_box", "複製事件編號"), QMessageBox.ActionRole)
    view = (box.addButton(QCoreApplication.translate("error_box", "開啟事件檢視器"), QMessageBox.ActionRole)
            if open_viewer else None)
    box.setDefaultButton(QMessageBox.Ok)
    box.setEscapeButton(QMessageBox.Ok)  # 有 ActionRole 按鈕時 Qt 不會自動指定，Esc 與右上角 X 會沒反應

    def clicked(b) -> None:
        if b == copy:
            QApplication.clipboard().setText(f"#{event_id}")
        elif view is not None and b == view:
            open_viewer(event_id)
    box.buttonClicked.connect(clicked)
    return box
