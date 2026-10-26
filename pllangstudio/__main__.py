import sys

from PySide6.QtWidgets import QApplication

from pllangstudio import appconfig
from pllangstudio.core.workspace import default_root
from pllangstudio.ui.main_window import MainWindow
from pllangstudio.ui.theme import apply_light_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PLLangStudio")
    apply_light_theme(app)
    root = appconfig.last_workspace() or default_root(appconfig.app_dir())
    win = MainWindow(root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
