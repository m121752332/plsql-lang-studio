import json
import shutil

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.compare import Status
from pllangstudio.core.langfile import Field
from pllangstudio.ui.compare_model import COL_SLAVE
from pllangstudio.ui.main_window import MainWindow

pytestmark = needs_lang_dir


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    installed = tmp_path / "Languages"
    installed.mkdir()
    for n in ["Chinese.lang", "Taiwan.lang", "Japanese.lang"]:
        shutil.copy(LANG_DIR / n, installed / n)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "settings.json").write_text(json.dumps({"plsql_lang_dir": str(installed)}), encoding="utf-8")
    return root, installed


@pytest.fixture
def win(qtbot, env, monkeypatch):
    root, _ = env
    answers = []
    w = MainWindow(root, elevate_fn=lambda s, d: False, info=lambda *a, **k: None,
                   ask=lambda *a, **k: answers.pop(0) if answers else QMessageBox.Yes)
    w.answers = answers
    qtbot.addWidget(w)
    return w


def row_of(win, text):
    return next(i for i in range(win.model.rowCount()) if win.model.slave_text(i) == text)


def test_opens_default_pair_with_auto_import(win, env):
    root, _ = env
    assert (win.master_name, win.slave_name) == ("Chinese.lang", "Taiwan.lang")
    assert win.model.rowCount() == 6672
    assert (root / "lang" / "Taiwan.lang").exists() and (root / "txt" / "Taiwan.txt").exists()
    assert win.filter_buttons[None].text() == "全部 6,672"


def test_switch_slave_keeps_selected_key(win):
    i = row_of(win, "&取消")
    key = win.model.rows[i].key
    win.select_row(i)
    win.set_pair("Chinese.lang", "Japanese.lang")  # 會詢問是否匯入，ask 預設回答「是」
    assert win.slave_name == "Japanese.lang"
    assert win.model.rows[win.current_row()].key == key


def test_edit_save_and_deploy(win, env):
    root, installed = env
    i = row_of(win, "&取消")
    win.model.setData(win.model.index(i, COL_SLAVE), "&取消X")
    assert win.save()
    assert win.model.modified_count() == 0
    saved = langfile.load(root / "lang" / "Taiwan.lang")
    assert any(e.target[Field.CAPTION] == ["&取消X"] for e in saved.entries)
    win.deploy()
    assert (installed / "Taiwan.lang").read_bytes() == (root / "lang" / "Taiwan.lang").read_bytes()


def test_save_blocked_by_placeholder_error(win, env):
    root, _ = env
    before = (root / "lang" / "Taiwan.lang").read_bytes()
    i = next(i for i in range(win.model.rowCount()) if "%1" in (win.model.slave_text(i) or ""))
    win.model.request_edit([(i, win.model.slave_text(i).replace("%1", ""))], "測試")
    assert not win.save()
    assert (root / "lang" / "Taiwan.lang").read_bytes() == before


def test_notepad_edit_is_reloaded_and_marked(win, env):
    root, _ = env
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    win.poll_txt()
    i = row_of(win, "&取消N")
    assert Status.MODIFIED in win.model.status[i]


def test_conflict_keeps_table_when_user_says_no(win, env):
    root, _ = env
    i = row_of(win, "定義")
    win.model.request_edit([(i, "表格改")], "測試")
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    win.answers.append(QMessageBox.No)
    win.poll_txt()
    assert win.model.slave_text(i) == "表格改"
    assert "表格改" in txt.read_text(encoding="utf-8-sig")


def test_asks_for_plsql_dir_when_missing(qtbot, env, monkeypatch):
    root, installed = env
    (root / "settings.json").write_text(json.dumps({"plsql_lang_dir": str(root / "沒有這個目錄")}), encoding="utf-8")
    monkeypatch.setattr("pllangstudio.ui.main_window.QFileDialog.getExistingDirectory", lambda *a, **k: str(installed))
    w = MainWindow(root, info=lambda *a, **k: None, ask=lambda *a, **k: QMessageBox.Yes)
    qtbot.addWidget(w)
    assert w.ws.installed_dir == installed
    assert w.model.rowCount() == 6672


def test_apply_edits_rejects_multiline_in_single_line_row(qtbot, env):
    root, _ = env
    calls = []
    w = MainWindow(root, elevate_fn=lambda s, d: False,
                   info=lambda *a, **k: calls.append((a, k)), ask=lambda *a, **k: QMessageBox.Yes)
    qtbot.addWidget(w)
    i = row_of(w, "&取消")
    before = w.model.slave_text(i)
    assert w.apply_edits([(i, "a\nb")], "測試") is False
    assert len(calls) == 1 and calls[0][1].get("error") is True
    assert w.undo_stack.count() == 0
    assert w.model.slave_text(i) == before


