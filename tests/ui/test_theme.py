import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.core.compare import Status
from pllangstudio.ui import theme


@pytest.fixture
def manager(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    system = {"dark": False}
    m = theme.ThemeManager(QApplication.instance(), system_dark=lambda: system["dark"])
    m.system = system
    yield m
    m.set_mode("light")  # 不影響其他測試


def window_is_dark() -> bool:
    return QApplication.instance().palette().color(QPalette.Window).lightness() < 128


def test_light_and_dark_switch_palette_and_colors(manager):
    manager.set_mode("dark")
    assert window_is_dark() and theme.colors() is theme.DARK
    manager.set_mode("light")
    assert not window_is_dark() and theme.colors() is theme.LIGHT


def test_system_mode_follows_os(manager):
    manager.set_mode("system")
    assert not window_is_dark()
    manager.system["dark"] = True
    manager.on_system_changed()
    assert window_is_dark() and theme.colors() is theme.DARK


def test_system_change_ignored_when_mode_is_explicit(manager):
    manager.set_mode("light")
    manager.system["dark"] = True
    manager.on_system_changed()
    assert not window_is_dark()


def test_changed_signal_and_persistence(manager, qtbot):
    with qtbot.waitSignal(manager.changed):
        manager.set_mode("dark")
    assert appconfig.theme_mode() == "dark"
    manager.set_mode("system")
    assert appconfig.theme_mode() == "system"


def test_theme_setting_does_not_drop_workspace(manager, tmp_path):
    appconfig.remember_workspace(tmp_path / "ws")
    manager.set_mode("dark")
    assert appconfig.last_workspace() == tmp_path / "ws"
    appconfig.remember_workspace(tmp_path / "ws2")
    assert appconfig.theme_mode() == "dark"


def test_default_and_invalid_mode(manager):
    assert appconfig.theme_mode() == "system"
    with pytest.raises(ValueError):
        manager.set_mode("purple")


def test_every_highlighted_status_has_both_colors():
    for c in (theme.LIGHT, theme.DARK):
        assert set(c.status) == {Status.ERROR, Status.MODIFIED, Status.SIMPLIFIED, Status.UNTRANSLATED,
                                 Status.ONE_SIDED, Status.DIFFERENT}


def test_deleted_manager_ignores_system_change(qtbot, tmp_path, monkeypatch):
    """視窗關閉、主題管理器被刪除後，系統切換深淺色不能出錯。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance()
    m = theme.ThemeManager(app)
    m.deleteLater()
    qtbot.wait(10)
    app.styleHints().colorSchemeChanged.emit(app.styleHints().colorScheme())
