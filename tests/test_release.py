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


def test_make_zip_overwrites_existing(tmp_path):
    exe = tmp_path / "PLLangStudio.exe"
    exe.write_bytes(b"old")
    release.make_zip(exe, tmp_path, "1.0.0")
    exe.write_bytes(b"new")
    out = release.make_zip(exe, tmp_path, "1.0.0")
    with zipfile.ZipFile(out) as z:
        assert z.read("PLLangStudio.exe") == b"new"
