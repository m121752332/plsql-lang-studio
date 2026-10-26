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
