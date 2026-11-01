"""內附的語言檔：PL/SQL Developer 沒有 Taiwan.lang 時，從程式資源放進工作區（見 ADR-0022）。"""

from pllangstudio import resources
from pllangstudio.core import langcrypt, langfile
from pllangstudio.core.workspace import Workspace, bundled_lang


def test_bundled_taiwan_is_valid_lang_file():
    lf = langfile.load(resources.path("Taiwan.lang"))
    assert lf.header[0] == ":Taiwan"
    assert lf.entries


def test_bundled_lang_only_for_known_files():
    assert bundled_lang("Taiwan.lang") == resources.path("Taiwan.lang")
    assert bundled_lang("Chinese.lang") is None


def test_add_bundled_copies_into_workspace(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    ws.settings.plsql_lang_dir = str(tmp_path / "Languages")  # 沒有 Taiwan.lang 的 Languages 目錄
    assert ws.add_bundled("Taiwan.lang")
    data = resources.path("Taiwan.lang").read_bytes()
    assert (ws.lang_dir / "Taiwan.lang").read_bytes() == data
    assert ws.txt_path("Taiwan.lang").read_bytes() == langcrypt.decrypt(data)
    assert [(i.name, i.deployed) for i in ws.list_workspace()] == [("Taiwan.lang", False)]


def test_add_bundled_never_overwrites_workspace_file(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    (ws.lang_dir / "Taiwan.lang").write_bytes(b"edited")
    assert not ws.add_bundled("Taiwan.lang")
    assert (ws.lang_dir / "Taiwan.lang").read_bytes() == b"edited"


def test_add_bundled_unknown_name(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    assert not ws.add_bundled("Chinese.lang")
    assert not (ws.lang_dir / "Chinese.lang").exists()
