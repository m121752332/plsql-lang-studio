"""靜態檔案（圖示等）。檔案和本模組放在同一個資料夾，打包時要用 --add-data 一起帶進 exe。"""

from pathlib import Path

_DIR = Path(__file__).parent


def path(name: str) -> Path:
    return _DIR / name