def _edit_cancel_row(win):
    i = row_of(win, "&取消")
    win.model.setData(win.model.index(i, COL_SLAVE), "&取消X")
    assert win.model.modified_count() == 1
    return i


def test_master_change_asks_before_discarding_edits(win):
    win.ws.import_lang("Japanese.lang")  # 已匯入，才不會被「是否匯入」的詢問擋下來
    i = _edit_cancel_row(win)
    win.answers.append(QMessageBox.No)
    win.set_pair("Japanese.lang", "Taiwan.lang")
    assert win.master_name == "Chinese.lang"
    assert win.model.modified_count() == 1 and win.model.slave_text(i) == "&取消X"


def test_slave_change_asks_before_discarding_edits(win):
    i = _edit_cancel_row(win)
    win.answers.append(QMessageBox.No)
    win.set_pair("Chinese.lang", "Japanese.lang")
    assert win.slave_name == "Taiwan.lang"
    assert win.model.modified_count() == 1 and win.model.slave_text(i) == "&取消X"


def test_close_asks_when_edits_pending(win):
    _edit_cancel_row(win)
    win.answers.append(QMessageBox.No)
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()
    win.answers.append(QMessageBox.Yes)
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()


def _open(qtbot, root, calls=None):
    w = MainWindow(root, elevate_fn=lambda s, d: False,
                   info=(lambda *a, **k: calls.append((a, k))) if calls is not None else (lambda *a, **k: None),
                   ask=lambda *a, **k: QMessageBox.Yes)
    qtbot.addWidget(w)
    return w


def test_txt_edited_while_closed_is_loaded_not_overwritten(qtbot, env):
    root, _ = env
    first = _open(qtbot, root)
    first.close()
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    calls = []
    w = _open(qtbot, root, calls)
    i = row_of(w, "&取消N")
    assert Status.MODIFIED in w.model.status[i]
    assert "&取消N" in txt.read_text(encoding="utf-8-sig")
    assert any(a[0] == "已載入記事本的修改" for a, _ in calls)


def test_malformed_txt_at_open_is_backed_up_and_replaced(qtbot, env):
    root, _ = env
    first = _open(qtbot, root)
    first.close()
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(b"||bad")
    calls = []
    w = _open(qtbot, root, calls)
    assert w.model.rowCount() == 6672 and w.model.modified_count() == 0
    assert [b.read_bytes() for b in (root / "backup").glob("Taiwan_*.txt")] == [b"||bad"]
    assert txt.read_text(encoding="utf-8-sig").startswith(":Taiwan")
    assert any(k.get("error") is True and "backup" in a[1] for a, k in calls)


@pytest.mark.parametrize("garbage", [b"garbage", b""])
def test_garbage_txt_at_open_never_reaches_slave(qtbot, env, garbage):
    """亂碼或空白的 .txt 不能變成副語系，否則存檔會把語言檔蓋成空檔。"""
    root, _ = env
    _open(qtbot, root).close()
    lang_before = (root / "lang" / "Taiwan.lang").read_bytes()
    (root / "txt" / "Taiwan.txt").write_bytes(garbage)
    calls = []
    w = _open(qtbot, root, calls)
    assert w.model.rowCount() == 6672
    assert all(r.s_index is not None for r in w.model.rows)
    assert any(k.get("error") is True for _a, k in calls)
    assert w.save()
    assert (root / "lang" / "Taiwan.lang").read_bytes() == lang_before


def test_reimport_shows_installed_text(win, env):
    root, installed = env
    lf = langfile.load(installed / "Taiwan.lang")
    lf.set_target(0, Field.CAPTION, ["外部新標題"])
    langfile.save(installed / "Taiwan.lang", lf)
    win.import_lang("Taiwan.lang")
    assert any(win.model.slave_text(i) == "外部新標題" for i in range(win.model.rowCount()))


def test_save_failure_is_reported(qtbot, env, monkeypatch):
    root, _ = env
    calls = []
    w = _open(qtbot, root, calls)

    def boom(*a, **k):
        raise OSError("磁碟已滿")

    monkeypatch.setattr(w.ws, "save", boom)
    assert w.save() is False
    assert calls and calls[-1][1].get("error") is True and "磁碟已滿" in calls[-1][0][1]


def test_poll_txt_skipped_while_busy(win, env):
    root, _ = env
    txt = root / "txt" / "Taiwan.txt"
    txt.write_bytes(txt.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    win._busy = 1
    win.poll_txt()
    assert win.model.modified_count() == 0
    win._busy = 0
    win.poll_txt()
    assert win.model.modified_count() == 1
