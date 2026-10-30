"""下方詳細區：元件路徑、說明註解、字元級差異、副語系多行編輯。"""

from __future__ import annotations

import difflib
import html

from PySide6.QtCore import QCoreApplication, QEvent, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core import i18n
from ..core.langfile import FIELD_LABEL
from ..core.validate import simplified_spans
from . import theme


def diff_html(master: str, slave: str, exceptions: list[str]) -> str:
    """主語系與副語系的字元級差異；副語系的殘留簡體字標紅底。顏色依目前主題。"""
    c = theme.colors()
    red = {a for a, _ in simplified_spans(slave, exceptions)}
    m_out, s_out = [], []
    sm = difflib.SequenceMatcher(None, master, slave, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        m_part = html.escape(master[a1:a2])
        m_out.append(m_part if op == "equal" else f'<span style="background:{c.diff_removed}">{m_part}</span>')
        for k in range(b1, b2):
            ch = html.escape(slave[k])
            if k in red:
                s_out.append(f'<span style="background:{c.simplified_bg};color:{c.simplified_fg}">{ch}</span>')
            elif op != "equal":
                s_out.append(f'<span style="background:{c.diff_added}">{ch}</span>')
            else:
                s_out.append(ch)
    br = lambda s: "".join(s).replace("\n", "<br>")
    master_label = QCoreApplication.translate("DetailPanel", "主語系：")
    slave_label = QCoreApplication.translate("DetailPanel", "副語系：")
    return f"<b>{master_label}</b>{br(m_out)}<br><b>{slave_label}</b>{br(s_out)}"


class DetailPanel(QWidget):
    applyRequested = Signal(int, str)  # (列, 新文字)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row: int | None = None
        self.path = QLabel()
        self.path.setWordWrap(True)
        self.comments = QLabel()
        self.comments.setWordWrap(True)
        self.comments.setStyleSheet(f"color:{theme.colors().comment_fg}")
        self.diff = QTextBrowser()
        self.diff.setMaximumHeight(90)
        self.editor = QPlainTextEdit()
        self.editor.setMaximumHeight(90)
        self.apply_btn = QPushButton()
        self.revert_btn = QPushButton()
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
        self.model = None
        self._set_texts()
        self.show_row(None, None)

    def _set_texts(self) -> None:
        self.apply_btn.setText(self.tr("套用"))
        self.revert_btn.setText(self.tr("還原"))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.LanguageChange:
            self._set_texts()
            self._show_labels()
            self.refresh_colors()
        super().changeEvent(event)

    def refresh_colors(self) -> None:
        """主題切換後重畫說明與差異標色（編輯框裡尚未套用的文字保留）。"""
        self.comments.setStyleSheet(f"color:{theme.colors().comment_fg}")
        if self.row is not None:
            self.diff.setHtml(diff_html(self.model.master_text(self.row) or "", self.model.slave_text(self.row) or "",
                                        self.model.exceptions))

    def show_row(self, model, i: int | None) -> None:
        self.model, self.row = model, i
        enabled = i is not None and model.is_editable(i)
        self.editor.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.revert_btn.setEnabled(enabled)
        self._show_labels()
        if i is None:
            self.diff.clear()
            self.editor.clear()
            return
        self.diff.setHtml(diff_html(model.master_text(i) or "", model.slave_text(i) or "", model.exceptions))
        self.editor.setPlainText(model.slave_text(i) or "")

    def _show_labels(self) -> None:
        """元件路徑與說明註解；切換介面語言時只重設這些，編輯框裡尚未套用的文字保留。"""
        if self.row is None:
            self.path.setText(self.tr("（未選取）"))
            self.comments.clear()
            return
        r = self.model.rows[self.row]
        lf = self.model.slave if r.s_index is not None else self.model.master
        e = lf.entries[r.s_index if r.s_index is not None else r.m_index]
        key = " &gt; ".join(html.escape(x) for x in r.key)
        field = i18n.translate("Field", FIELD_LABEL[r.field])
        self.path.setText(self.tr("<b>{key}</b>　欄位：{field}").format(key=key, field=field))
        comments = " / ".join(c for c in e.comments if c) or self.tr("（無）")
        self.comments.setText(self.tr("說明：{comments}").format(comments=comments))

    def _apply(self) -> None:
        if self.row is not None:
            text = self.editor.toPlainText()
            if self.model.rows[self.row].item is not None:
                text = text.replace("\n", " ")  # 單行字串不能有換行
            self.applyRequested.emit(self.row, text)

    def _revert(self) -> None:
        if self.row is not None:
            self.applyRequested.emit(self.row, self.model.original[self.row] or "")
