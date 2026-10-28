from PySide6.QtGui import QIcon

from pllangstudio import resources


def test_app_icon_file_exists():
    assert resources.path("app.ico").is_file()


def test_app_icon_loads(qtbot):
    icon = QIcon(str(resources.path("app.ico")))
    assert not icon.isNull() and icon.availableSizes()
