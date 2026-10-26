from PySide6.QtCore import Qt

from pllangstudio.core.batch import Change
from pllangstudio.core.compare import Row
from pllangstudio.core.glossary import Glossary, Rule
from pllangstudio.core.langfile import Field
from pllangstudio.ui.batch_dialog import PreviewDialog
from pllangstudio.ui.detail_panel import diff_html
from pllangstudio.ui.glossary_dialog import GlossaryDialog


def test_diff_html_marks_changes_and_simplified():
    h = diff_html("定义", "定后", [])
    assert "定" in h and "ff8080" in h  # 「后」是簡體字，標紅底
    assert "ffd7d7" in h  # MASTER 的「义」被標成差異


def test_preview_dialog_unchecked_rows_are_excluded(qtbot):
    row = Row(("W", "Btn", "Button"), Field.CAPTION, 0, "Save", 0, 0)
    changes = [Change(row, "儲存", "存檔"), Change(row, "取消", "取消X")]
    dlg = PreviewDialog("測試", changes)
    qtbot.addWidget(dlg)
    dlg.table.item(1, 0).setCheckState(Qt.Unchecked)
    assert dlg.checked() == [changes[0]]
    assert "勾選 1 個" in dlg.summary.text()


def test_glossary_dialog_roundtrip_and_move(qtbot):
    g = Glossary([Rule("配置", "設定"), Rule("新建", "新增", ["重新建"], enabled=False)], ["游標"])
    dlg = GlossaryDialog(g)
    qtbot.addWidget(dlg)
    assert dlg.glossary() == g
    dlg.table.setCurrentCell(1, 1)
    dlg._move(-1)
    assert [r.find for r in dlg.glossary().rules] == ["新建", "配置"]
