from PySide6.QtWidgets import QApplication

from pllangstudio.ui.error_box import error_box


def button(box, text):
    return next(b for b in box.buttons() if b.text() == text)


def test_copy_event_id(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", 42)
    qtbot.addWidget(box)
    button(box, "複製事件編號").click()
    assert QApplication.clipboard().text() == "#42"


def test_open_viewer_with_event_id(qtbot):
    opened = []
    box = error_box(None, "存檔失敗", "沒有存成功", 42, opened.append)
    qtbot.addWidget(box)
    button(box, "開啟事件檢視器").click()
    assert opened == [42]


def test_without_viewer_has_no_viewer_button(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", 42)
    qtbot.addWidget(box)
    assert [b.text() for b in box.buttons() if b.text() == "開啟事件檢視器"] == []


def test_without_event_id_only_ok(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", None, lambda eid: None)
    qtbot.addWidget(box)
    assert len(box.buttons()) == 1
