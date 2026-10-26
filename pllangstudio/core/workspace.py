"""工作區：匯入、存檔、備份、部署、記事本 .txt 同步（見 ADR-0004、0008、0009）。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import appconfig
from . import glossary, langcrypt, langfile
from .langfile import LangFile

DEFAULT_PLSQL_DIR = Path(r"C:\Program Files\PLSQL Developer 17\Languages")


def find_plsql_lang_dir() -> Path | None:
    if DEFAULT_PLSQL_DIR.is_dir():
        return DEFAULT_PLSQL_DIR
    found = sorted(p for base in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)"))
                   if base.is_dir() for p in base.glob("PLSQL Developer*/Languages") if p.is_dir())
    return found[-1] if found else None


def is_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def default_root(app_dir: Path) -> Path:
    first = app_dir / "workspace"
    if is_writable(first):
        return first
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Documents" / "PLLangStudio" / "workspace"


@dataclass
class Settings:
    plsql_lang_dir: str = ""
    master: str = "Chinese.lang"
    slave: str = "Taiwan.lang"


@dataclass
class LangInfo:
    name: str
    path: Path
    size: int
    mtime: float
    imported: bool = False      # 用於 PL/SQL 清單：工作區是否已有同名檔
    deployed: bool | None = None  # 用於工作區清單：是否與 PL/SQL 目錄裡的同名檔相同


@dataclass
class DeployResult:
    ok: bool
    changed: bool
    message: str
    backup: Path | None = None


class ImportConflict(Exception):
    """工作區已有同名檔而且內容不同。"""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lang_dir = self.root / "lang"
        self.txt_dir = self.root / "txt"
        self.backup_dir = self.root / "backup"
        for d in (self.lang_dir, self.txt_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.glossary_path = self.root / "glossary.json"
        self.settings = self._load_settings()
        if not self.glossary_path.exists():
            glossary.save(self.glossary_path, glossary.default())
        self._txt_hash: dict[str, str] = {}

    # ---------- 設定 ----------

    def _load_settings(self) -> Settings:
        s = Settings()
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                s = Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                appconfig.quarantine(self.settings_path)
                s = Settings()
        if not s.plsql_lang_dir:
            found = find_plsql_lang_dir()
            s.plsql_lang_dir = str(found) if found else ""
        return s

    def save_settings(self) -> None:
        text = json.dumps(asdict(self.settings), ensure_ascii=False, indent=2)
        langfile.atomic_write(self.settings_path, text.encode("utf-8"))

    @property
    def installed_dir(self) -> Path:
        return Path(self.settings.plsql_lang_dir)

    def load_glossary(self) -> glossary.Glossary:
        return glossary.load(self.glossary_path)

    def save_glossary(self, g: glossary.Glossary) -> None:
        glossary.save(self.glossary_path, g)

    # ---------- 清單 ----------

    def list_installed(self) -> list[LangInfo]:
        if not self.installed_dir.is_dir():
            return []
        return [LangInfo(p.name, p, p.stat().st_size, p.stat().st_mtime, (self.lang_dir / p.name).exists())
                for p in sorted(self.installed_dir.glob("*.lang"))]

    def list_workspace(self) -> list[LangInfo]:
        out = []
        for p in sorted(self.lang_dir.glob("*.lang")):
            inst = self.installed_dir / p.name
            deployed = inst.exists() and inst.read_bytes() == p.read_bytes()
            out.append(LangInfo(p.name, p, p.stat().st_size, p.stat().st_mtime, True, deployed))
        return out

    def txt_path(self, name: str) -> Path:
        return self.txt_dir / (Path(name).stem + ".txt")

    # ---------- 匯入／存檔 ----------

    def backup(self, path: Path, prefix: str = "") -> Path:
        dst = self.backup_dir / f"{prefix}{path.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}{path.suffix}"
        shutil.copy2(path, dst)
        return dst

    def import_lang(self, name: str, overwrite: bool = False) -> None:
        src, dst = self.installed_dir / name, self.lang_dir / name
        data = src.read_bytes()
        plain = langcrypt.decrypt(data)
        langfile.parse(plain)  # 格式錯誤就拋出 LangFormatError，不匯入
        if dst.exists() and dst.read_bytes() != data:
            if not overwrite:
                raise ImportConflict(name)
            self.backup(dst)
        if self.txt_path(name).exists() and self._raw_differs(name, plain):
            self.backup_txt(name)  # 記事本改過的 .txt 不能無聲覆蓋
        langfile.atomic_write(dst, data)
        self.write_txt(name, plain)

    def load(self, name: str) -> LangFile:
        return langfile.load(self.lang_dir / name)

    def save(self, name: str, lf: LangFile) -> Path:
        target = self.lang_dir / name
        plain = langfile.serialize(lf)
        if target.exists():
            self.backup(target)
        langfile.atomic_write(target, langcrypt.encrypt(plain))
        self.write_txt(name, plain)
        return target

    # ---------- 記事本 .txt ----------

    def write_txt(self, name: str, plain: bytes) -> None:
        langfile.atomic_write(self.txt_path(name), plain)
        self._txt_hash[name] = _hash(plain)

    def _raw_differs(self, name: str, plain: bytes) -> bool:
        try:
            return langcrypt.normalize_text(self.txt_path(name).read_bytes()) != plain
        except UnicodeDecodeError:
            return True

    def txt_differs(self, name: str, lf: LangFile) -> bool:
        """.txt 存在而且內容和 lf 不同（例如程式關閉時在記事本改過）。"""
        return self.txt_path(name).exists() and self._raw_differs(name, langfile.serialize(lf))

    def backup_txt(self, name: str) -> Path:
        return self.backup(self.txt_path(name))

    def sync_txt(self, name: str, lf: LangFile) -> None:
        """編輯器開啟 SLAVE 時呼叫：讓 .txt 與程式內的正本一致。"""
        self.write_txt(name, langfile.serialize(lf))

    def txt_changed(self, name: str) -> bool:
        p = self.txt_path(name)
        return p.exists() and _hash(p.read_bytes()) != self._txt_hash.get(name)

    def acknowledge_txt(self, name: str) -> None:
        """.txt 讀取失敗時呼叫，避免同一個錯誤每秒都跳出來；使用者再次存檔 .txt 後才會重新偵測。"""
        self._txt_hash[name] = _hash(self.txt_path(name).read_bytes())

    def load_txt(self, name: str) -> LangFile:
        """讀取被記事本修改過的 .txt。非 UTF-8 拋出 UnicodeDecodeError，格式錯誤拋出 LangFormatError。"""
        raw = self.txt_path(name).read_bytes()
        lf = langfile.parse(langcrypt.normalize_text(raw))
        self._txt_hash[name] = _hash(raw)
        return lf

    # ---------- 部署 ----------

    def deploy(self, name: str, elevate: Callable[[Path, Path], bool]) -> DeployResult:
        src, dst = self.lang_dir / name, self.installed_dir / name
        data = src.read_bytes()
        backup = None
        if dst.exists():
            if dst.read_bytes() == data:
                return DeployResult(True, False, "PL/SQL Developer 裡的檔案已經是最新的")
            backup = self.backup(dst, prefix="installed_")
        try:
            langfile.atomic_write(dst, data)
        except PermissionError:
            try:
                ok = elevate(src, dst)
            except Exception as e:  # 提升權限的過程出任何錯都要變成看得見的失敗
                return DeployResult(False, False, f"沒有寫入：提升權限時發生錯誤（{e}）。修改仍保留在工作區。", backup)
            if not ok:
                return DeployResult(False, False, "沒有寫入：使用者取消了 UAC，或系統管理員複製失敗。修改仍保留在工作區。", backup)
        if not dst.exists() or dst.read_bytes() != data:
            return DeployResult(False, False, f"寫入後讀回的內容不一致。原檔備份在：{backup}", backup)
        return DeployResult(True, True, "已部署，重新啟動 PL/SQL Developer 後生效。", backup)
