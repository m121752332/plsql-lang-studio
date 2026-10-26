import pytest

from langdata import LANG_FILES, needs_lang_dir
from pllangstudio.core import langcrypt


@needs_lang_dir
@pytest.mark.parametrize("path", LANG_FILES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    data = path.read_bytes()
    plain = langcrypt.decrypt(data)
    plain.decode("utf-8")
    assert langcrypt.encrypt(plain) == data


def test_normalize_adds_bom_and_crlf():
    assert langcrypt.normalize_text("甲\n乙\r\n丙".encode()) == langcrypt.BOM + "甲\r\n乙\r\n丙".encode()


def test_rejects_non_lang_file():
    with pytest.raises(ValueError):
        langcrypt.decrypt(b"hello world")


def test_rejects_non_utf8_text():
    with pytest.raises(UnicodeDecodeError):
        langcrypt.normalize_text("中文".encode("big5"))
