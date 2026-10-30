"""介面翻譯（ADR-0020）：.ts 要跟程式裡的字串一致、全部翻完，.qm 要是最新的。

改了介面文字後這裡會失敗：執行 `uv run i18n`，用 Qt Linguist 翻好新字串，再執行一次。
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from pllangstudio import release, resources

LANGS = release.TRANSLATION_LANGUAGES
PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def messages(ts):
    """{(情境, 原文, 註解): (翻譯, 是否未完成)}"""
    out = {}
    for ctx in ET.parse(ts).getroot().iter("context"):
        name = ctx.find("name").text
        for m in ctx.iter("message"):
            comment = m.find("comment")
            tr = m.find("translation")
            out[(name, m.find("source").text, comment.text if comment is not None else None)] = \
                (tr.text or "", tr.get("type") == "unfinished")
    return out


@pytest.mark.parametrize("code", LANGS)
def test_ts_matches_source_code(code, tmp_path):
    ts = tmp_path / release.ts_path(code).name
    shutil.copy(release.ts_path(code), ts)
    subprocess.run([release.qt_tool("lupdate"), *release.lupdate_args(ts)], check=True, capture_output=True)
    assert set(messages(ts)) == set(messages(release.ts_path(code))), "程式的介面文字有變動，請執行 uv run i18n"


@pytest.mark.parametrize("code", LANGS)
def test_all_strings_translated_with_same_placeholders(code):
    for (ctx, src, _comment), (text, unfinished) in messages(release.ts_path(code)).items():
        assert text and not unfinished, f"{ctx}：{src} 還沒翻譯"
        assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(src)), f"{ctx}：{src} → {text}"


@pytest.mark.parametrize("code", LANGS)
def test_qm_is_up_to_date(code, tmp_path):
    qm = tmp_path / "out.qm"
    subprocess.run([release.qt_tool("lrelease"), str(release.ts_path(code)), "-qm", str(qm)], check=True,
                   capture_output=True)
    assert qm.read_bytes() == resources.path(f"i18n/pllangstudio_{code}.qm").read_bytes(), "請執行 uv run i18n"


def test_english_avoids_master_slave_wording():
    """CONTEXT.md：主語系／副語系不寫成 MASTER／SLAVE，英文介面也一樣。"""
    texts = [t for t, _ in messages(release.ts_path("en")).values()]
    assert not [t for t in texts if re.search(r"\b(master|slave)\b", t, re.IGNORECASE)]


def test_no_literal_translation_inside_fstring():
    """f-string 大括號裡的 tr("…")／translate("…", "…") 收不到，切換語言後會一直是繁體中文。"""
    pattern = re.compile(r"""\bf(["']).*\{[^{}]*\b(tr|translate)\(\s*["'][^)]*["']\s*\)""")
    bad = [f"{p.name}:{n}" for p in release.translation_sources()
           for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert not bad
