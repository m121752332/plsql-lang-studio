from PySide6.QtCore import QAbstractAnimation, QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication, QWidget

from pllangstudio.ui.theme import DARK, LIGHT
from pllangstudio.ui.toast import KINDS, Toast, ToastHost


def make_host(qtbot) -> tuple[QWidget, ToastHost]:
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    return parent, ToastHost(parent)


def test_toast_shows_title_and_text(qtbot):
    _, host = make_host(qtbot)
    t = host.show("success", "已存檔", "Taiwan.lang")
    assert isinstance(t, Toast) and host.toasts == [t]
    assert t.title_label.text() == "已存檔" and t.text_label.text() == "Taiwan.lang"
    assert t.isVisible()


def test_toast_without_text_hides_text_label(qtbot):
    _, host = make_host(qtbot)
    t = host.show("info", "沒有需要修改的字串")
    assert t.text_label.isHidden()


def test_toast_closes_after_duration(qtbot):
    _, host = make_host(qtbot)
    host.show("info", "提示", duration=50)
    qtbot.waitUntil(lambda: not host.toasts, timeout=3000)


def test_close_button_dismisses_immediately(qtbot):
    _, host = make_host(qtbot)
    t = host.show("warning", "警告", duration=60000)
    qtbot.mouseClick(t.close_button, Qt.LeftButton)
    assert t not in host.toasts


def test_hover_pauses_countdown(qtbot):
    _, host = make_host(qtbot)
    t = host.show("info", "提示", duration=80)
    QApplication.sendEvent(t, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.wait(250)
    assert t in host.toasts  # 滑鼠停在上面時不會消失


def test_oldest_toast_removed_beyond_limit(qtbot):
    _, host = make_host(qtbot)
    shown = [host.show("info", f"第 {i} 則", duration=60000) for i in range(ToastHost.MAX + 1)]
    assert host.toasts == shown[1:]


def test_toasts_stack_in_bottom_right_corner(qtbot):
    parent, host = make_host(qtbot)
    a = host.show("info", "第一則", duration=60000)
    b = host.show("info", "第二則", duration=60000)
    qtbot.waitUntil(lambda: b.slide.state() == QAbstractAnimation.Stopped)  # 等滑入動畫結束
    for t in (a, b):
        assert parent.rect().contains(t.geometry())
        assert t.geometry().right() > parent.width() * 0.6
    assert a.geometry().bottom() < b.geometry().top()  # 新的在最下面，舊的往上推


def test_toasts_follow_parent_resize(qtbot):
    parent, host = make_host(qtbot)
    t = host.show("info", "提示", duration=60000)
    parent.resize(1200, 900)
    qtbot.waitUntil(lambda: t.geometry().bottom() > 600)
    assert parent.rect().contains(t.geometry())


def test_every_kind_has_theme_colors():
    for c in (LIGHT, DARK):
        assert set(c.toast_accent) == set(KINDS)
