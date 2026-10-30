import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from pllangstudio import resources
from pllangstudio.core.helpdoc import Command
from pllangstudio.helpviewer import window
from pllangstudio.helpviewer.window import HelpPage, HelpWindow, StdinBridge, chromium_flags

INDEX = resources.path("help/index.html")


def js(view, qtbot, code):
    box = []
    view.page().runJavaScript(code, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=5000)
    return box[0]


@pytest.fixture
def viewer(qtbot):
    w = HelpWindow(INDEX, "glossary", "dark")
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.ready, timeout=20000)
    return w


def test_opens_topic_with_theme(viewer, qtbot):
    assert js(viewer, qtbot, "location.hash") == "#glossary"
    assert js(viewer, qtbot, "document.documentElement.dataset.theme") == "dark"


def test_show_command_switches_topic_and_theme(viewer, qtbot):
    viewer.apply(Command("show", "light", "replace"))
    assert (viewer.topic, viewer.theme) == ("replace", "light")
    qtbot.waitUntil(lambda: js(viewer, qtbot, "location.hash") == "#replace", timeout=5000)
    assert js(viewer, qtbot, "document.documentElement.dataset.theme") == "light"


def test_show_without_topic_goes_to_top(viewer, qtbot):
    viewer.apply(Command("show", "dark", None))
    qtbot.waitUntil(lambda: js(viewer, qtbot, "location.hash") == "", timeout=5000)


def test_theme_command_keeps_topic(viewer, qtbot):
    viewer.apply(Command("theme", "light"))
    qtbot.waitUntil(lambda: js(viewer, qtbot, "document.documentElement.dataset.theme") == "light",
                    timeout=5000)
    assert js(viewer, qtbot, "location.hash") == "#glossary"


def theme_of(viewer, qtbot):
    return js(viewer, qtbot, "document.documentElement.dataset.theme")


def test_theme_button_toggles_only_help_page(viewer, qtbot):
    js(viewer, qtbot, "document.getElementById('theme-toggle').click(), true")
    assert theme_of(viewer, qtbot) == "light"
    js(viewer, qtbot, "document.getElementById('theme-toggle').click(), true")
    assert theme_of(viewer, qtbot) == "dark"


def test_manual_theme_survives_show_command(viewer, qtbot):
    """在說明視窗手動切換後，從主程式再按 F1 不會被蓋回主程式的主題。"""
    js(viewer, qtbot, "document.getElementById('theme-toggle').click(), true")
    viewer.apply(Command("show", "dark", "replace"))
    qtbot.waitUntil(lambda: js(viewer, qtbot, "location.hash") == "#replace", timeout=5000)
    assert theme_of(viewer, qtbot) == "light"


def test_main_theme_change_overrides_manual_theme(viewer, qtbot):
    js(viewer, qtbot, "document.getElementById('theme-toggle').click(), true")
    viewer.apply(Command("theme", "dark"))
    qtbot.waitUntil(lambda: theme_of(viewer, qtbot) == "dark", timeout=5000)


def test_search_filters_sections(viewer, qtbot):
    js(viewer, qtbot, "(() => { const s = document.getElementById('search'); s.value = 'UAC';"
                      "s.dispatchEvent(new Event('input')); return true; })()")
    # 陣列傳回 Python 會變成空字串，所以先在網頁端接成字串
    visible = js(viewer, qtbot,
                 "[...document.querySelectorAll('main > section:not(.hidden)')].map(s => s.id).join(',')")
    assert "save-deploy" in visible.split(",") and "glossary" not in visible.split(",")
    assert js(viewer, qtbot, "document.querySelectorAll('mark').length") > 0


def test_chromium_flags_pin_scale_to_qt():
    """Windows「文字大小」不是 100% 時，Chromium 會用不同於 Qt 的縮放繪製，畫面被拉伸而掉列（破圖）。"""
    flags = chromium_flags("", 1.25)
    assert "--force-device-scale-factor=1.25" in flags.split()
    assert "--disable-features=CalculateNativeWinOcclusion" in flags.split()


def test_chromium_flags_keep_existing():
    assert chromium_flags("--foo", 1.0).split()[0] == "--foo"


@pytest.mark.parametrize("value, expected", [(107, 1.07), (100, 1.0), (None, 1.0)])
def test_text_scale_factor(monkeypatch, value, expected):
    def fake_read():
        if value is None:
            raise OSError("沒有這個設定")
        return value
    monkeypatch.setattr(window, "_read_text_scale", fake_read)
    assert window.text_scale_factor() == pytest.approx(expected)


def test_zoom_applies_to_page(qtbot):
    w = HelpWindow(INDEX, None, "light", zoom=1.07)
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.ready, timeout=20000)
    assert w.zoomFactor() == pytest.approx(1.07)


def test_external_links_open_in_system_browser(qtbot):
    opened = []
    page = HelpPage(open_url=opened.append)
    ext = QUrl("https://github.com/m121752332/plsql-lang-studio")
    assert not page.acceptNavigationRequest(ext, QWebEnginePage.NavigationTypeLinkClicked, True)
    assert opened == [ext]
    assert page.acceptNavigationRequest(QUrl.fromLocalFile(str(INDEX)),
                                        QWebEnginePage.NavigationTypeLinkClicked, True)


def test_stdin_bridge_emits_lines_then_closed(qtbot):
    bridge = StdinBridge()
    lines = []
    bridge.received.connect(lines.append)
    r, w = os.pipe()
    with qtbot.waitSignal(bridge.closed, timeout=5000):
        bridge.start(r)
        os.write(w, "show glossary dark\nthe".encode("utf-8"))  # 一行分兩次寄達也要能接起來
        os.write(w, "me light\n".encode("utf-8"))
        os.close(w)
    assert lines == ["show glossary dark", "theme light"]


def test_exit_while_reading_stdin_does_not_crash():
    """使用者先關掉說明視窗時，讀 stdin 的執行緒還卡著，程式也要正常結束（不可 Fatal Python error）。"""
    script = ("import sys, time\n"
              "from pllangstudio.helpviewer.window import StdinBridge\n"
              "StdinBridge().start(sys.stdin.fileno())\n"
              "time.sleep(0.5)\n")
    proc = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        err = proc.stderr.read()  # stdin 保持開著，子行程要自己結束
        assert proc.wait(timeout=30) == 0, err.decode("utf-8", "replace")
    finally:
        proc.stdin.close()
