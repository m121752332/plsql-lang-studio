import os

import pytest

from langdata import LANG_DIR, LANG_FILES, needs_lang_dir
from pllangstudio.core import langcrypt, langfile
from pllangstudio.core.langfile import Field, LangFormatError

pytestmark = needs_lang_dir


@pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    plain = langcrypt.decrypt(path.read_bytes())
    assert langfile.serialize(langfile.parse(plain)) == plain


@pytest.mark.parametrize("name,count", [("Taiwan.lang", 5876), ("Chinese.lang", 5876), ("Hungarian.lang", 5695)])
def test_entry_counts(name, count):
    lf = langfile.load(LANG_DIR / name)
    assert len(lf.entries) == count
    assert len(lf.header) == 12
    assert lf.trailing_newline


def test_parses_cancel_button():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    e = next(e for e in lf.entries if e.key == ("AAMacrosEditDlg", "ButtonPanel", "CancelBtn", "Button"))
    assert e.source[Field.CAPTION] == ["&Cancel"]
    assert e.target[Field.CAPTION] == ["&取消"]


def test_english_is_identical_across_languages():
    def english(name):
        return {e.key: e.source for e in langfile.load(LANG_DIR / name).entries}
    base = english("Chinese.lang")
    for name in ["German.lang", "Japanese.lang", "Taiwan.lang"]:
        other = english(name)
        assert all(other[k] == v for k, v in base.items() if k in other)


def test_keys_are_unique():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    keys = [e.key for e in lf.entries]
    assert len(keys) == len(set(keys))


def test_set_target_changes_only_that_line():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    before = langfile.serialize(lf).split(b"\r\n")
    i = next(i for i, e in enumerate(lf.entries) if e.target[Field.CAPTION] == ["&取消"])
    lf.set_target(i, Field.CAPTION, ["&取消X"])
    after = langfile.serialize(lf).split(b"\r\n")
    diff = [k for k, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(diff) == 1
    assert after[diff[0]] == "&取消X".encode()


def test_set_target_with_more_lines_updates_flags():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    i = next(i for i, e in enumerate(lf.entries) if e.target[Field.CAPTION] == ["&取消"])
    lf.set_target(i, Field.CAPTION, ["第一行", "第二行"])
    again = langfile.parse(langfile.serialize(lf))
    assert again.entries[i].target[Field.CAPTION] == ["第一行", "第二行"]
    assert again.entries[i].flags[8] == 2
    assert len(again.entries) == len(lf.entries)


def test_set_target_rejects_newlines_and_flag_prefix():
    lf = langfile.load(LANG_DIR / "Taiwan.lang")
    with pytest.raises(ValueError):
        lf.set_target(0, Field.CAPTION, ["a\nb"])
    with pytest.raises(ValueError):
        lf.set_target(0, Field.CAPTION, ["||0100"])


def test_missing_line_reports_line_number():
    plain = langcrypt.decrypt((LANG_DIR / "Taiwan.lang").read_bytes())
    lines = plain.split(b"\r\n")
    k = lines.index("&取消".encode())
    broken = b"\r\n".join(lines[:k] + lines[k + 1:])
    with pytest.raises(LangFormatError) as err:
        langfile.parse(broken)
    assert err.value.line_no > 12


def test_rejects_non_bom():
    with pytest.raises(LangFormatError):
        langfile.parse(b"hello")


def test_save_is_atomic_when_replace_fails(lang_copy, monkeypatch):
    path = lang_copy("Taiwan.lang")
    original = path.read_bytes()
    lf = langfile.load(path)
    lf.set_target(1, Field.CAPTION, ["改過"])

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        langfile.save(path, lf)
    assert path.read_bytes() == original


def test_save_then_load(lang_copy):
    path = lang_copy("Taiwan.lang")
    lf = langfile.load(path)
    lf.set_target(1, Field.CAPTION, ["改過"])
    langfile.save(path, lf)
    assert langfile.load(path).entries[1].target[Field.CAPTION] == ["改過"]


def test_atomic_write_cleans_tmp_on_failure(tmp_path, monkeypatch):
    import os
    target = tmp_path / "a.bin"

    def boom(*a, **k):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        langfile.atomic_write(target, b"x")
    assert not list(tmp_path.glob("*.tmp")) and not target.exists()
