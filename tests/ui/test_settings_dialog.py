import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from pllangstudio import appconfig, eventlog
from pllangstudio.ui.fonts import FontManager
from pllangstudio.ui.settings_dialog import SettingsDialog
from pllangstudio.ui.theme import ThemeManager


@pytest.fixture
def dialog(qtbot, tmp_path, monkeypatch, events_db):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance()
    original = QFont(app.font())
    theme = ThemeManager(app, system_dark=lambda: False)
    fonts = FontManager(app)
    opened = []
    dlg = SettingsDialog(theme, fonts, lambda: opened.append(True))
    dlg.opened, dlg.theme, dlg.fonts = opened, theme, fonts
    qtbot.addWidget(dlg)
    yield dlg
    theme.set_mode("light")  # 不影響其他測試
    app.setFont(original)


def test_pages(dialog):
    pages = [dialog.pages_list.item(i).text() for i in range(dialog.pages_list.count())]
    assert pages == ["外觀", "紀錄事件"]


def test_retention_defaults_shown(dialog):
    assert {g: b.value() for g, b in dialog.log_page.days.items()} == {"info": 90, "warning": 90, "error": 30}


def test_apply_saves_retention_and_logs(dialog):
    dialog.log_page.days["error"].setValue(7)
    dialog.apply()
    assert appconfig.log_retention() == {"info": 90, "warning": 90, "error": 7}
    assert eventlog.query(keyword="保留天數")[0].category == "配置"


def test_cancel_saves_nothing(dialog):
    dialog.log_page.days["info"].setValue(5)
    dialog.appearance.theme_buttons["dark"].setChecked(True)
    dialog.reject()
    assert appconfig.log_retention()["info"] == 90 and dialog.theme.mode == "system"


def test_ok_applies_theme_and_font(dialog):
    dialog.appearance.theme_buttons["dark"].setChecked(True)
    dialog.appearance.size.setValue(15)
    dialog.accept()
    assert dialog.theme.mode == "dark" and appconfig.theme_mode() == "dark"
    assert dialog.fonts.size() == 15 and appconfig.font_size() == 15


def test_unchanged_font_keeps_system_default(dialog):
    dialog.accept()
    assert appconfig.font_size() == 0


def test_reset_font_button(dialog):
    dialog.fonts.set_font("Arial", 18)
    dialog.appearance.reset_button.click()
    assert dialog.fonts.size() == dialog.fonts.default_size and appconfig.font_size() == 0
    assert dialog.appearance.size.value() == dialog.fonts.default_size


def test_stats_and_purge_now(dialog):
    eventlog.info("程式", "啟動")
    dialog.log_page.refresh_stats()
    assert "1 筆" in dialog.log_page.stats.text()
    dialog.log_page.purge_now()  # 沒有過期的，不會刪
    assert len(eventlog.query()) >= 1


def test_open_viewer_closes_dialog_first(dialog):
    dialog.show()
    dialog.log_page.viewer_button.click()
    assert dialog.opened == [True] and not dialog.isVisible()


def answer(dialog, reply):
    """換掉確認對話框，記下問了什麼。"""
    asked = []
    dialog.log_page.ask = lambda title, text: asked.append(text) or reply
    return asked


def backdate(db, days):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE events SET time = ?",
                 ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds"),))
    conn.commit()
    conn.close()


def test_summary_shown(dialog):
    eventlog.warning("存檔", "有警告")
    dialog.log_page.refresh_stats()
    text = dialog.log_page.stats.text()
    assert "共 1 筆" in text and "警告 1" in text and "最舊" in text


def test_delete_old_asks_then_keeps_ids(dialog, events_db):
    first = eventlog.info("測試", "舊的")
    backdate(events_db, 40)
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.delete_days.setValue(30)
    dialog.log_page.delete_old()
    assert "1 筆" in asked[0]
    [e] = eventlog.query()
    assert e.id == first + 1 and "手動刪除 30 天前的紀錄 1 筆" in e.message
    assert "已刪除 1 筆" in dialog.log_page.message.text()


def test_delete_old_cancelled(dialog, events_db):
    eventlog.info("測試", "舊的")
    backdate(events_db, 40)
    answer(dialog, QMessageBox.No)
    dialog.log_page.delete_old()
    assert len(eventlog.query()) == 1


def test_delete_old_nothing_to_delete(dialog):
    eventlog.info("測試", "新的")
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.delete_old()
    assert asked == [] and "沒有" in dialog.log_page.message.text()


def test_reset_from_page(dialog, events_db):
    eventlog.info("測試", "一")
    eventlog.info("測試", "二")
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.reset_log()
    assert "2 筆" in asked[0] and "備份" in asked[0]
    [e] = eventlog.query()
    assert e.id == 1 and "已初始化" in e.message
    assert list((events_db.parent / "backup").glob("events-*.zip"))
    assert "共 1 筆" in dialog.log_page.stats.text()


def test_reset_cancelled(dialog):
    eventlog.info("測試", "一")
    answer(dialog, QMessageBox.No)
    dialog.log_page.reset_log()
    assert len(eventlog.query()) == 1


def test_reset_failure_keeps_events(dialog, monkeypatch):
    eid = eventlog.info("測試", "要保留")
    answer(dialog, QMessageBox.Yes)
    warned = []
    dialog.log_page.warn = lambda title, text: warned.append(text)

    def boom(*_args, **_kwargs):
        raise OSError("磁碟已滿")
    monkeypatch.setattr(eventlog, "export_zip", boom)
    dialog.log_page.reset_log()
    assert eid in [e.id for e in eventlog.query()]
    assert "沒有刪除任何紀錄" in warned[0] and "磁碟已滿" in warned[0] and "事件編號" in warned[0]


def test_open_folder(dialog, events_db):
    opened = []
    dialog.log_page.open_folder = opened.append
    dialog.log_page.folder_button.click()
    assert opened == [str(events_db.parent)]
