import shutil

import pytest

from langdata import LANG_DIR, needs_lang_dir
from pllangstudio.core import langfile
from pllangstudio.core.langfile import Field, LangFormatError
from pllangstudio.core.workspace import ImportConflict, Workspace

pytestmark = needs_lang_dir


@pytest.fixture
def installed(tmp_path):
    """模擬 PL/SQL Developer 的 Languages 目錄（只放兩個檔案）。"""
    d = tmp_path / "Languages"
    d.mkdir()
    for n in ["Chinese.lang", "Taiwan.lang"]:
        shutil.copy(LANG_DIR / n, d / n)
    return d


@pytest.fixture
def ws(tmp_path, installed):
    w = Workspace(tmp_path / "workspace")
    w.settings.plsql_lang_dir = str(installed)
    return w


def test_creates_structure_and_default_glossary(ws):
    assert ws.lang_dir.is_dir() and ws.txt_dir.is_dir() and ws.backup_dir.is_dir()
    assert any(r.find == "會話" for r in ws.load_glossary().rules)


def test_settings_roundtrip(ws, tmp_path):
    ws.settings.slave = "Chinese.lang"
    ws.save_settings()
    assert Workspace(ws.root).settings.slave == "Chinese.lang"


def test_import_creates_lang_and_txt(ws):
    ws.import_lang("Taiwan.lang")
    assert (ws.lang_dir / "Taiwan.lang").read_bytes() == (LANG_DIR / "Taiwan.lang").read_bytes()
    assert ws.txt_path("Taiwan.lang").read_text(encoding="utf-8-sig").startswith(":Taiwan")
    assert [i.name for i in ws.list_installed() if i.imported] == ["Taiwan.lang"]
    assert ws.list_workspace()[0].deployed is True


def test_import_conflict(ws):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    with pytest.raises(ImportConflict):
        ws.import_lang("Taiwan.lang")
    ws.import_lang("Taiwan.lang", overwrite=True)
    assert len(list(ws.backup_dir.glob("Taiwan_*.lang"))) >= 2


def test_save_backs_up_and_regenerates_txt(ws):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    assert ws.load("Taiwan.lang").entries[1].target[Field.CAPTION] == ["改過"]
    assert "改過" in ws.txt_path("Taiwan.lang").read_text(encoding="utf-8-sig")
    assert list(ws.backup_dir.glob("Taiwan_*.lang"))
    assert not ws.txt_changed("Taiwan.lang")


def test_txt_external_edit_detected_and_loaded(ws):
    ws.import_lang("Taiwan.lang")
    ws.sync_txt("Taiwan.lang", ws.load("Taiwan.lang"))
    p = ws.txt_path("Taiwan.lang")
    # 模擬記事本：改一個字並存成 LF 換行
    p.write_bytes(p.read_bytes().replace("&取消".encode(), "&取消X".encode(), 1).replace(b"\r\n", b"\n"))
    assert ws.txt_changed("Taiwan.lang")
    lf = ws.load_txt("Taiwan.lang")
    assert any(e.target[Field.CAPTION] == ["&取消X"] for e in lf.entries)
    assert not ws.txt_changed("Taiwan.lang")


def test_txt_broken_format_rejected(ws):
    ws.import_lang("Taiwan.lang")
    p = ws.txt_path("Taiwan.lang")
    p.write_bytes(p.read_bytes().replace("&取消\r\n".encode(), b"", 1))
    with pytest.raises(LangFormatError):
        ws.load_txt("Taiwan.lang")


def test_txt_non_utf8_rejected(ws):
    ws.import_lang("Taiwan.lang")
    ws.txt_path("Taiwan.lang").write_bytes("中文".encode("big5"))
    with pytest.raises(UnicodeDecodeError):
        ws.load_txt("Taiwan.lang")


