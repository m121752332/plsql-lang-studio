import sys

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QDialog

from pllangstudio.ui import help_launcher
from pllangstudio.ui.help_launcher import HelpLauncher, install_help

# 假的說明程式：第一行記命令列參數，之後把 stdin 收到的每一行照抄
FAKE = """
import pathlib, sys
out = pathlib.Path(sys.argv[1])
out.write_text(" ".join(sys.argv[2:]) + "\\n", encoding="utf-8")
for line in sys.stdin:
    with out.open("a", encoding="utf-8") as f:
        f.write(line)
"""


class FakeTheme(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.dark = False

    def is_dark(self):
        return self.dark


@pytest.fixture
def fake(tmp_path, qtbot):
    script = tmp_path / "fake_help.py"
    script.write_text(FAKE, encoding="utf-8")
    out = tmp_path / "out.txt"
    theme = FakeTheme()
    opened = []
    launcher = HelpLauncher(theme, program=[sys.executable, str(script), str(out)], open_url=opened.append)
    launcher.out, launcher.fake_theme, launcher.opened = out, theme, opened
    yield launcher
    launcher.close()


def lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_first_show_starts_program_with_topic_and_theme(fake, qtbot):
    fake.show("glossary")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--listen --topic glossary --theme light"], timeout=10000)
    assert fake.running()


def test_second_show_sends_command_instead_of_restarting(fake, qtbot):
    fake.show(None)
    qtbot.waitUntil(lambda: bool(lines(fake.out)), timeout=10000)
    fake.fake_theme.dark = True
    fake.show("replace")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--listen --topic - --theme light", "show replace dark"],
                    timeout=10000)


def test_theme_change_sent_only_while_running(fake, qtbot):
    fake.fake_theme.changed.emit()  # 還沒啟動，不應有任何動作
    assert not fake.running()
    fake.show(None)
    qtbot.waitUntil(lambda: bool(lines(fake.out)), timeout=10000)
    fake.fake_theme.dark = True
    fake.fake_theme.changed.emit()
    qtbot.waitUntil(lambda: lines(fake.out)[1:] == ["theme dark"], timeout=10000)


def test_unknown_topic_starts_at_top(fake, qtbot):
    fake.show("nope")
    qtbot.waitUntil(lambda: lines(fake.out) == ["--listen --topic - --theme light"], timeout=10000)


def test_close_ends_program(fake, qtbot):
    fake.show(None)
    qtbot.waitUntil(lambda: bool(lines(fake.out)), timeout=10000)
    fake.close()
    assert not fake.running()


def test_without_program_opens_system_browser(qtbot):
    opened = []
    launcher = HelpLauncher(FakeTheme(), program=None, open_url=opened.append)
    launcher.show("glossary")
    assert len(opened) == 1
    url = opened[0].toString()
    assert url.startswith("file:///") and url.endswith("index.html?theme=light#glossary")


def test_start_failure_falls_back_to_browser(qtbot, tmp_path, events_db):
    opened = []
    launcher = HelpLauncher(FakeTheme(), program=[str(tmp_path / "missing.exe")], open_url=opened.append)
    launcher.show("faq")
    assert len(opened) == 1 and opened[0].toString().endswith("#faq")
    assert not launcher.running()


def test_default_program_from_source_runs_module(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert help_launcher.default_program() == [sys.executable, "-m", "pllangstudio.helpviewer"]


def test_default_program_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PLLangStudio.exe"))
    assert help_launcher.default_program() is None
    exe = tmp_path / "PLLangHelp" / "PLLangHelp.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    assert help_launcher.default_program() == [str(exe)]


def test_install_help_adds_f1_shortcut(qtbot):
    dlg = QDialog()
    qtbot.addWidget(dlg)
    shown = []
    sc = install_help(dlg, "glossary", shown.append)
    assert isinstance(sc, QShortcut) and sc.key().toString() == "F1"
    sc.activated.emit()
    assert shown == ["glossary"]
