"""PL/SQL Developer .lang 檔加解密。

.lang 檔是 UTF-8（含 BOM）純文字，與一組 256 bytes 的循環金鑰做 XOR。
XOR 是對稱的，所以加密與解密是同一個運算。
"""

from . import i18n

KEY = bytes.fromhex(
    "c5c8dfe2f1fc8b96ada0b74a5954637e15180f32212cdbc6fdf0e79a8984b3ae"
    "65687f42515c2b360d0017eaf9f4c3deb5b8af92818c7b665d50473a2924130e"
    "85889fa2b1bccbd6ede0f70a1914233e55584f72616c9b86bdb0a7dac9c4f3ee"
    "25283f02111c6b764d4057aab9b4839ef5f8efd2c1cc3b261d10077a6964534e"
    "45485f62717c0b162d2037cad9d4e3fe95988fb2a1ac5b467d70671a0904332e"
    "e5e8ffc2d1dcabb68d80976a7974435e35382f12010cfbe6ddd0c7baa9a4938e"
    "05081f22313c4b566d60778a9994a3bed5d8cff2e1ec1b063d30275a4944736e"
    "a5a8bf82919cebf6cdc0d72a3934031e75786f52414cbba69d9087fae9e4d3ce"
)
BOM = b"\xef\xbb\xbf"


def xor(data: bytes) -> bytes:
    n = len(data)
    stream = (KEY * (n // 256 + 1))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(n, "big")


def decrypt(data: bytes) -> bytes:
    plain = xor(data)
    if not plain.startswith(BOM):
        raise ValueError(i18n.translate("langcrypt", "這不是有效的 PL/SQL Developer .lang 檔（解密後沒有 UTF-8 BOM）"))
    return plain


def normalize_text(raw: bytes) -> bytes:
    """把編輯後的 .txt 整理成 .lang 需要的格式：UTF-8 + BOM、CRLF 換行。"""
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    text = raw.decode("utf-8")  # 編碼錯誤時拋出 UnicodeDecodeError
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return BOM + text.encode("utf-8")


def encrypt(plain: bytes) -> bytes:
    return xor(normalize_text(plain))
