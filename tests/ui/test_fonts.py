import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.ui import fonts


@pytest.fixture
def manager(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance()
    original = QFont(app.font())
    m = fonts.FontManager(app)
    yield m
    app.setFont(original)  # 不影響其他測試


def test_default_keeps_system_font(manager):
    assert manager.size() == manager.default_size and appconfig.font_size() == 0


def test_set_font_applies_and_remembers(manager):
    manager.set_font("Arial", 14)
    font = QApplication.instance().font()
    assert font.family() == "Arial" and font.pointSize() == 14
    assert (appconfig.font_family(), appconfig.font_size()) == ("Arial", 14)


def test_empty_family_keeps_default_family(manager):
    family = QApplication.instance().font().family()
    manager.set_font("", 12)
    assert QApplication.instance().font().family() == family and manager.size() == 12


def test_step_and_reset(manager):
    base = manager.size()
    manager.step(2)
    assert manager.size() == base + 2
    manager.reset()
    assert manager.size() == base and (appconfig.font_family(), appconfig.font_size()) == ("", 0)


def test_size_is_clamped(manager):
    manager.set_font("", 999)
    assert manager.size() == fonts.MAX_SIZE
    manager.step(-999)
    assert manager.size() == fonts.MIN_SIZE


def test_saved_font_restored_on_start(manager):
    appconfig.remember_font("Arial", 13)
    fonts.FontManager(QApplication.instance())
    assert QApplication.instance().font().pointSize() == 13


def test_invalid_saved_values_fall_back_to_default(manager):
    appconfig._update(font_family=123, font_size="大")
    assert (appconfig.font_family(), appconfig.font_size()) == ("", 0)
    fonts.FontManager(QApplication.instance())
    assert QApplication.instance().font().pointSize() == manager.default_size


def test_changed_signal_emitted(manager, qtbot):
    with qtbot.waitSignal(manager.changed):
        manager.step(1)
