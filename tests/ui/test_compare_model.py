import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.compare import Status
from pllangstudio.ui.compare_model import COL_MASTER, COL_SLAVE, CompareFilter, CompareModel

pytestmark = needs_lang_dir


@pytest.fixture
def model(qtbot):
    m = CompareModel(QUndoStack())
    m.load(langfile.load(LANG_DIR / "Chinese.lang"), langfile.load(LANG_DIR / "Taiwan.lang"), ["游標", "批准"])
    return m


def find_row(model, slave_text):
    return next(i for i in range(model.rowCount()) if model.slave_text(i) == slave_text)


def test_row_count_and_counts(model):
    assert model.rowCount() == 6672
    c = model.counts()
    assert c["ALL"] == 6672 and c[Status.SIMPLIFIED] == 1 and c[Status.MODIFIED] == 0


def test_master_not_editable_slave_editable(model):
    i = find_row(model, "&取消")
    assert not model.flags(model.index(i, COL_MASTER)) & Qt.ItemIsEditable
    assert model.flags(model.index(i, COL_SLAVE)) & Qt.ItemIsEditable
    assert not model.setData(model.index(i, COL_MASTER), "改")


def test_edit_marks_modified_and_undo_restores(model):
    i = find_row(model, "&取消")
    assert model.setData(model.index(i, COL_SLAVE), "&取消X")
    assert model.slave_text(i) == "&取消X" and Status.MODIFIED in model.status[i]
    assert model.modified_count() == 1
    model.undo_stack.undo()
    assert model.slave_text(i) == "&取消" and Status.MODIFIED not in model.status[i]


def test_placeholder_error_flagged(model):
    i = next(i for i in range(model.rowCount()) if "%1" in (model.slave_text(i) or ""))
    model.request_edit([(i, model.slave_text(i).replace("%1", ""))], "測試")
    assert Status.ERROR in model.status[i] and model.has_errors() == [i]


def test_batch_is_single_undo_step(model):
    rows = [find_row(model, "&取消"), find_row(model, "定義")]
    model.request_edit([(rows[0], "A"), (rows[1], "B")], "批次")
    assert model.undo_stack.count() == 1
    model.undo_stack.undo()
    assert model.slave_text(rows[0]) == "&取消" and model.slave_text(rows[1]) == "定義"


def test_mark_saved_clears_modified(model):
    i = find_row(model, "&取消")
    model.request_edit([(i, "改")], "測試")
    model.mark_saved()
    assert model.modified_count() == 0 and model.undo_stack.isClean()


def test_filter_by_status_and_search(model):
    f = CompareFilter()
    f.setSourceModel(model)
    f.set_status(Status.SIMPLIFIED)
    assert f.rowCount() == 1
    f.set_status(None)
    f.set_search("tablespace", "英文")
    assert 0 < f.rowCount() < 200
    f.set_search("天后", "SLAVE")
    assert f.rowCount() == 1


@pytest.fixture
def hu_model(qtbot):
    m = CompareModel(QUndoStack())
    m.load(langfile.load(LANG_DIR / "Chinese.lang"), langfile.load(LANG_DIR / "Hungarian.lang"), [])
    return m


def test_request_edit_rejects_row_without_slave(hu_model):
    i = next(i for i, r in enumerate(hu_model.rows) if r.s_index is None)
    with pytest.raises(ValueError, match="沒有 SLAVE"):
        hu_model.request_edit([(i, "改")], "測試")
    assert hu_model.undo_stack.count() == 0


def test_request_edit_rejects_newline_on_single_line_and_is_atomic(model):
    i = find_row(model, "&取消")
    j = find_row(model, "定義")
    with pytest.raises(ValueError, match="單行"):
        model.request_edit([(i, "A"), (j, "甲\n乙")], "批次")
    assert model.slave_text(i) == "&取消" and model.undo_stack.count() == 0


def test_request_edit_multiline_row_allows_newline_and_undo(model):
    i = next(i for i, r in enumerate(model.rows) if r.item is None and r.s_index is not None)
    before = model.slave_text(i)
    model.request_edit([(i, "甲\n乙")], "多行")
    assert model.slave_text(i) == "甲\n乙"
    model.undo_stack.undo()
    assert model.slave_text(i) == before


def test_batch_emits_countschanged_once(model, qtbot):
    rows = [find_row(model, "&取消"), find_row(model, "定義")]
    with qtbot.waitSignal(model.countsChanged, timeout=1000):
        model.request_edit([(rows[0], "A"), (rows[1], "B")], "批次")
    counter = []
    model.countsChanged.connect(lambda: counter.append(1))
    model.undo_stack.undo()
    assert len(counter) == 1
