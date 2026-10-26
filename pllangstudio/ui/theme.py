"""固定使用淺色主題：表格的狀態底色是淺色系，深色模式下白字會看不見。"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    for role, color in ((QPalette.Window, "#f3f3f3"), (QPalette.WindowText, "#1a1a1a"),
                        (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f5f7fa"),
                        (QPalette.Text, "#1a1a1a"), (QPalette.Button, "#ececec"),
                        (QPalette.ButtonText, "#1a1a1a"), (QPalette.ToolTipBase, "#ffffdc"),
                        (QPalette.ToolTipText, "#1a1a1a"), (QPalette.Highlight, "#3874d8"),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.PlaceholderText, "#888888")):
        p.setColor(role, QColor(color))
    app.setPalette(p)
