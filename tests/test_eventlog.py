import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta, timezone

from pllangstudio import __version__, appconfig, eventlog


def test_log_returns_event_id_and_is_queryable(events_db):
    eid = eventlog.info("存檔", "已存檔 Taiwan.lang")
    assert isinstance(eid, int)
    [e] = eventlog.query()
    assert (e.id, e.level, e.category, e.message, e.app_version) == (eid, "INFO", "存檔", "已存檔 Taiwan.lang", __version__)
    assert e.level_label == "資訊"
    assert abs(e.time - datetime.now().astimezone()) < timedelta(minutes=1)


def test_error_records_traceback(events_db):
    try:
        raise OSError("磁碟已滿")
    except OSError as exc:
        eid = eventlog.error("存檔", "存檔失敗", exc)
    [e] = eventlog.query(keyword=f"#{eid}")
    assert e.level == "ERROR" and "Traceback" in e.detail and "OSError: 磁碟已滿" in e.detail


def test_message_with_braces_is_kept(events_db):
    eventlog.info("批次修改", "規則 {0} 與 {name}")
    assert eventlog.query()[0].message == "規則 {0} 與 {name}"


def test_query_filters_by_group_since_and_keyword(events_db):
    eventlog.info("工作區", "開啟工作區")
    eventlog.warning("存檔", "有警告")
    eventlog.error("部署", "部署失敗 50%")
    eventlog.critical("未預期的錯誤", "ZeroDivisionError")
    assert [e.level for e in eventlog.query({"error"})] == ["CRITICAL", "ERROR"]
    assert [e.category for e in eventlog.query({"warning", "info"})] == ["存檔", "工作區"]
    assert [e.message for e in eventlog.query(keyword="50%")] == ["部署失敗 50%"]
    assert [e.category for e in eventlog.query(keyword="部署")] == ["部署"]
    assert eventlog.query(set()) == []
    assert eventlog.query(since=datetime.now() + timedelta(hours=1)) == []


def test_query_by_event_id_ignores_other_filters(events_db):
    eid = eventlog.info("工作區", "開啟")
    assert [e.id for e in eventlog.query({"error"}, keyword=f"#{eid}")] == [eid]


def test_corrupt_database_is_quarantined(tmp_path):
    db = tmp_path / "events.db"
    db.write_bytes(b"not a sqlite database" * 100)
    eventlog.setup(db)
    try:
        assert (tmp_path / "events.db.corrupt").exists()
        assert eventlog.info("程式", "啟動") is not None
    finally:
        eventlog.shutdown()


def test_unusable_location_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    eventlog.setup(blocker / "events.db")  # 上層是檔案，建不了資料夾
    try:
        assert eventlog.info("程式", "啟動") is None
        assert eventlog.query() == []
    finally:
        eventlog.shutdown()


def test_retention_defaults_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert appconfig.log_retention() == {"info": 90, "warning": 90, "error": 30}
    appconfig.remember_log_retention({"info": 7, "warning": 14, "error": 3650})
    assert appconfig.log_retention() == {"info": 7, "warning": 14, "error": 3650}
    (tmp_path / "PLLangStudio" / "app.json").write_text(
        '{"log_days_info": 0, "log_days_warning": "9", "log_days_error": true}', encoding="utf-8")
    assert appconfig.log_retention() == {"info": 90, "warning": 90, "error": 30}


def test_retention_keeps_other_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    appconfig.remember_theme("dark")
    appconfig.remember_log_retention({"info": 10, "warning": 20, "error": 5})
    assert appconfig.theme_mode() == "dark"


def test_default_path_under_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert eventlog.default_path() == tmp_path / "PLLangStudio" / "events.db"


def test_purge_by_group(events_db):
    for level in ("INFO", "WARNING", "ERROR", "CRITICAL"):
        eventlog.log(level, "測試", level)
    later = datetime.now(timezone.utc) + timedelta(days=31)
    assert eventlog.purge({"info": 90, "warning": 90, "error": 30}, now=later) == 2
    assert {e.level for e in eventlog.query()} == {"INFO", "WARNING"}
    assert eventlog.purge({"info": 30, "warning": 90, "error": 30}, now=later) == 1
    assert [e.level for e in eventlog.query()] == ["WARNING"]


def test_setup_purges_with_retention(tmp_path):
    db = tmp_path / "events.db"
    eventlog.setup(db)
    eventlog.error("測試", "四十天前的錯誤")
    eventlog.shutdown()
    conn = sqlite3.connect(db)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="milliseconds")
    conn.execute("UPDATE events SET time = ?", (old,))
    conn.commit()
    conn.close()
    eventlog.setup(db, {"info": 90, "warning": 90, "error": 30})
    try:
        assert eventlog.query() == []
    finally:
        eventlog.shutdown()


def test_stats(events_db):
    eventlog.info("程式", "啟動")
    count, size = eventlog.stats()
    assert count == 1 and size > 0
