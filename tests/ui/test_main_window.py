import json
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

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


def menu_texts(menu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_menu_bar_has_file_edit_about(win):
    menus = {a.text(): a.menu() for a in win.menuBar().actions()}
    assert list(menus) == ["檔案(&F)", "編輯(&E)", "關於(&A)"]
    assert "💾 加密存檔" in menu_texts(menus["檔案(&F)"]) and "結束" in menu_texts(menus["檔案(&F)"])
    edit = menu_texts(menus["編輯(&E)"])
    assert {"復原", "重做", "🔍 尋找取代…", "主題"} <= set(edit)
    theme_menu = next(a.menu() for a in menus["編輯(&E)"].actions() if a.text() == "主題")
    assert menu_texts(theme_menu) == ["亮色", "暗色", "跟隨系統"]
    assert menu_texts(menus["關於(&A)"]) == ["使用說明", "關於 PLLangStudio"]


def test_shortcuts_are_registered_once(win):
    from collections import Counter
    shortcuts = Counter(s.toString() for a in win.findChildren(type(win.act["save"])) for s in a.shortcuts())
    assert shortcuts["Ctrl+S"] == 1 and shortcuts["Ctrl+F"] == 1 and shortcuts["F3"] == 1


def test_file_panel_workspace_above_installed(win):
    from PySide6.QtWidgets import QLabel
    top, bottom = win.files.widget(0), win.files.widget(1)
    assert win.files.workspace in top.findChildren(type(win.files.workspace))
    assert win.files.installed in bottom.findChildren(type(win.files.installed))
    assert top.findChild(QLabel).text() == "<b>工作區</b>"
    roles = {win.files.workspace.topLevelItem(k).text(0): win.files.workspace.topLevelItem(k).text(1)
             for k in range(win.files.workspace.topLevelItemCount())}
    assert roles == {"Chinese.lang": "🔒 主語系", "Taiwan.lang": "副語系"}


def test_theme_switch_recolors_table(win):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from pllangstudio.ui import theme
    i = row_of(win, "定義")  # 主語系「定义」≠ 副語系「定義」→ 不同（黃底）
    cell = win.model.index(i, COL_SLAVE)
    win.act["theme_dark"].trigger()
    assert win.model.data(cell, Qt.BackgroundRole).color().name() == theme.DARK.status[Status.DIFFERENT]
    assert QApplication.instance().palette().color(QPalette.Window).name() == theme.DARK.palette[QPalette.Window]
    win.act["theme_light"].trigger()
    assert win.model.data(cell, Qt.BackgroundRole).color().name() == theme.LIGHT.status[Status.DIFFERENT]
    assert win.act["theme_light"].isChecked() and not win.act["theme_dark"].isChecked()


def test_no_master_slave_wording_in_ui(win):
    from PySide6.QtWidgets import QAbstractButton, QLabel
    texts = [a.text() for a in win.findChildren(QAction)]
    texts += [w.text() for w in win.findChildren(QLabel)] + [w.text() for w in win.findChildren(QAbstractButton)]
    texts += [win.model.headerData(c, Qt.Horizontal) for c in range(win.model.columnCount())]
    texts += [win.scope.itemText(k) for k in range(win.scope.count())]
    assert not [t for t in texts if t and ("MASTER" in t or "SLAVE" in t)]


def disabled_items(combo):
    return [combo.itemText(i) for i in range(combo.count()) if not combo.model().item(i).isEnabled()]


def test_pair_rejects_same_file(win):
    shown = []
    win.info = lambda *a, **k: shown.append(a)
    win.set_pair("Taiwan.lang", "Taiwan.lang")
    assert (win.master_name, win.slave_name) == ("Chinese.lang", "Taiwan.lang") and shown


def test_combos_disable_the_other_side(win):
    assert disabled_items(win.master_combo) == ["Taiwan.lang"]
    assert disabled_items(win.slave_combo) == ["Chinese.lang"]


def test_startup_with_identical_pair_picks_another_file(qtbot, env):
    root, _ = env
    path = root / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["master"] = data["slave"] = "Taiwan.lang"
    path.write_text(json.dumps(data), encoding="utf-8")
    w = MainWindow(root, elevate_fn=lambda s, d: False, info=lambda *a, **k: None, ask=lambda *a, **k: QMessageBox.Yes)
    qtbot.addWidget(w)
    assert w.master_name and w.slave_name and w.master_name != w.slave_name


def test_workspace_list_marks_master_as_locked(win):
    items = {win.files.workspace.topLevelItem(i).text(0): win.files.workspace.topLevelItem(i)
             for i in range(win.files.workspace.topLevelItemCount())}
    assert items["Chinese.lang"].text(1) == "🔒 主語系" and "唯讀" in items["Chinese.lang"].toolTip(1)
    assert items["Taiwan.lang"].text(1) == "副語系" and "🔒" not in items["Taiwan.lang"].text(1)


def test_remove_lang_from_workspace(win, env):
    root, installed = env
    win.set_pair("Chinese.lang", "Japanese.lang")  # 會匯入 Japanese
    win.set_pair("Chinese.lang", "Taiwan.lang")
    assert (root / "lang" / "Japanese.lang").exists()
    win.remove_lang("Japanese.lang")
    assert not (root / "lang" / "Japanese.lang").exists() and (installed / "Japanese.lang").exists()
    names = [win.files.workspace.topLevelItem(i).text(0) for i in range(win.files.workspace.topLevelItemCount())]
    assert "Japanese.lang" not in names and "Japanese.lang" not in [win.slave_combo.itemText(i) for i in range(win.slave_combo.count())]


def test_remove_lang_declined_keeps_file(win, env):
    root, _ = env
    win.set_pair("Chinese.lang", "Japanese.lang")
    win.set_pair("Chinese.lang", "Taiwan.lang")
    win.answers.append(QMessageBox.No)
    win.remove_lang("Japanese.lang")
    assert (root / "lang" / "Japanese.lang").exists()


def test_remove_lang_in_use_is_refused(win, env):
    root, _ = env
    shown = []
    win.info = lambda *a, **k: shown.append(a)
    for name in ("Chinese.lang", "Taiwan.lang"):  # 主語系與副語系都不能移除
        win.remove_lang(name)
        assert (root / "lang" / name).exists()
    assert len(shown) == 2


def test_row_height_follows_font(win):
    base = win.table.verticalHeader().defaultSectionSize()
    try:
        win.fonts.set_font("", 28)
        assert win.table.verticalHeader().defaultSectionSize() > base
    finally:
        win.fonts.reset()
    assert win.table.verticalHeader().defaultSectionSize() == base
