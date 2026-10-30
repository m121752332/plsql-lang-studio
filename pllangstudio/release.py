"""打包與發行：`uv run build` 產生 dist\\PLLangStudio.exe 與說明程式 dist\\PLLangHelp\\，
`uv run package` 再壓成 bin\\ 底下的 zip。

程式本身不會 import 這個模組，所以不會被包進 exe。
"""

import os
import shutil
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "PLLangStudio"
HELP_NAME = "PLLangHelp"


def version() -> str:
    """版本號以 pyproject.toml 為準。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def pyinstaller_args() -> list[str]:
    # 一律用絕對路徑：搭配 --specpath 時，相對路徑會從 build\ 算起
    res = ROOT / "pllangstudio" / "resources"
    return [
        "--noconfirm", "--onefile", "--windowed",
        "--collect-all", "opencc",  # OpenCC 字典檔，不能省略
        # Qt WebEngine 只給說明程式用，主程式不能帶進去（見 ADR-0019）
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.QtWebChannel",
        "--add-data", f"{res};pllangstudio/resources",
        "--icon", str(res / "app.ico"),
        "--name", NAME,
        "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build"),
        "--distpath", str(ROOT / "dist"),
        str(ROOT / "pllangstudio" / "__main__.py"),
    ]


def help_pyinstaller_args() -> list[str]:
    """說明程式用資料夾形式（onedir），Chromium 很大，每次啟動都解壓太慢。"""
    res = ROOT / "pllangstudio" / "resources"
    return [
        "--noconfirm", "--onedir", "--windowed",
        "--add-data", f"{res};pllangstudio/resources",
        "--icon", str(res / "app.ico"),
        "--name", HELP_NAME,
        "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build"),
        "--distpath", str(ROOT / "dist"),
        str(ROOT / "pllangstudio" / "helpviewer" / "__main__.py"),
    ]


def _unused_help_files(qt: Path):
    """說明程式用不到、PyInstaller 卻會帶進來的 Qt 檔案。"""
    res = qt / "resources"
    yield from res.glob("*.debug.pak")  # 給除錯版 Qt 用的
    yield from res.glob("*.debug.bin")
    yield from res.glob("qtwebengine_devtools_resources*.pak")  # 開發者工具
    for f in (qt / "translations" / "qtwebengine_locales").glob("*.pak"):
        if f.stem not in ("en-US", "zh-TW"):
            yield f
    for f in (qt / "translations").glob("*.qm"):
        if "zh_TW" not in f.name:
            yield f
    if (qt / "qml").is_dir():  # 說明程式是 Widgets 程式，不載入 QML 模組
        yield from (f for f in (qt / "qml").rglob("*") if f.is_file())


def prune_help_dir(help_dir: Path) -> int:
    """刪掉說明程式資料夾裡用不到的檔案，回傳省下的位元組數。"""
    qt = help_dir / "_internal" / "PySide6"
    removed = 0
    for f in set(_unused_help_files(qt)):  # 同一個檔案可能符合多條規則
        removed += f.stat().st_size
        f.unlink()
    shutil.rmtree(qt / "qml", ignore_errors=True)
    return removed


def make_zip(exe: Path, out_dir: Path, ver: str, help_dir: Path | None = None) -> Path:
    """把 exe、說明程式資料夾、README.md、LICENSE 壓成發行用 zip。先寫 .tmp 再換檔，不會留下壞掉的一半。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}-v{ver}-win64.zip"
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, exe.name)
        if help_dir is not None:
            for f in sorted(help_dir.rglob("*")):
                if f.is_file():
                    z.write(f, f"{help_dir.name}/{f.relative_to(help_dir).as_posix()}")
        for name in ("README.md", "LICENSE"):
            z.write(ROOT / name, name)
    os.replace(tmp, out)
    return out


def build() -> int:
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args())
    PyInstaller.__main__.run(help_pyinstaller_args())
    saved = prune_help_dir(ROOT / "dist" / HELP_NAME)
    print(f"說明程式移除用不到的檔案 {saved / 1024 / 1024:.0f} MB")
    print(f"完成：{ROOT / 'dist' / (NAME + '.exe')}、{ROOT / 'dist' / HELP_NAME}")
    return 0


def package() -> int:
    build()
    out = make_zip(ROOT / "dist" / f"{NAME}.exe", ROOT / "bin", version(), ROOT / "dist" / HELP_NAME)
    print(f"完成：{out}")
    return 0
