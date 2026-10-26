import sys

from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.core.workspace import default_root
from pllangstudio.ui.fonts import FontManager
from pllangstudio.ui.main_window import MainWindow
from pllangstudio.ui.theme import ThemeManager


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PLLangStudio")
    theme = ThemeManager(app)  # 先套用主題和字型再建立視窗，避免開啟時閃一下
    fonts = FontManager(app)
    root = appconfig.last_workspace() or default_root(appconfig.app_dir())
    win = MainWindow(root, theme_manager=theme, font_manager=fonts)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
