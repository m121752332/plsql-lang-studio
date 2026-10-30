import zipfile
from pathlib import Path

import pllangstudio
from pllangstudio import release


def test_version_matches_package():
    assert release.version() == pllangstudio.__version__


def test_pyinstaller_args_point_to_existing_files():
    args = release.pyinstaller_args()
    assert Path(args[args.index("--icon") + 1]).is_file()
    src = args[args.index("--add-data") + 1].rsplit(";", 1)[0]
    assert Path(src).is_dir()
    assert Path(args[-1]).is_file()  # 進入點


def test_make_zip_contains_exe_readme_license(tmp_path):
    exe = tmp_path / "PLLangStudio.exe"
    exe.write_bytes(b"MZ fake exe")
    out = release.make_zip(exe, tmp_path / "bin", "9.9.9")
    assert out == tmp_path / "bin" / "PLLangStudio-v9.9.9-win64.zip"
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["LICENSE", "PLLangStudio.exe", "README.md"]
        assert z.read("PLLangStudio.exe") == b"MZ fake exe"
    assert not list((tmp_path / "bin").glob("*.tmp"))


def test_main_program_excludes_webengine():
    args = release.pyinstaller_args()
    excluded = {args[i + 1] for i, a in enumerate(args) if a == "--exclude-module"}
    assert {"PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"} <= excluded


def test_help_program_args():
    args = release.help_pyinstaller_args()
    assert "--onedir" in args and "--onefile" not in args
    assert args[args.index("--name") + 1] == "PLLangHelp"
    src = args[args.index("--add-data") + 1].rsplit(";", 1)[0]
    assert (Path(src) / "help" / "index.html").is_file()
    assert Path(args[-1]).is_file() and Path(args[-1]).parent.name == "helpviewer"


def test_make_zip_includes_help_folder(tmp_path):
    exe = tmp_path / "PLLangStudio.exe"
    exe.write_bytes(b"MZ")
    help_dir = tmp_path / "PLLangHelp"
    (help_dir / "_internal").mkdir(parents=True)
    (help_dir / "PLLangHelp.exe").write_bytes(b"MZ help")
    (help_dir / "_internal" / "a.dll").write_bytes(b"dll")
    out = release.make_zip(exe, tmp_path / "bin", "9.9.9", help_dir)
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    assert {"PLLangStudio.exe", "README.md", "LICENSE",
            "PLLangHelp/PLLangHelp.exe", "PLLangHelp/_internal/a.dll"} <= names


def test_prune_help_dir_removes_unused_files_only(tmp_path):
    qt = tmp_path / "PLLangHelp" / "_internal" / "PySide6"
    keep = ["Qt6WebEngineCore.dll", "QtWebEngineProcess.exe", "opengl32sw.dll",
            "resources/qtwebengine_resources.pak", "resources/icudtl.dat", "resources/v8_context_snapshot.bin",
            "translations/qtwebengine_locales/en-US.pak", "translations/qtwebengine_locales/zh-TW.pak",
            "translations/qtbase_zh_TW.qm"]
    drop = ["resources/qtwebengine_resources.debug.pak", "resources/v8_context_snapshot.debug.bin",
            "resources/qtwebengine_devtools_resources.pak", "resources/qtwebengine_devtools_resources.debug.pak",
            "translations/qtwebengine_locales/fr.pak",
            "translations/qtbase_fr.qm", "qml/QtQuick/a.qml"]
    for rel in keep + drop:
        (qt / rel).parent.mkdir(parents=True, exist_ok=True)
        (qt / rel).write_bytes(b"x" * 10)
    removed = release.prune_help_dir(tmp_path / "PLLangHelp")
    assert removed == 10 * len(drop)
    assert all((qt / rel).is_file() for rel in keep)
    assert not any((qt / rel).exists() for rel in drop)
    assert not (qt / "qml").exists()


def test_make_zip_overwrites_existing(tmp_path):
    exe = tmp_path / "PLLangStudio.exe"
    exe.write_bytes(b"old")
    release.make_zip(exe, tmp_path, "1.0.0")
    exe.write_bytes(b"new")
    out = release.make_zip(exe, tmp_path, "1.0.0")
    with zipfile.ZipFile(out) as z:
        assert z.read("PLLangStudio.exe") == b"new"
