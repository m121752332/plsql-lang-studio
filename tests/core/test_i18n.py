import pytest

from pllangstudio.core import i18n, validate


@pytest.fixture
def fake_translator():
    """把每個字串都加上語言標記的假翻譯；測試結束還原成不翻譯。"""
    i18n.install(lambda context, text: f"[{context}]{text}")
    yield
    i18n.install(None)


def test_returns_source_text_without_translator():
    assert i18n.translate("validate", "殘留簡體字：{chars}") == "殘留簡體字：{chars}"


def test_noop_marker_returns_text_unchanged(fake_translator):
    assert i18n.QT_TRANSLATE_NOOP("Status", "不同") == "不同"


def test_translate_uses_installed_translator(fake_translator):
    assert i18n.translate("langfile", "換行字元必須是 CRLF") == "[langfile]換行字元必須是 CRLF"


def test_issue_message_is_translated_when_read():
    """檢查結果會留在表格裡；切換介面語言後，提示要用新的語言顯示。"""
    issue = next(x for x in validate.check("Open", "开启") if x.code == "SIMPLIFIED")
    assert issue.message == "殘留簡體字：开启"
    i18n.install(lambda context, text: "Leftover: {chars}" if text == "殘留簡體字：{chars}" else text)
    try:
        assert issue.message == "Leftover: 开启"
    finally:
        i18n.install(None)


def test_core_error_messages_go_through_translator(fake_translator):
    from pllangstudio.core.langfile import LangFormatError
    assert str(LangFormatError(3, "壞了")) == "[langfile]第 3 行：壞了"
