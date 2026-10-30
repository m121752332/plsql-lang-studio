import json

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.core import validate
from pllangstudio.ui.language import LANGUAGE_NAMES, LanguageManager

tr = QCoreApplication.translate


@pytest.fixture
def manager(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    m = LanguageManager(QApplication.instance())
    yield m
    m.set_language("zh_TW")  # 翻譯器是整個程式共用的，不能影響其他測試


def test_default_is_traditional_chinese_source_text(manager):
    assert manager.code == "zh_TW" and appconfig.language() == "zh_TW"
    assert tr("MainWindow", "結束") == "結束"
    assert tr("QPlatformTheme", "OK") == "確定"  # Qt 自己的標準按鈕也是繁體中文


@pytest.mark.parametrize("code, text", [("zh_CN", "结束"), ("en", "Exit"), ("ja", "終了")])
def test_switch_language_and_remember(manager, code, text):
    manager.set_language(code)
    assert tr("MainWindow", "結束") == text
    assert appconfig.language() == code


def test_core_messages_follow_language(manager):
    issue = next(x for x in validate.check("Open", "开启") if x.code == "SIMPLIFIED")
    manager.set_language("en")
    assert issue.message == "Leftover Simplified characters: 开启"
    manager.set_language("zh_TW")
    assert issue.message == "殘留簡體字：开启"
    assert tr("MainWindow", "結束") == "結束"


def test_saved_language_is_used_at_startup(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    appconfig.remember_language("ja")
    m = LanguageManager(QApplication.instance())
    try:
        assert m.code == "ja" and tr("MainWindow", "結束") == "終了"
    finally:
        m.set_language("zh_TW")


def test_unknown_saved_language_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    (tmp_path / "appdata" / "PLLangStudio").mkdir(parents=True)
    (tmp_path / "appdata" / "PLLangStudio" / "app.json").write_text(json.dumps({"language": "xx"}), encoding="utf-8")
    assert appconfig.language() == "zh_TW"


def test_unknown_language_rejected(manager):
    with pytest.raises(ValueError):
        manager.set_language("xx")


def test_language_names_cover_config_choices():
    assert tuple(LANGUAGE_NAMES) == appconfig.LANGUAGES


def test_event_viewer_retranslates(manager, qtbot, events_db):
    from pllangstudio.ui.event_viewer import EventViewer
    v = EventViewer()
    qtbot.addWidget(v)
    manager.set_language("en")
    qtbot.waitUntil(lambda: v.windowTitle() == "Event Viewer")
    assert v.table.horizontalHeaderItem(0).text() == "No."
    assert v.period.itemText(1) == "Last 7 days" and v.level_boxes["info"].text() == "Info"
