"""介面語言：用 Qt 的 QTranslator 切換，設定存在 app.json，下次啟動沿用（見 ADR-0020）。

程式原文是繁體中文，選繁體中文時不載入本程式的介面翻譯（.qm）。切換時 Qt 會送 LanguageChange 給所有視窗，
開著的視窗在 changeEvent 裡重設文字，不必重新啟動。
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, QTranslator, Signal

from .. import appconfig, resources
from ..core import i18n

# 選單上一律用該語言自己的寫法，看不懂目前語言的人也找得到
LANGUAGE_NAMES = {"zh_TW": "繁體中文", "zh_CN": "简体中文", "en": "English", "ja": "日本語"}


def qm_path(code: str):
    return resources.path(f"i18n/pllangstudio_{code}.qm")


class LanguageManager(QObject):
    changed = Signal()

    def __init__(self, app: QCoreApplication, parent=None):
        super().__init__(parent)
        self.app = app
        self.code = appconfig.language()
        self._translators: list[QTranslator] = []
        i18n.install(QCoreApplication.translate)  # core 與 eventlog 的訊息也走 Qt 的翻譯
        self._apply()

    def set_language(self, code: str) -> None:
        if code not in LANGUAGE_NAMES:
            raise ValueError(f"未知的介面語言：{code}")
        if code == self.code:
            return
        self.code = code
        appconfig.remember_language(code)
        self._apply()

    def _apply(self) -> None:
        for t in self._translators:
            self.app.removeTranslator(t)
            t.deleteLater()
        self._translators = []
        # Qt 自己的文字（標準按鈕、輸入框右鍵選單）；找不到就維持英文
        qt = QTranslator(self)
        if qt.load(f"qtbase_{self.code}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            self._translators.append(qt)
        if self.code != appconfig.LANGUAGES[0]:
            own = QTranslator(self)
            if own.load(str(qm_path(self.code))):
                self._translators.append(own)
        for t in self._translators:
            self.app.installTranslator(t)
        self.changed.emit()
