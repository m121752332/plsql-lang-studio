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


def _app_dir(tmp_path):
    """假的 dist\PLLangStudio\：主程式、_internal\ 與說明程式。"""
    app = tmp_path / "PLLangStudio"
    (app / "_internal").mkdir(parents=True)
    (app / "PLLangStudio.exe").write_bytes(b"MZ fake exe")
    (app / "_internal" / "python314.dll").write_bytes(b"dll")
    (app / "PLLangHelp" / "_internal").mkdir(parents=True)
    (app / "PLLangHelp" / "PLLangHelp.exe").write_bytes(b"MZ help")
    return app


def test_make_zip_puts_program_files_at_top_level(tmp_path):
    """zip 最外層就是 exe，解壓後 workspace\ 仍在 exe 旁邊（預設工作區位置不變）。"""
    out = release.make_zip(_app_dir(tmp_path), tmp_path / "bin", "9.9.9")
    assert out == tmp_path / "bin" / "PLLangStudio-v9.9.9-win64.zip"
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["LICENSE", "PLLangHelp/PLLangHelp.exe", "PLLangStudio.exe", "README.md",
                                        "_internal/python314.dll"]
        assert z.read("PLLangStudio.exe") == b"MZ fake exe"
    assert not list((tmp_path / "bin").glob("*.tmp"))


def test_main_program_is_onedir_without_qtnetwork():
    """onefile 每次啟動都要解壓上百 MB，開程式要多等 1 秒以上。"""
    args = release.pyinstaller_args()
    assert "--onedir" in args and "--onefile" not in args
    assert "PySide6.QtNetwork" in {args[i + 1] for i, a in enumerate(args) if a == "--exclude-module"}


def test_main_program_excludes_webengine():
    args = release.pyinstaller_args()
    excluded = {args[i + 1] for i, a in enumerate(args) if a == "--exclude-module"}
    assert {"PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"} <= excluded


def test_main_program_excludes_dunder_main_to_keep_analysis_cache():
    args = release.pyinstaller_args()
    assert "__main__" in {args[i + 1] for i, a in enumerate(args) if a == "--exclude-module"}


def test_help_program_args():
    args = release.help_pyinstaller_args()
    assert "--onedir" in args and "--onefile" not in args
    assert args[args.index("--name") + 1] == "PLLangHelp"
    src = args[args.index("--add-data") + 1].rsplit(";", 1)[0]
    assert (Path(src) / "help" / "index.html").is_file()
    assert Path(args[-1]).is_file() and Path(args[-1]).parent.name == "helpviewer"


def test_install_help_copies_into_app_dir(tmp_path):
    app = tmp_path / "PLLangStudio"
    (app / "PLLangHelp").mkdir(parents=True)
    (app / "PLLangHelp" / "stale.dll").write_bytes(b"old")  # 上次留下的檔案要清掉
    staged = tmp_path / "staged" / "PLLangHelp"
    (staged / "_internal").mkdir(parents=True)
    (staged / "PLLangHelp.exe").write_bytes(b"MZ help")
    (staged / "_internal" / "a.dll").write_bytes(b"dll")
    release.install_help(staged, app)
    assert (app / "PLLangHelp" / "PLLangHelp.exe").read_bytes() == b"MZ help"
    assert (app / "PLLangHelp" / "_internal" / "a.dll").is_file()
    assert not (app / "PLLangHelp" / "stale.dll").exists()
    assert (staged / "PLLangHelp.exe").is_file()  # 暫存的說明程式留著，下次沒變動就直接沿用


def test_prune_main_dir_removes_unused_files_only(tmp_path):
    internal = tmp_path / "PLLangStudio" / "_internal"
    keep = ["PySide6/Qt6Core.dll", "PySide6/Qt6Gui.dll", "PySide6/Qt6Widgets.dll", "PySide6/Qt6Svg.dll",
            "PySide6/plugins/platforms/qwindows.dll", "PySide6/plugins/imageformats/qico.dll",
            "PySide6/plugins/styles/qmodernwindowsstyle.dll",
            "PySide6/translations/qtbase_zh_TW.qm", "PySide6/translations/qtbase_zh_CN.qm",
            "PySide6/translations/qtbase_ja.qm", "PySide6/translations/qtbase_en.qm",
            "libcrypto-3.dll", "opencc/clib/share/opencc/STPhrases.ocd2", "opencc/clib/opencc_clib.cp314-win_amd64.pyd"]
    drop = ["PySide6/opengl32sw.dll", "PySide6/Qt6Pdf.dll", "PySide6/Qt6Quick.dll", "PySide6/Qt6Qml.dll",
            "PySide6/Qt6QmlModels.dll", "PySide6/Qt6QmlMeta.dll", "PySide6/Qt6QmlWorkerScript.dll",
            "PySide6/Qt6VirtualKeyboard.dll", "PySide6/plugins/imageformats/qpdf.dll",
            "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
            "PySide6/translations/qtbase_fr.qm", "PySide6/translations/qt_zh_TW.qm",
            "opencc/clib/lib/opencc.lib", "opencc/clib/bin/opencc.exe"]
    for rel in keep + drop:
        (internal / rel).parent.mkdir(parents=True, exist_ok=True)
        (internal / rel).write_bytes(b"x" * 10)
    removed = release.prune_main_dir(tmp_path / "PLLangStudio")
    assert removed == 10 * len(drop)
    assert all((internal / rel).is_file() for rel in keep)
    assert not any((internal / rel).exists() for rel in drop)


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


def test_help_inputs_cover_viewer_resources_and_build_settings():
    rel = {p.relative_to(release.ROOT).as_posix() for p in release.help_inputs()}
    assert {"pllangstudio/helpviewer/__main__.py", "pllangstudio/helpviewer/window.py",
            "pllangstudio/core/helpdoc.py", "pllangstudio/resources/help/index.html",
            "pllangstudio/resources/app.ico", "pllangstudio/release.py", "uv.lock"} <= rel
    assert not any("__pycache__" in r for r in rel)


def test_fingerprint_changes_with_content_and_path(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1")
    b.write_text("2")
    base = release.fingerprint([a, b], tmp_path)
    assert release.fingerprint([b, a], tmp_path) == base  # 與傳入順序無關
    a.write_text("changed")
    assert release.fingerprint([a, b], tmp_path) != base
    a.write_text("1")
    a.rename(tmp_path / "c.txt")
    assert release.fingerprint([tmp_path / "c.txt", b], tmp_path) != base


def test_help_up_to_date_needs_exe_and_matching_stamp(tmp_path):
    help_dir = tmp_path / "PLLangHelp"
    stamp = tmp_path / "PLLangHelp.fingerprint"
    assert not release.help_up_to_date(help_dir, stamp, "abc")
    stamp.write_text("abc")
    assert not release.help_up_to_date(help_dir, stamp, "abc")  # 說明程式被刪掉了
    help_dir.mkdir()
    (help_dir / "PLLangHelp.exe").write_bytes(b"MZ")
    assert release.help_up_to_date(help_dir, stamp, "abc")
    assert not release.help_up_to_date(help_dir, stamp, "def")


def test_make_zip_overwrites_existing(tmp_path):
    app = _app_dir(tmp_path)
    release.make_zip(app, tmp_path, "1.0.0")
    (app / "PLLangStudio.exe").write_bytes(b"new")
    out = release.make_zip(app, tmp_path, "1.0.0")
    with zipfile.ZipFile(out) as z:
        assert z.read("PLLangStudio.exe") == b"new"
