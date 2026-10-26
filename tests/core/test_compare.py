import pytest

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import compare, langfile
from pllangstudio.core.compare import Status
from pllangstudio.core.langfile import Field

pytestmark = needs_lang_dir


@pytest.fixture(scope="module")
def zh():
    return langfile.load(LANG_DIR / "Chinese.lang")


@pytest.fixture(scope="module")
def tw():
    return langfile.load(LANG_DIR / "Taiwan.lang")


@pytest.fixture(scope="module")
def rows(zh, tw):
    return compare.align(zh, tw)


def test_row_counts(rows):
    assert len(rows) == 6672
    assert sum(r.item is None for r in rows) == 49
    assert all(r.m_index is not None and r.s_index is not None for r in rows)


def test_master_and_slave_share_key(rows, zh, tw):
    for r in rows:
        assert zh.entries[r.m_index].key == tw.entries[r.s_index].key == r.key


def test_source_comes_from_master(rows, zh):
    r = next(r for r in rows if r.key[-2:] == ("CancelBtn", "Button") and r.key[0] == "AAMacrosEditDlg")
    assert r.source == "&Cancel" and r.field is Field.CAPTION and r.item == 0
    assert compare.get_text(zh, r.m_index, r.field, r.item) == "&取消"


def test_hungarian_one_sided_rows(zh):
    hu = langfile.load(LANG_DIR / "Hungarian.lang")
    rows = compare.align(zh, hu)
    one = [r for r in rows if r.m_index is None or r.s_index is None]
    assert one and all(compare.row_status(r, zh, hu, None)[0] >= {Status.ONE_SIDED} for r in one)
    assert sum(r.s_index is None for r in rows) > 0  # 只有 MASTER 有的筆也要出現


def test_status_different_and_modified(rows, zh, tw):
    r = next(r for r in rows if compare.get_text(zh, r.m_index, r.field, r.item) == "定义")
    status, _ = compare.row_status(r, zh, tw, original="定義")
    assert status == {Status.DIFFERENT}
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    compare.set_text(lf, r.s_index, r.field, r.item, "定義X")
    status, _ = compare.row_status(r, zh, lf, original="定義")
    assert Status.MODIFIED in status


def test_status_simplified(rows, zh):
    # 自己在副本放一個殘留簡體字，不依賴使用者目前 Taiwan.lang 的內容
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    r = next(r for r in rows if r.source == "Expires in %1 days")
    compare.set_text(lf, r.s_index, r.field, r.item, "%1 天后過期")
    status, _ = compare.row_status(r, zh, lf, None, ["游標", "批准"])
    assert {Status.SIMPLIFIED, Status.WARNING} <= status


def test_set_text_multiline_row(rows, tw):
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    r = next(r for r in rows if r.item is None)
    compare.set_text(lf, r.s_index, r.field, r.item, "甲\n乙\n丙")
    assert lf.entries[r.s_index].target[r.field] == ["甲", "乙", "丙"]
    with pytest.raises(ValueError):
        single = next(x for x in rows if x.item is not None)
        compare.set_text(lf, single.s_index, single.field, single.item, "a\nb")


def test_count_differences(zh, tw):
    assert compare.count_differences(tw, tw) == 0
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    lf.set_target(0, Field.CAPTION, ["改"])
    assert compare.count_differences(lf, tw) == 1