def test_deploy_writes_and_verifies(ws, installed):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    res = ws.deploy("Taiwan.lang", elevate=lambda s, d: pytest.fail("不應該需要 UAC"))
    assert res.ok and res.changed and res.backup.exists()
    assert langfile.load(installed / "Taiwan.lang").entries[1].target[Field.CAPTION] == ["改過"]
    assert ws.deploy("Taiwan.lang", elevate=lambda s, d: False).changed is False


def test_deploy_uses_elevation_on_permission_error(ws, installed, monkeypatch):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)

    def deny(path, data):
        raise PermissionError
    monkeypatch.setattr(langfile, "atomic_write", deny)
    calls = []

    def fake_elevate(src, dst):
        calls.append((src, dst))
        shutil.copy(src, dst)
        return True
    assert ws.deploy("Taiwan.lang", elevate=fake_elevate).ok
    assert calls


def test_deploy_cancelled_uac(ws, monkeypatch):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(1, Field.CAPTION, ["改過"])
    ws.save("Taiwan.lang", lf)
    monkeypatch.setattr(langfile, "atomic_write", lambda p, d: (_ for _ in ()).throw(PermissionError()))
    res = ws.deploy("Taiwan.lang", elevate=lambda s, d: False)
    assert not res.ok and "工作區" in res.message


def test_txt_differs_and_backup(ws):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    assert ws.txt_differs("Taiwan.lang", lf) is False
    p = ws.txt_path("Taiwan.lang")
    p.write_bytes(p.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    assert ws.txt_differs("Taiwan.lang", lf) is True
    p.write_bytes(b"\xff\xfe\x00bad")
    assert ws.txt_differs("Taiwan.lang", lf) is True
    b = ws.backup_txt("Taiwan.lang")
    assert b.parent == ws.backup_dir and b.read_bytes() == b"\xff\xfe\x00bad"


def test_import_overwrite_backs_up_edited_txt(ws, installed):
    ws.import_lang("Taiwan.lang")
    p = ws.txt_path("Taiwan.lang")
    p.write_bytes(p.read_bytes().replace("&取消".encode(), "&取消N".encode(), 1))
    edited = p.read_bytes()
    # 讓 PL/SQL 目錄的版本和工作區的 .lang 不同，才會走到覆蓋流程
    lf = ws.load("Taiwan.lang")
    lf.set_target(0, Field.CAPTION, ["x"])
    langfile.save(ws.lang_dir / "Taiwan.lang", lf)
    ws.import_lang("Taiwan.lang", overwrite=True)
    assert any(b.read_bytes() == edited for b in ws.backup_dir.glob("Taiwan_*.txt"))


def test_empty_settings_and_glossary_fall_back(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "settings.json").write_text("", encoding="utf-8")
    (root / "glossary.json").write_text("", encoding="utf-8")
    w = Workspace(root)
    assert w.settings.master == "Chinese.lang"
    assert any(r.find == "會話" for r in w.load_glossary().rules)
    assert (root / "settings.json.corrupt").exists() and (root / "glossary.json.corrupt").exists()


def test_empty_app_json_gives_no_workspace(tmp_path, monkeypatch):
    from pllangstudio import appconfig
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = tmp_path / "PLLangStudio"
    d.mkdir()
    (d / "app.json").write_text("", encoding="utf-8")
    assert appconfig.last_workspace() is None
    assert (d / "app.json.corrupt").exists()


def test_deploy_elevate_exception_is_failed_result(ws, installed, monkeypatch):
    ws.import_lang("Taiwan.lang")
    lf = ws.load("Taiwan.lang")
    lf.set_target(0, Field.CAPTION, ["x"])
    ws.save("Taiwan.lang", lf)

    def deny(*a, **k):
        raise PermissionError

    monkeypatch.setattr(langfile, "atomic_write", deny)

    def boom(s, d):
        raise OSError("炸了")

    res = ws.deploy("Taiwan.lang", boom)
    assert res.ok is False and "炸了" in res.message
