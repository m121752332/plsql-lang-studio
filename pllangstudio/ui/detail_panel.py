"""下方詳細區：元件路徑、說明註解、字元級差異、SLAVE 多行編輯。"""

from __future__ import annotations

import difflib
import html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core.langfile import FIELD_LABEL
from ..core.validate import simplified_spans


def diff_html(master: str, slave: str, exceptions: list[str]) -> str:
    """MASTER 與 SLAVE 的字元級差異；SLAVE 的殘留簡體字標紅底。"""
    red = {a for a, _ in simplified_spans(slave, exceptions)}
    m_out, s_out = [], []
    sm = difflib.SequenceMatcher(None, master, slave, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        m_part = html.escape(master[a1:a2])
        m_out.append(m_part if op == "equal" else f'<span style="background:#ffd7d7">{m_part}</span>')
        for k in range(b1, b2):
            ch = html.escape(slave[k])
            if k in red:
                s_out.append(f'<span style="background:#ff8080;color:white">{ch}</span>')
            elif op != "equal":
                s_out.append(f'<span style="background:#d7f5d7">{ch}</span>')
            else:
                s_out.append(ch)
    br = lambda s: "".join(s).replace("\n", "<br>")
    return (f"<b>MASTER：</b>{br(m_out)}<br><b>SLAVE&nbsp;&nbsp;：</b>{br(s_out)}")


class DetailPanel(QWidget):
    applyRequested = Signal(int, str)  # (列, 新文字)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row: int | None = None
        self.path = QLabel()
        self.path.setWordWrap(True)
        self.comments = QLabel()
        self.comments.setWordWrap(True)
        self.comments.setStyleSheet("color:#666")
        self.diff = QTextBrowser()
        self.diff.setMaximumHeight(90)
        self.editor = QPlainTextEdit()
        self.editor.setMaximumHeight(90)
        self.apply_btn = QPushButton("套用")
        self.revert_btn = QPushButton("還原")
        self.apply_btn.clicked.connect(self._apply)
        self.revert_btn.clicked.connect(self._revert)

        buttons = QVBoxLayout()
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.revert_btn)
        buttons.addStretch()
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.editor)
        edit_row.addLayout(buttons)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        for w in (self.path, self.comments, self.diff):
            lay.addWidget(w)
        lay.addLayout(edit_row)
        self.show_row(None, None)

    def show_row(self, model, i: int | None) -> None:
        self.model, self.row = model, i
        enabled = i is not None and model.is_editable(i)
        self.editor.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.revert_btn.setEnabled(enabled)
        if i is None:
            self.path.setText("（未選取）")
            self.comments.clear()
            self.diff.clear()
            self.editor.clear()
            return
        r = model.rows[i]
        lf = model.slave if r.s_index is not None else model.master
        e = lf.entries[r.s_index if r.s_index is not None else r.m_index]
        self.path.setText(f"<b>{' &gt; '.join(html.escape(x) for x in r.key)}</b>　欄位：{FIELD_LABEL[r.field]}")
        self.comments.setText("說明：" + (" / ".join(c for c in e.comments if c) or "（無）"))
        self.diff.setHtml(diff_html(model.master_text(i) or "", model.slave_text(i) or "", model.exceptions))
        self.editor.setPlainText(model.slave_text(i) or "")

    def _apply(self) -> None:
        if self.row is not None:
            text = self.editor.toPlainText()
            if self.model.rows[self.row].item is not None:
                text = text.replace("\n", " ")  # 單行字串不能有換行
            self.applyRequested.emit(self.row, text)

    def _revert(self) -> None:
        if self.row is not None:
            self.applyRequested.emit(self.row, self.model.original[self.row] or "")
