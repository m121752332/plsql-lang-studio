import io

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from pllangstudio import resources
from pllangstudio.core.helpdoc import Command
from pllangstudio.helpviewer.window import HelpPage, HelpWindow, StdinBridge

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


def test_search_filters_sections(viewer, qtbot):
    js(viewer, qtbot, "(() => { const s = document.getElementById('search'); s.value = 'UAC';"
                      "s.dispatchEvent(new Event('input')); return true; })()")
    # 陣列傳回 Python 會變成空字串，所以先在網頁端接成字串
    visible = js(viewer, qtbot,
                 "[...document.querySelectorAll('main > section:not(.hidden)')].map(s => s.id).join(',')")
    assert "save-deploy" in visible.split(",") and "glossary" not in visible.split(",")
    assert js(viewer, qtbot, "document.querySelectorAll('mark').length") > 0


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
    with qtbot.waitSignal(bridge.closed, timeout=5000):
        bridge.start(io.BytesIO("show glossary dark\ntheme light\n".encode("utf-8")))
    assert lines == ["show glossary dark\n", "theme light\n"]
