import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig, resources
from pllangstudio.core.workspace import default_root
from pllangstudio.ui.fonts import FontManager
from pllangstudio.ui.main_window import MainWindow
from pllangstudio.ui.theme import ThemeManager


def main() -> int:
    if sys.platform == "win32":  # 用 python 執行時，工作列才會顯示本程式的圖示而不是 Python 的
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PLLangStudio")
    app = QApplication(sys.argv)
    app.setApplicationName("PLLangStudio")
    app.setWindowIcon(QIcon(str(resources.path("app.ico"))))
    theme = ThemeManager(app)  # 先套用主題和字型再建立視窗，避免開啟時閃一下
    fonts = FontManager(app)
    root = appconfig.last_workspace() or default_root(appconfig.app_dir())
    win = MainWindow(root, theme_manager=theme, font_manager=fonts)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
