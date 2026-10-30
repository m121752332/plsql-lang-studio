import argparse
import os
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pllangstudio import resources
from pllangstudio.core.helpdoc import THEMES, parse_command
from pllangstudio.helpviewer.window import HelpWindow, StdinBridge


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
    # Chromium 偵測到視窗被主程式蓋住時會停止繪製，帶到前面後可能一直是黑畫面或舊畫面，關掉這個偵測
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --disable-features=CalculateNativeWinOcclusion".strip()
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)  # Qt WebEngine 要求在建立 QApplication 前設定
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PLLangHelp")
    app.setWindowIcon(QIcon(str(resources.path("app.ico"))))
    win = HelpWindow(resources.path("help/index.html"), args.topic, args.theme)
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
