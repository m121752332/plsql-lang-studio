"""打包與發行：`uv run build` 產生 dist\\PLLangStudio\\（主程式與說明程式 PLLangHelp\\），
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
APP_DIR = ROOT / "dist" / NAME  # 發行的內容，zip 就是把這個資料夾的內容壓起來
HELP_STAGE = ROOT / "build" / "dist" / HELP_NAME  # 說明程式先打包到這裡，沒變動時下次直接沿用


def version() -> str:
    """版本號以 pyproject.toml 為準。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def pyinstaller_args() -> list[str]:
    # 一律用絕對路徑：搭配 --specpath 時，相對路徑會從 build\ 算起
    res = ROOT / "pllangstudio" / "resources"
    return [
        # onedir：onefile 每次啟動都要把上百 MB 解壓到暫存資料夾，開程式多等 1 秒以上（見 ADR-0021）
        "--noconfirm", "--onedir", "--windowed",
        "--collect-all", "opencc",  # OpenCC 字典檔，不能省略
        # Qt WebEngine 只給說明程式用，主程式不能帶進去（見 ADR-0019）
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.QtWebChannel",
        "--exclude-module", "PySide6.QtNetwork",  # PySide6 的 hook 會順手帶進來，程式沒用到
        # PyInstaller 分析時會把 __main__ 直接加進我們的排除清單，存進快取後與下次的清單比對不符，
        # 每次都重新分析（多花約 30 秒）；先自己加上，快取才能沿用
        "--exclude-module", "__main__",
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
        "--distpath", str(HELP_STAGE.parent),
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


def _unused_main_files(internal: Path):
    """主程式用不到、PyInstaller 卻會帶進來的檔案。"""
    qt = internal / "PySide6"
    yield qt / "opengl32sw.dll"  # 沒有顯示卡驅動時的軟體 OpenGL，Widgets 程式用不到
    yield from qt.glob("Qt6Qml*.dll")  # QML／Quick 只被虛擬鍵盤外掛用到
    yield from qt.glob("Qt6Quick*.dll")
    yield qt / "Qt6VirtualKeyboard.dll"
    yield from (qt / "plugins" / "platforminputcontexts").glob("*")
    yield qt / "Qt6Pdf.dll"  # 只被 PDF 圖片外掛用到
    yield qt / "plugins" / "imageformats" / "qpdf.dll"
    keep = {f"qtbase_{code}.qm" for code in ("zh_TW", *TRANSLATION_LANGUAGES)}  # 對話框按鈕等 Qt 內建文字
    yield from (f for f in (qt / "translations").glob("*.qm") if f.name not in keep)
    yield from (internal / "opencc" / "clib" / "lib").glob("*.lib")  # 編譯用的靜態函式庫
    yield from (internal / "opencc" / "clib" / "bin").glob("*")  # opencc 命令列工具


def prune_main_dir(app_dir: Path) -> int:
    """刪掉主程式資料夾裡用不到的檔案，回傳省下的位元組數。"""
    removed = 0
    for f in set(_unused_main_files(app_dir / "_internal")):
        if f.is_file():
            removed += f.stat().st_size
            f.unlink()
    return removed


def install_help(staged: Path, app_dir: Path) -> None:
    """把打包好的說明程式複製到主程式旁邊（主程式用 exe 所在資料夾\\PLLangHelp\\ 找它）。"""
    dest = app_dir / HELP_NAME
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(staged, dest)


HELP_STAMP = ROOT / "build" / f"{HELP_NAME}.fingerprint"  # 上次打包說明程式時的指紋


def help_inputs() -> list[Path]:
    """會影響說明程式打包結果的檔案：程式、它 import 的 core 模組、資源、打包設定與依賴版本。"""
    pkg = ROOT / "pllangstudio"
    files = [pkg / "__init__.py", pkg / "core" / "__init__.py", pkg / "core" / "helpdoc.py",
             Path(__file__).resolve(), ROOT / "uv.lock"]
    for folder in (pkg / "helpviewer", pkg / "resources"):
        files += (f for f in folder.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    return files


def fingerprint(files: list[Path], root: Path) -> str:
    """依路徑與內容算出指紋，任何一個檔案改名或改內容都會不同。"""
    import hashlib
    import sys

    h = hashlib.sha256(sys.version.encode())  # 換 Python 版本也要重打包
    for f in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def help_up_to_date(help_dir: Path, stamp: Path, fp: str) -> bool:
    """說明程式還在，而且上次打包時的指紋與現在相同，就不必重打包。"""
    return ((help_dir / f"{HELP_NAME}.exe").is_file() and stamp.is_file()
            and stamp.read_text(encoding="utf-8") == fp)


def make_zip(app_dir: Path, out_dir: Path, ver: str) -> Path:
    """把程式資料夾的內容、README.md、LICENSE 壓成發行用 zip。先寫 .tmp 再換檔，不會留下壞掉的一半。

    zip 最外層就是 exe，不另外包一層資料夾：解壓後 workspace\\ 仍在 exe 旁邊，與舊版相同。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}-v{ver}-win64.zip"
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(app_dir.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(app_dir).as_posix())
        for name in ("README.md", "LICENSE"):
            z.write(ROOT / name, name)
    os.replace(tmp, out)
    return out


TRANSLATIONS = ROOT / "translations"  # 給翻譯者編輯的 .ts（可用 Qt Linguist 開啟）
TRANSLATION_LANGUAGES = ("zh_CN", "en", "ja")  # 程式原文是繁體中文，不需要介面翻譯


def ts_path(code: str) -> Path:
    return TRANSLATIONS / f"pllangstudio_{code}.ts"


def translation_sources() -> list[Path]:
    """要收集介面文字的程式檔。說明程式只有繁體中文（ADR-0019），本模組只在開發時用，都不收。"""
    pkg = ROOT / "pllangstudio"
    return sorted(p for p in pkg.rglob("*.py")
                  if "helpviewer" not in p.relative_to(pkg).parts and p.name != "release.py")


def qt_tool(name: str) -> str:
    """PySide6 附的 lupdate／lrelease，跟目前的 Python 放在同一個 Scripts 資料夾。"""
    import sys
    return str(Path(sys.executable).parent / f"pyside6-{name}")


def lupdate_args(ts: Path) -> list[str]:
    # 不記行號：程式改一行就會讓整份 .ts 變動，比對時看不出真正改了哪些字串
    return [*map(str, translation_sources()), "-no-obsolete", "-locations", "none",
            "-source-language", "zh_TW", "-target-language", ts.stem.removeprefix("pllangstudio_"), "-ts", str(ts)]


def i18n() -> int:
    """更新 .ts（收集新字串、刪掉不用的），再編成程式用的 .qm。新字串要翻好再執行一次。"""
    import subprocess

    out_dir = ROOT / "pllangstudio" / "resources" / "i18n"
    out_dir.mkdir(parents=True, exist_ok=True)
    for code in TRANSLATION_LANGUAGES:
        ts = ts_path(code)
        subprocess.run([qt_tool("lupdate"), *lupdate_args(ts)], check=True)
        subprocess.run([qt_tool("lrelease"), str(ts), "-qm", str(out_dir / f"pllangstudio_{code}.qm")], check=True)
    return 0


def build() -> int:
    import PyInstaller.__main__

    for old in (ROOT / "dist" / f"{NAME}.exe", ROOT / "dist" / HELP_NAME):  # 舊版 onefile 打包留下的成品
        if old.is_file():
            old.unlink()
        else:
            shutil.rmtree(old, ignore_errors=True)
    PyInstaller.__main__.run(pyinstaller_args())
    print(f"主程式移除用不到的檔案 {prune_main_dir(APP_DIR) / 1024 / 1024:.0f} MB")
    fp = fingerprint(help_inputs(), ROOT)
    if help_up_to_date(HELP_STAGE, HELP_STAMP, fp):
        print("說明程式沒有變動，沿用上次打包的結果")
    else:
        HELP_STAMP.unlink(missing_ok=True)  # 打包中途失敗時，不能留下舊指紋
        PyInstaller.__main__.run(help_pyinstaller_args())
        saved = prune_help_dir(HELP_STAGE)
        print(f"說明程式移除用不到的檔案 {saved / 1024 / 1024:.0f} MB")
        HELP_STAMP.write_text(fp, encoding="utf-8")
    install_help(HELP_STAGE, APP_DIR)
    print(f"完成：{APP_DIR}")
    return 0


def package() -> int:
    build()
    out = make_zip(APP_DIR, ROOT / "bin", version())
    print(f"完成：{out}")
    return 0
