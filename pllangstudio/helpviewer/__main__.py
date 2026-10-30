import argparse
import os
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pllangstudio import resources
from pllangstudio.core.helpdoc import THEMES, parse_command
from pllangstudio.helpviewer.window import HelpWindow, StdinBridge, chromium_flags, text_scale_factor


def main() -> int:
    parser = argparse.ArgumentParser(prog="PLLangHelp")
    parser.add_argument("--topic", default="-")
    parser.add_argument("--theme", choices=THEMES, default="light")
    # 由主程式啟動時才從 stdin 接收指令；單獨執行時 stdin 可能是空的，一讀到結尾就會被誤判成主程式已關閉
    parser.add_argument("--listen", action="store_true")
    args = parser.parse_args()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PLLangStudio.Help")
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # Qt WebEngine 要求在建立 QApplication 前設定
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PLLangHelp")
    app.setWindowIcon(QIcon(str(resources.path("app.ico"))))
    # 要知道 Qt 的縮放比例才能設定，Qt WebEngine 在建立第一個網頁元件時才讀取這些參數
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags(
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""), app.primaryScreen().devicePixelRatio())
    win = HelpWindow(resources.path("help/index.html"), args.topic, args.theme, zoom=text_scale_factor())
    win.show()
    bridge = StdinBridge()
    if args.listen and sys.stdin is not None:
        def on_line(line: str) -> None:
            cmd = parse_command(line)
            if cmd is not None:
                win.apply(cmd)
        bridge.received.connect(on_line)
        bridge.closed.connect(app.quit)  # 主程式關閉，說明視窗跟著關
        bridge.start(sys.stdin.fileno())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
