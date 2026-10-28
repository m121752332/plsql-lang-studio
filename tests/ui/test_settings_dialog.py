import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

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
