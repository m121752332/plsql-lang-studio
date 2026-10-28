import platform
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from pllangstudio import __version__, appconfig, eventlog, resources
from pllangstudio.core.workspace import default_root
from pllangstudio.ui.fonts import FontManager
from pllangstudio.ui.main_window import MainWindow
from pllangstudio.ui.theme import ThemeManager


def main() -> int:
    if sys.platform == "win32":  # 用 python 執行時，工作列才會顯示本程式的圖示而不是 Python 的
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PLLangStudio")
    eventlog.setup(eventlog.default_path(), appconfig.log_retention())  # 越早越好，後面出錯才記得到
    eventlog.info("程式", f"PLLangStudio {__version__} 啟動（{platform.platform()}）")
    app = QApplication(sys.argv)
    app.setApplicationName("PLLangStudio")
    app.setWindowIcon(QIcon(str(resources.path("app.ico"))))
    eventlog.install_excepthook(lambda eid: QMessageBox.critical(
        QApplication.activeWindow(), "發生未預期的錯誤", eventlog.crash_message(eid)))
    app.aboutToQuit.connect(lambda: eventlog.info("程式", "PLLangStudio 結束"))
    theme = ThemeManager(app)  # 先套用主題和字型再建立視窗，避免開啟時閃一下
    fonts = FontManager(app)
    root = appconfig.last_workspace() or default_root(appconfig.app_dir())
    win = MainWindow(root, theme_manager=theme, font_manager=fonts)
    win.show()
    code = app.exec()
    eventlog.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
