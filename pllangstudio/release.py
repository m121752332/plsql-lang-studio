"""打包與發行：`uv run build` 產生 dist\\PLLangStudio.exe，`uv run package` 再壓成 bin\\ 底下的 zip。

程式本身不會 import 這個模組，所以不會被包進 exe。
"""

import os
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "PLLangStudio"


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
        "--add-data", f"{res};pllangstudio/resources",
        "--icon", str(res / "app.ico"),
        "--name", NAME,
        "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build"),
        "--distpath", str(ROOT / "dist"),
        str(ROOT / "pllangstudio" / "__main__.py"),
    ]


def make_zip(exe: Path, out_dir: Path, ver: str) -> Path:
    """把 exe、README.md、LICENSE 壓成發行用 zip。先寫 .tmp 再換檔，不會留下壞掉的一半。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{NAME}-v{ver}-win64.zip"
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, exe.name)
        for name in ("README.md", "LICENSE"):
            z.write(ROOT / name, name)
    os.replace(tmp, out)
    return out


def build() -> int:
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args())
    print(f"完成：{ROOT / 'dist' / (NAME + '.exe')}")
    return 0


def package() -> int:
    build()
    out = make_zip(ROOT / "dist" / f"{NAME}.exe", ROOT / "bin", version())
    print(f"完成：{out}")
    return 0
