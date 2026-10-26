import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.batch import Change
from pllangstudio.core.compare import Row
from pllangstudio.core.glossary import Glossary, Rule
from pllangstudio.core.langfile import Field
from pllangstudio.ui.batch_dialog import PreviewDialog
from pllangstudio.ui.compare_model import CompareModel
from pllangstudio.ui.detail_panel import DetailPanel, diff_html
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


def test_preview_dialog_select_all_and_none_are_fast(qtbot):
    row = Row(("W", "Btn", "Button"), Field.CAPTION, 0, "Save", 0, 0)
    changes = [Change(row, f"舊{i}", f"新{i}") for i in range(2000)]
    dlg = PreviewDialog("測試", changes)
    qtbot.addWidget(dlg)
    count = []
    dlg.table.itemChanged.connect(lambda _item: count.append(1))
    dlg._set_all(Qt.Unchecked)
    assert count == []
    assert dlg.checked() == []
    assert "勾選 0 個" in dlg.summary.text()
    dlg._set_all(Qt.Checked)
    assert len(dlg.checked()) == 2000
    assert "勾選 2000 個" in dlg.summary.text()


@pytest.fixture
def chinese_model(qtbot):
    def _load(slave_name: str = "Taiwan.lang"):
        m = CompareModel(QUndoStack())
        m.load(langfile.load(LANG_DIR / "Chinese.lang"), langfile.load(LANG_DIR / slave_name),
               ["游標", "批准"])
        return m
    return _load


def _find_row(model, pred):
    return next(i for i in range(len(model.rows)) if pred(i))


@needs_lang_dir
def test_detail_panel_no_selection_disables_editing(qtbot, chinese_model):
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_row(chinese_model(), None)
    assert not panel.editor.isEnabled()
    assert not panel.apply_btn.isEnabled()
    assert not panel.revert_btn.isEnabled()


@needs_lang_dir
def test_detail_panel_single_line_apply_collapses_newline(qtbot, chinese_model):
    model = chinese_model()
    i = _find_row(model, lambda i: model.rows[i].item is not None and model.slave_text(i) == "&取消")
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_row(model, i)
    assert panel.editor.isEnabled()
    panel.editor.setPlainText("甲\n乙")
    with qtbot.waitSignal(panel.applyRequested) as blocker:
        panel.apply_btn.click()
    assert tuple(blocker.args) == (i, "甲 乙")


@needs_lang_dir
def test_detail_panel_multiline_apply_keeps_newline(qtbot, chinese_model):
    model = chinese_model()
    i = _find_row(model, lambda i: model.rows[i].item is None)
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_row(model, i)
    panel.editor.setPlainText("甲\n乙")
    with qtbot.waitSignal(panel.applyRequested) as blocker:
        panel._apply()
    assert tuple(blocker.args) == (i, "甲\n乙")


@needs_lang_dir
def test_detail_panel_revert_emits_original(qtbot, chinese_model):
    model = chinese_model()
    i = _find_row(model, lambda i: model.rows[i].item is not None and model.slave_text(i) == "&取消")
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_row(model, i)
    with qtbot.waitSignal(panel.applyRequested) as blocker:
        panel.revert_btn.click()
    assert tuple(blocker.args) == (i, model.original[i])


@needs_lang_dir
def test_detail_panel_non_editable_row_disables_editing(qtbot, chinese_model):
    model = chinese_model("Hungarian.lang")
    i = _find_row(model, lambda i: model.rows[i].s_index is None)
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_row(model, i)
    assert not panel.editor.isEnabled()
    assert not panel.apply_btn.isEnabled()
    assert not panel.revert_btn.isEnabled()
