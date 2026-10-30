"""介面語言（見 ADR-0020）：core 產生給使用者看的文字時經過這裡翻譯。

core 不能 import Qt（ADR-0006），由畫面層啟動時用 install() 接上 QCoreApplication.translate；
沒接上時（例如核心測試）一律回傳原文，也就是繁體中文。

pyside6-lupdate 只認得 `某物.translate("情境", "原文")`（剛好兩個參數）與 `QT_TRANSLATE_NOOP("情境", "原文")`，
所以呼叫時情境與原文都要寫成字面字串；有變數的訊息用 {名稱} 佔位，翻譯後再 format()。
"""

from __future__ import annotations

from typing import Callable

_translator: Callable[[str, str], str] | None = None


def install(translator: Callable[[str, str], str] | None) -> None:
    global _translator
    _translator = translator


def translate(context: str, text: str) -> str:
    return text if _translator is None else _translator(context, text)


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802 名稱要跟 Qt 一樣，lupdate 才認得
    """只標記要翻譯的字串，原樣回傳；用在模組層級的常數，顯示時再呼叫 translate()。"""
    return text
