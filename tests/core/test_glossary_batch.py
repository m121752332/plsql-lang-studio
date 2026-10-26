from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import batch, compare, convert, glossary, langfile
from pllangstudio.core.glossary import Rule


def test_apply_rule_respects_exceptions():
    rule = Rule("新建", "新增", ["重新建"])
    assert glossary.apply_rule("新建連線；重新建立表", rule) == "新增連線；重新建立表"


def test_apply_rule_disabled():
    assert glossary.apply_rule("新建", Rule("新建", "新增", enabled=False)) == "新建"


def test_pass_count_is_kept():
    rules = glossary.default().rules
    assert glossary.apply_rules("使用&通過計數；可以通過網路", rules) == "使用&通過計數；可以透過網路"
    assert glossary.apply_rules("[通過] 計數", rules) == "[通過] 計數"


def test_longer_rule_first():
    assert glossary.apply_rules("配置文件與配置", glossary.default().rules) == "設定檔與設定"


def test_save_and_load_roundtrip(tmp_path):
    g = glossary.default()
    glossary.save(tmp_path / "g.json", g)
    assert glossary.load(tmp_path / "g.json") == g


@needs_lang_dir
def test_default_glossary_reproduces_taiwan():
    """驗收標準 #3：s2twp(Chinese) 套用預設用語表後，每個字串都跟目前的 Taiwan.lang 相同。"""
    zh = langfile.load(LANG_DIR / "Chinese.lang")
    tw = langfile.load(LANG_DIR / "Taiwan.lang")
    rules = glossary.default().rules
    for r in compare.align(zh, tw):
        m = compare.get_text(zh, r.m_index, r.field, r.item)
        assert glossary.apply_rules(convert.s2twp(m), rules) == compare.get_text(tw, r.s_index, r.field, r.item)


@needs_lang_dir
def test_preview_functions():
    zh = langfile.load(LANG_DIR / "Chinese.lang")
    tw = langfile.load(LANG_DIR / "Taiwan.lang")
    rows = compare.align(zh, tw)
    changes = batch.preview_replace(rows, zh, tw, "巨集", "Macro")
    assert changes and all("巨集" in c.before and "Macro" in c.after for c in changes)
    assert batch.preview_rules(rows, zh, tw, glossary.default().rules) == []
    s2 = batch.preview_s2twp(rows, zh, tw)
    assert any(c.before == "偏好設定" and c.after == "首選項" for c in s2)
    regex = batch.preview_replace(rows, zh, tw, r"%(\d)", r"{\1}", regex=True)
    assert all("{" in c.after for c in regex)
