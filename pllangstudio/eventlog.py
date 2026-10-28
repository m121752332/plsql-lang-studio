"""事件紀錄：用 Loguru 記錄操作過程與錯誤，存進 SQLite，供事件檢視器查詢與匯出（見 ADR-0017）。

紀錄本身失敗時（資料庫壞掉、被鎖、沒有權限）一律吞掉，不可影響主程式。
"""

from __future__ import annotations

import contextlib
import io
import os
import platform
import sqlite3
import sys
import threading
import traceback
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from loguru import logger

from . import __version__, appconfig
from .core import langfile

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
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER NOT NULL,
    started TEXT NOT NULL,
    ended TEXT,
    abnormal INTEGER NOT NULL DEFAULT 0
);
"""
_COLUMNS = "id, time, level, category, message, detail, app_version"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_db_path: Path | None = None
_handler_id: int | None = None
_last_id: int | None = None
_session_id: int | None = None


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


@dataclass(frozen=True)
class Summary:
    counts: dict[str, int]  # 等級群組（info／warning／error）→ 筆數
    oldest: datetime | None  # 最舊一筆的本地時間；沒有紀錄時是 None
    size: int  # 資料庫檔案大小 bytes（含 -wal）

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _utc(dt: datetime) -> str:
    """存成 UTC 字串，字串大小順序就是時間順序；沒有時區的視為本地時間。"""
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def default_path() -> Path:
    return appconfig.data_dir() / "events.db"


def log_dir() -> Path:
    """資料庫所在的資料夾（「開啟紀錄資料夾」用）。"""
    return (_db_path or default_path()).parent


def backup_dir() -> Path:
    """初始化前的備份放在資料庫旁的 backup 資料夾。"""
    return log_dir() / "backup"


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None,  # 自動提交
                           timeout=1)  # 被鎖住時最多等 1 秒，不拖慢啟動
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
        except sqlite3.OperationalError:
            raise  # 被其他實例鎖住不是損毀，交給外層：只是不記錄
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
    global _conn, _db_path, _handler_id, _session_id
    if _handler_id is not None:
        logger.remove(_handler_id)
        _handler_id = None
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn, _db_path = None, None
        _session_id = None


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
            if retention:  # 已結束的工作階段保留到最長的保留天數
                _conn.execute("DELETE FROM sessions WHERE ended IS NOT NULL AND ended < ?",
                              (_utc(now - timedelta(days=max(retention.values()))),))
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


def summary() -> Summary:
    """各等級群組的筆數、最舊一筆的時間與檔案大小（配置頁顯示用）。"""
    counts = dict.fromkeys(GROUP_LABEL, 0)
    oldest = None
    with _lock:
        if _conn is not None:
            try:
                for level, n in _conn.execute("SELECT level, COUNT(*) FROM events GROUP BY level"):
                    group = GROUP_OF_LEVEL.get(level)
                    if group:
                        counts[group] += n
                first = _conn.execute("SELECT MIN(time) FROM events").fetchone()[0]
                oldest = datetime.fromisoformat(first).astimezone() if first else None
            except sqlite3.Error:
                pass
    return Summary(counts, oldest, stats()[1])


def _cutoff(days: int, now: datetime | None) -> str:
    return _utc((now or datetime.now(timezone.utc)) - timedelta(days=days))


def count_older_than(days: int, now: datetime | None = None) -> int:
    with _lock:
        if _conn is None:
            return 0
        try:
            return _conn.execute("SELECT COUNT(*) FROM events WHERE time < ?", (_cutoff(days, now),)).fetchone()[0]
        except sqlite3.Error:
            return 0


def delete_older_than(days: int, now: datetime | None = None) -> int:
    """不分等級刪除 days 天前的紀錄，事件編號不重設；回傳刪除筆數。"""
    with _lock:
        if _conn is None:
            return 0
        try:
            return _conn.execute("DELETE FROM events WHERE time < ?", (_cutoff(days, now),)).rowcount
        except sqlite3.Error:
            return 0


def compact() -> None:
    """刪除後壓縮資料庫，檔案才會真的變小。其他實例正在用時會失敗，就略過。"""
    with _lock:
        if _conn is None:
            return
        try:
            _conn.execute("VACUUM")
            _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass


def _rollback() -> None:
    """復原交易；復原本身失敗時不可蓋掉原本的錯誤。呼叫端要持有 _lock。"""
    if _conn is not None and _conn.in_transaction:
        with contextlib.suppress(sqlite3.Error):
            _conn.execute("ROLLBACK")


def reset(now: datetime | None = None) -> tuple[int, Path]:
    """初始化：先把全部紀錄備份成 zip，再清空並把事件編號歸零。

    備份失敗就拋出 OSError，什麼都不刪；回傳（刪除筆數, 備份檔）。
    """
    if _conn is None:
        raise RuntimeError("事件紀錄目前無法使用")
    now = now or datetime.now()
    dest = backup_dir() / f"events-{now:%Y%m%d-%H%M%S}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 讀取、備份、刪除放在同一個交易：BEGIN IMMEDIATE 先取得寫入鎖，備份之後才寫入的紀錄不會被刪掉。
    # export_zip 不寫紀錄，持有 _lock 時呼叫是安全的；寫紀錄的 info、compact 要等離開鎖之後。
    with _lock:
        if _conn is None:
            raise RuntimeError("事件紀錄目前無法使用")
        try:
            _conn.execute("BEGIN IMMEDIATE")
            rows = _conn.execute(f"SELECT {_COLUMNS} FROM events ORDER BY id DESC").fetchall()  # 讀取失敗要拋出，不可當成沒有紀錄
            events = [_event(r) for r in rows]
            export_zip(events, dest)
            _conn.execute("DELETE FROM events")
            _conn.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")  # 編號從 1 重新開始
            _conn.execute("DELETE FROM sessions WHERE ended IS NOT NULL")  # 還沒結束的（含其他實例）要留著，才偵測得到異常結束
            _conn.execute("COMMIT")
        except sqlite3.Error as e:
            _rollback()
            raise RuntimeError(f"無法清空事件紀錄：{e}") from e
        except BaseException:
            _rollback()
            raise
    compact()
    info("事件紀錄", f"事件紀錄已初始化，刪除 {len(events):,} 筆；原紀錄備份在：{dest}")
    return len(events), dest


def format_event(e: Event) -> str:
    head = f"#{e.id}  {e.time:%Y-%m-%d %H:%M:%S}  {e.level_label}  [{e.category}]  {e.message}"
    return head + (f"\n{e.detail.rstrip()}" if e.detail else "")


def system_info(extra: dict[str, str] | None = None) -> dict[str, str]:
    """回報問題時附上的環境資訊；Qt 版本由畫面層透過 extra 帶入（本模組不 import Qt）。"""
    info = {"程式版本": __version__, "Python": platform.python_version(), "作業系統": platform.platform()}
    info.update(extra or {})
    return info


def export_name(now: datetime) -> str:
    return f"PLLangStudio-events-{now:%Y%m%d-%H%M%S}.zip"


def export_zip(events: list[Event], dest: Path, extra: dict[str, str] | None = None) -> None:
    """匯出成 zip（events.txt＋system.txt），不含語言檔內容。先寫 .tmp 再換檔。"""
    lines = [f"{k}：{v}" for k, v in system_info(extra).items()]
    lines += [f"匯出時間：{datetime.now():%Y-%m-%d %H:%M:%S}", f"筆數：{len(events)}"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("events.txt", "\n\n".join(format_event(e) for e in events) + "\n")
        z.writestr("system.txt", "\n".join(lines) + "\n")
    langfile.atomic_write(Path(dest), buf.getvalue())


def with_event_id(text: str, event_id: int | None) -> str:
    """錯誤對話框的訊息附上事件編號，回報問題時用。"""
    return text if event_id is None else f"{text}\n\n事件編號 #{event_id}"


def crash_message(event_id: int | None) -> str:
    text = "發生未預期的錯誤。"
    if event_id is not None:
        text += f"（事件編號 #{event_id}）\n\n回報問題時請提供此編號，並從「配置 ▸ 事件檢視器」匯出紀錄。"
    return text


def _pid_alive(pid: int) -> bool:
    """程序是否還在執行；用來分辨「另一個實例還開著」和「上次異常結束」。"""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def start_session(pid: int | None = None, alive: Callable[[int], bool] | None = None) -> list[int]:
    """記下這次的工作階段。先找出上次沒有正常結束、程序也已不存在的，各記一筆警告；回傳那些警告的事件編號。"""
    global _session_id
    pid = os.getpid() if pid is None else pid
    alive = alive or _pid_alive
    now = _utc(datetime.now(timezone.utc))
    found: list[tuple[str, int | None]] = []
    with _lock:
        if _conn is None:
            return []
        try:
            for sid, other, started in _conn.execute(
                    "SELECT id, pid, started FROM sessions WHERE ended IS NULL").fetchall():
                if other != pid and alive(other):  # 自己還沒寫入工作階段，同 pid 的未結束紀錄必是已死的舊實例（pid 被重用）
                    continue
                last = _conn.execute("SELECT MAX(id) FROM events WHERE time >= ?", (started,)).fetchone()[0]
                _conn.execute("UPDATE sessions SET ended = ?, abnormal = 1 WHERE id = ?", (now, sid))
                found.append((started, last))
            _session_id = _conn.execute("INSERT INTO sessions (pid, started) VALUES (?, ?)", (pid, now)).lastrowid
        except sqlite3.Error:
            return []
    ids = []
    for started, last in found:
        tail = f"，最後一筆紀錄 #{last}" if last else ""
        eid = warning("程式", f"上次程式未正常結束（開始於 {datetime.fromisoformat(started).astimezone():%Y-%m-%d %H:%M:%S}{tail}）")
        if eid is not None:
            ids.append(eid)
    return ids


def end_session() -> None:
    """正常結束時標記工作階段，下次啟動才不會當成異常結束。"""
    global _session_id
    with _lock:
        if _conn is not None and _session_id is not None:
            try:
                _conn.execute("UPDATE sessions SET ended = ? WHERE id = ?",
                              (_utc(datetime.now(timezone.utc)), _session_id))
            except sqlite3.Error:
                pass
        _session_id = None


def install_excepthook(on_crash: Callable[[int | None], None]) -> None:
    """未預期的例外記成嚴重錯誤，再交給 on_crash 顯示事件編號。"""
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        eid = critical("未預期的錯誤", f"{exc_type.__name__}: {exc}", (exc_type, exc, tb))
        try:
            on_crash(eid)
        except Exception:
            pass
    sys.excepthook = hook
