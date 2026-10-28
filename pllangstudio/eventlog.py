"""事件紀錄：用 Loguru 記錄操作過程與錯誤，存進 SQLite，供事件檢視器查詢與匯出（見 ADR-0017）。

紀錄本身失敗時（資料庫壞掉、被鎖、沒有權限）一律吞掉，不可影響主程式。
"""

from __future__ import annotations

import sqlite3
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from . import __version__, appconfig

GROUP_OF_LEVEL = {"TRACE": "info", "DEBUG": "info", "INFO": "info", "SUCCESS": "info",
                  "WARNING": "warning", "ERROR": "error", "CRITICAL": "error"}
GROUP_LABEL = {"info": "資訊", "warning": "警告", "error": "錯誤"}
LEVEL_LABEL = {"TRACE": "資訊", "DEBUG": "資訊", "INFO": "資訊", "SUCCESS": "資訊",
               "WARNING": "警告", "ERROR": "錯誤", "CRITICAL": "嚴重錯誤"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_time ON events(time);
CREATE INDEX IF NOT EXISTS events_level ON events(level);
"""
_COLUMNS = "id, time, level, category, message, detail, app_version"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_db_path: Path | None = None
_handler_id: int | None = None
_last_id: int | None = None


@dataclass(frozen=True)
class Event:
    id: int
    time: datetime  # 本地時間
    level: str
    category: str
    message: str
    detail: str
    app_version: str

    @property
    def level_label(self) -> str:
        return LEVEL_LABEL.get(self.level, self.level)


def _utc(dt: datetime) -> str:
    """存成 UTC 字串，字串大小順序就是時間順序；沒有時區的視為本地時間。"""
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def default_path() -> Path:
    return appconfig.data_dir() / "events.db"


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)  # 自動提交
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # 檢視器讀取時不擋住寫入
        conn.executescript(_SCHEMA)
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("quick_check 失敗")
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def setup(db_path: Path, retention: dict[str, int] | None = None) -> None:
    """啟用事件紀錄。資料庫壞了就改名成 .corrupt 再重建；開不了就只是不記錄。"""
    global _conn, _db_path, _handler_id
    shutdown()
    db_path = Path(db_path)
    try:
        try:
            conn = _open(db_path)
        except sqlite3.DatabaseError:
            appconfig.quarantine(db_path)
            for suffix in ("-wal", "-shm"):
                db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
            conn = _open(db_path)
    except (OSError, sqlite3.Error):
        conn = None
    _conn, _db_path = conn, db_path
    logger.remove()  # 視窗程式沒有主控台，不要 Loguru 預設的 stderr 輸出
    _handler_id = logger.add(_sink, level="DEBUG", catch=False)
    if retention:
        purge(retention)


def shutdown() -> None:
    """停止記錄並關閉資料庫（測試結束、程式結束時呼叫）。"""
    global _conn, _db_path, _handler_id
    if _handler_id is not None:
        logger.remove(_handler_id)
        _handler_id = None
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn, _db_path = None, None


def _sink(message) -> None:
    global _last_id
    r = message.record
    detail = ""
    if r["exception"] is not None:
        t, v, tb = r["exception"]
        detail = "".join(traceback.format_exception(t, v, tb))
    row = (_utc(r["time"]), r["level"].name, str(r["extra"].get("category", "")), r["message"], detail, __version__)
    with _lock:
        _last_id = None
        if _conn is None:
            return
        try:
            _last_id = _conn.execute(
                "INSERT INTO events (time, level, category, message, detail, app_version) VALUES (?, ?, ?, ?, ?, ?)",
                row).lastrowid
        except sqlite3.Error:
            pass


def log(level: str, category: str, message: str, exc=None) -> int | None:
    """寫一筆事件，回傳事件編號；沒有啟用或寫入失敗時回傳 None。exc 可以是例外物件或 (type, value, tb)。"""
    global _last_id
    _last_id = None
    logger.bind(category=category).opt(exception=exc, depth=1).log(level, message)
    return _last_id


def info(category: str, message: str) -> int | None:
    return log("INFO", category, message)


def success(category: str, message: str) -> int | None:
    return log("SUCCESS", category, message)


def warning(category: str, message: str) -> int | None:
    return log("WARNING", category, message)


def error(category: str, message: str, exc=None) -> int | None:
    return log("ERROR", category, message, exc)


def critical(category: str, message: str, exc=None) -> int | None:
    return log("CRITICAL", category, message, exc)


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _event(row) -> Event:
    eid, time, level, category, message, detail, version = row
    return Event(eid, datetime.fromisoformat(time).astimezone(), level, category, message, detail, version)


def query(groups=("info", "warning", "error"), since: datetime | None = None, keyword: str = "",
          limit: int = 5000) -> list[Event]:
    """查詢事件，新的在前。keyword 是 #數字 時只依事件編號找，忽略其他條件。"""
    kw = keyword.strip()
    if kw.startswith("#") and kw[1:].isdigit():
        sql, args = f"SELECT {_COLUMNS} FROM events WHERE id = ?", [int(kw[1:])]
    else:
        levels = [lv for lv, g in GROUP_OF_LEVEL.items() if g in groups]
        if not levels:
            return []
        where, args = [f"level IN ({','.join('?' * len(levels))})"], list(levels)
        if since is not None:
            where.append("time >= ?")
            args.append(_utc(since))
        if kw:
            where.append("(message LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' OR detail LIKE ? ESCAPE '\\')")
            args += [_like(kw)] * 3
        sql = f"SELECT {_COLUMNS} FROM events WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?"
        args.append(limit)
    with _lock:
        if _conn is None:
            return []
        try:
            rows = _conn.execute(sql, args).fetchall()
        except sqlite3.Error:
            return []
    return [_event(r) for r in rows]


def purge(retention: dict[str, int], now: datetime | None = None) -> int:
    """依各等級群組的保留天數刪除過期紀錄，回傳刪除筆數。"""
    now = now or datetime.now(timezone.utc)
    removed = 0
    with _lock:
        if _conn is None:
            return 0
        try:
            for group, days in retention.items():
                levels = [lv for lv, g in GROUP_OF_LEVEL.items() if g == group]
                removed += _conn.execute(
                    f"DELETE FROM events WHERE time < ? AND level IN ({','.join('?' * len(levels))})",
                    [_utc(now - timedelta(days=days)), *levels]).rowcount
        except sqlite3.Error:
            pass
    return removed


def stats() -> tuple[int, int]:
    """回傳（總筆數, 資料庫檔案大小 bytes，含 -wal）。"""
    with _lock:
        if _conn is None or _db_path is None:
            return 0, 0
        try:
            count = _conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        except sqlite3.Error:
            count = 0
        size = sum(p.stat().st_size for p in (_db_path, _db_path.with_name(_db_path.name + "-wal")) if p.exists())
    return count, size
