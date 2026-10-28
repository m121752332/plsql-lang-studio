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


@pytest.mark.parametrize("mode, c", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_border_and_accent_roles_follow_theme(manager, mode, c):
    """外框、分隔線用的立體色與強調色要由主題的按鈕色推導，不能沿用作業系統的值。"""
    from PySide6.QtGui import QColor
    manager.set_mode(mode)
    p = QApplication.instance().palette()
    derived = QPalette(QColor(c.palette[QPalette.Button]), QColor(c.palette[QPalette.Window]))
    for role in (QPalette.Light, QPalette.Midlight, QPalette.Mid, QPalette.Dark, QPalette.Shadow):
        assert p.color(role) == derived.color(role), role
    assert p.color(QPalette.Accent).name() == c.palette[QPalette.Highlight]


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


def _luminance(hex_color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_dark_text_readable_on_every_background():
    c = theme.DARK
    for bg in (*c.status.values(), *c.group, c.diff_removed, c.diff_added):
        assert _contrast(c.palette[QPalette.Text], bg) >= 4.5, bg


def test_deleted_manager_ignores_system_change(qtbot, tmp_path, monkeypatch):
    """視窗關閉、主題管理器被刪除後，系統切換深淺色不能出錯。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance()
    m = theme.ThemeManager(app)
    m.deleteLater()
    qtbot.wait(10)
    app.styleHints().colorSchemeChanged.emit(app.styleHints().colorScheme())
