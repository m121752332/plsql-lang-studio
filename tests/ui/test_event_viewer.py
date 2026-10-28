import zipfile

import pytest
from PySide6.QtWidgets import QApplication

from pllangstudio import eventlog
from pllangstudio.ui import theme
from pllangstudio.ui.event_viewer import EventViewer


@pytest.fixture
def viewer(qtbot, events_db, tmp_path):
    eventlog.info("工作區", "開啟工作區")
    eventlog.warning("存檔", "有警告")
    try:
        raise OSError("磁碟已滿")
    except OSError as exc:
        eventlog.error("存檔", "存檔失敗", exc)
    out = tmp_path / "export.zip"
    v = EventViewer(save_path=lambda name: str(out))
    v.out = out
    qtbot.addWidget(v)
    return v


def column(v, c):
    return [v.table.item(r, c).text() for r in range(v.table.rowCount())]


def test_lists_newest_first_with_labels(viewer):
    assert column(viewer, 2) == ["錯誤", "警告", "資訊"]
    assert column(viewer, 3) == ["存檔", "存檔", "工作區"]
    assert viewer.count_label.text() == "共 3 筆"


def test_filter_by_level_and_keyword(viewer):
    viewer.level_boxes["info"].setChecked(False)
    assert column(viewer, 2) == ["錯誤", "警告"]
    viewer.search.setText("磁碟")
    assert column(viewer, 4) == ["存檔失敗"]


def test_search_by_event_id(viewer):
    eid = viewer.events[-1].id
    viewer.search.setText(f"#{eid}")
    assert column(viewer, 0) == [str(eid)]


def test_detail_shows_traceback(viewer):
    viewer.table.selectRow(0)
    assert "OSError: 磁碟已滿" in viewer.detail.toPlainText()


def test_error_rows_are_colored(viewer):
    assert viewer.table.item(0, 4).foreground().color().name() == theme.colors().event_level["error"]


def test_copy_selected(viewer):
    viewer.table.selectRow(1)
    viewer.copy_selected()
    assert QApplication.clipboard().text().startswith(f"#{viewer.events[1].id}")


def test_export_filtered(viewer):
    viewer.level_boxes["info"].setChecked(False)
    viewer.export()
    with zipfile.ZipFile(viewer.out) as z:
        text = z.read("events.txt").decode("utf-8")
        system = z.read("system.txt").decode("utf-8")
    assert "存檔失敗" in text and "開啟工作區" not in text and "Qt：" in system
    assert eventlog.query(keyword="匯出")[0].category == "事件檢視器"


def test_every_theme_has_event_colors():
    for c in (theme.LIGHT, theme.DARK):
        assert set(c.event_level) == {"warning", "error"}
