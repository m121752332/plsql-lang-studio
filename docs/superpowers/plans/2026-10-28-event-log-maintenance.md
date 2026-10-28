# 事件紀錄維護功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「配置 ▸ 紀錄事件」頁加入初始化（編號重設、先備份）、刪除超過 N 天、壓縮資料庫與統計、開啟紀錄資料夾，並偵測上次異常結束、讓錯誤對話框可複製事件編號或直接開啟事件檢視器。

**Architecture:** 資料操作都放在 `pllangstudio/eventlog.py`（不依賴 Qt）：`summary`、`count_older_than`、`delete_older_than`、`compact`、`reset`、工作階段（`sessions` 資料表＋`start_session`／`end_session`）。畫面層：新的 `ui/error_box.py` 建立有事件編號的錯誤對話框；`MainWindow._info` 改用它，`show_events(event_id)` 可直接列出某一筆；`LogPage` 加上維護區塊。

**Tech Stack:** Python 3.14、PySide6、Loguru、sqlite3、pytest＋pytest-qt＋xdist、uv。

**Spec:** 本計畫的設計已在對話中經使用者同意（2026-10-28），以第一階段的 [docs/superpowers/specs/2026-10-28-event-log-design.md](../specs/2026-10-28-event-log-design.md) 為基礎延伸，決策記錄在 Task 5 新增的 ADR-0018。同意的設計重點：

1. 初始化事件紀錄：確認 → 先把全部紀錄備份成 zip 到資料庫旁的 `backup\events-日期時間.zip` → **備份失敗就中止不刪除** → 清空並把 AUTOINCREMENT 歸零 → 壓縮 → 第一筆為「#1 事件紀錄已初始化…」。
2. 刪除超過 N 天（預設 30，範圍 1～3650，不分等級，編號不重設）：確認時顯示筆數，刪除後壓縮並記一筆。
3. 偵測上次異常結束：工作階段資料表記 pid 與開始時間，正常結束時標記；下次啟動發現未結束且程序已不存在者，記警告「上次程式未正常結束（開始於 …，最後一筆紀錄 #N）」；同時開兩個實例不誤報。
4. 手動刪除、立即清除、初始化後執行 VACUUM；啟動時自動清除不壓縮。頁面顯示資訊／警告／錯誤筆數、最舊日期、大小。
5. 有事件編號的錯誤對話框（含未預期錯誤）多「複製事件編號」「開啟事件檢視器」按鈕；後者開啟檢視器並以 `#編號` 搜尋。
6. 「開啟紀錄資料夾」按鈕。備份 zip 不自動清除。

## Global Constraints

- 一律用 uv：`uv run pytest`；不可直接呼叫系統 `python`／`pip`。
- `core/` 與 `eventlog.py` 不可 import PySide6。
- 介面文字、註解、ADR 用繁體中文（台灣用語），遵守 CONTEXT.md 用詞。
- 含中文的檔案只能用 Write／Edit 工具修改，不可用 `sed -i`、heredoc、`echo` 寫入。
- 測試必須能平行執行：資料庫放 `tmp_path`（用 `events_db` fixture），不可寫入真實的 `%APPDATA%` 或 Languages 目錄；會呼叫 `os.startfile` 或對話框的地方一律可注入、測試時換掉。
- 紀錄本身失敗不可讓主程式出錯；唯一例外是 `reset()`：備份失敗或資料庫無法使用時必須拋出例外，讓畫面告知使用者「沒有刪除任何紀錄」。
- 刪除天數範圍沿用 `appconfig.LOG_DAYS_RANGE = (1, 3650)`，預設 30 天。
- 分支：`feature/event-log`。Commit 用 Conventional Commits＋繁體中文，結尾空一行加 `Co-Authored-By:`（寫實際執行的模型）。不 push。

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `pllangstudio/eventlog.py` | 修改 | `Summary`、`summary`、`log_dir`、`backup_dir`、`count_older_than`、`delete_older_than`、`compact`、`reset`；`sessions` 資料表、`start_session`、`end_session`、`_pid_alive` |
| `pllangstudio/ui/error_box.py` | 新增 | 有事件編號的錯誤對話框 |
| `pllangstudio/ui/main_window.py` | 修改 | `_info(event_id=)`、`_error` 傳編號、`show_events(event_id=None)` |
| `pllangstudio/ui/settings_dialog.py` | 修改 | `LogPage` 維護區塊 |
| `pllangstudio/__main__.py` | 修改 | 工作階段、未預期錯誤對話框 |
| `tests/test_eventlog.py` | 修改 | 新增核心測試 |
| `tests/ui/test_error_box.py` | 新增 | 錯誤對話框測試 |
| `tests/ui/test_main_window.py`、`tests/ui/test_settings_dialog.py` | 修改 | 畫面測試 |
| `docs/adr/0018-event-log-maintenance.md`、`README.md`、`CONTEXT.md`、`AGENTS.md` | 新增／修改 | 文件 |

---

### Task 1: eventlog 維護函式（統計、刪除、壓縮、初始化）

**Files:**
- Modify: `pllangstudio/eventlog.py`
- Test: `tests/test_eventlog.py`

**Interfaces:**
- Consumes: 既有 `_lock`、`_conn`、`_db_path`、`_utc`、`default_path`、`query(groups, since, keyword, limit)`、`export_zip(events, dest, extra=None)`、`info`、`stats() -> (count, size)`、`GROUP_LABEL`、`GROUP_OF_LEVEL`
- Produces:
  - `@dataclass(frozen=True) Summary(counts: dict[str, int], oldest: datetime | None, size: int)`，屬性 `total -> int`；`counts` 的 key 固定為 `"info"`、`"warning"`、`"error"`
  - `summary() -> Summary`
  - `log_dir() -> Path`（資料庫所在資料夾）、`backup_dir() -> Path`（`log_dir() / "backup"`）
  - `count_older_than(days: int, now: datetime | None = None) -> int`
  - `delete_older_than(days: int, now: datetime | None = None) -> int`
  - `compact() -> None`
  - `reset(now: datetime | None = None) -> tuple[int, Path]`（刪除筆數、備份檔路徑；備份失敗拋 `OSError`，資料庫無法使用或清空失敗拋 `RuntimeError`）

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_eventlog.py` 的 import 區加上 `import pytest`（放在標準函式庫 import 之後、`from pllangstudio ...` 之前，空一行分組）。檔尾加：

```python
def test_summary_counts_groups_and_oldest(events_db):
    eventlog.info("測試", "一")
    eventlog.success("測試", "二")
    eventlog.warning("測試", "三")
    eventlog.critical("測試", "四")
    s = eventlog.summary()
    assert s.counts == {"info": 2, "warning": 1, "error": 1} and s.total == 4
    assert abs(s.oldest - datetime.now().astimezone()) < timedelta(minutes=1)
    assert s.size > 0


def test_summary_when_empty(events_db):
    s = eventlog.summary()
    assert s.total == 0 and s.oldest is None


def test_delete_older_than_keeps_ids(events_db):
    first = eventlog.info("測試", "舊的")
    eventlog.error("測試", "舊的錯誤")
    later = datetime.now(timezone.utc) + timedelta(days=31)
    assert eventlog.count_older_than(30, now=later) == 2
    assert eventlog.count_older_than(32, now=later) == 0
    assert eventlog.delete_older_than(30, now=later) == 2
    assert eventlog.query() == []
    assert eventlog.info("測試", "新的") == first + 2  # 編號不重設


def test_compact_shrinks_file(events_db):
    for _ in range(300):
        eventlog.info("測試", "x" * 2000)
    eventlog.compact()
    before = eventlog.stats()[1]
    eventlog.delete_older_than(0, now=datetime.now(timezone.utc) + timedelta(seconds=1))
    eventlog.compact()
    assert eventlog.stats()[1] < before


def test_backup_dir_is_next_to_database(events_db):
    assert eventlog.log_dir() == events_db.parent
    assert eventlog.backup_dir() == events_db.parent / "backup"


def test_reset_backs_up_and_restarts_ids(events_db):
    eventlog.info("測試", "第一筆")
    eventlog.error("測試", "第二筆")
    n, backup = eventlog.reset(now=datetime(2026, 10, 28, 14, 3, 21))
    assert n == 2 and backup == events_db.parent / "backup" / "events-20261028-140321.zip"
    with zipfile.ZipFile(backup) as z:
        text = z.read("events.txt").decode("utf-8")
    assert "第一筆" in text and "第二筆" in text
    [e] = eventlog.query()
    assert e.id == 1 and "已初始化" in e.message and str(backup) in e.message
    assert eventlog.info("測試", "第三筆") == 2


def test_reset_aborts_when_backup_fails(events_db, monkeypatch):
    eid = eventlog.info("測試", "要保留")

    def boom(*_args, **_kwargs):
        raise OSError("磁碟已滿")
    monkeypatch.setattr(eventlog, "export_zip", boom)
    with pytest.raises(OSError):
        eventlog.reset()
    assert [e.id for e in eventlog.query()] == [eid]


def test_reset_without_database_raises():
    eventlog.shutdown()
    with pytest.raises(RuntimeError):
        eventlog.reset()
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/test_eventlog.py`
Expected: 新的 8 個測試 FAIL（`AttributeError: module 'pllangstudio.eventlog' has no attribute 'summary'` 等）

- [ ] **Step 3: 實作**

在 `Event` dataclass 之後加：

```python
@dataclass(frozen=True)
class Summary:
    counts: dict[str, int]  # 等級群組（info／warning／error）→ 筆數
    oldest: datetime | None  # 最舊一筆的本地時間；沒有紀錄時是 None
    size: int  # 資料庫檔案大小 bytes（含 -wal）

    @property
    def total(self) -> int:
        return sum(self.counts.values())
```

在 `default_path()` 之後加：

```python
def log_dir() -> Path:
    """資料庫所在的資料夾（「開啟紀錄資料夾」用）。"""
    return (_db_path or default_path()).parent


def backup_dir() -> Path:
    """初始化前的備份放在資料庫旁的 backup 資料夾。"""
    return log_dir() / "backup"
```

在 `stats()` 之後加：

```python
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


def reset(now: datetime | None = None) -> tuple[int, Path]:
    """初始化：先把全部紀錄備份成 zip，再清空並把事件編號歸零。

    備份失敗就拋出 OSError，什麼都不刪；回傳（刪除筆數, 備份檔）。
    """
    if _conn is None:
        raise RuntimeError("事件紀錄目前無法使用")
    now = now or datetime.now()
    events = query(limit=-1)  # LIMIT -1：全部
    dest = backup_dir() / f"events-{now:%Y%m%d-%H%M%S}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    export_zip(events, dest)
    with _lock:
        try:
            _conn.execute("BEGIN")
            _conn.execute("DELETE FROM events")
            _conn.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")  # 編號從 1 重新開始
            _conn.execute("COMMIT")
        except sqlite3.Error as e:
            if _conn.in_transaction:
                _conn.execute("ROLLBACK")
            raise RuntimeError(f"無法清空事件紀錄：{e}") from e
    compact()
    info("事件紀錄", f"事件紀錄已初始化，刪除 {len(events):,} 筆；原紀錄備份在：{dest}")
    return len(events), dest
```

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/test_eventlog.py`
Expected: 全部通過（原 20 個＋新 8 個）

- [ ] **Step 5: 跑全部測試**

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add pllangstudio/eventlog.py tests/test_eventlog.py
git commit -F <訊息檔>   # feat: 事件紀錄可統計、刪除超過 N 天、壓縮與初始化（先備份、編號重設）
```

---

### Task 2: 工作階段與異常結束偵測

**Files:**
- Modify: `pllangstudio/eventlog.py`
- Modify: `pllangstudio/__main__.py`
- Test: `tests/test_eventlog.py`

**Interfaces:**
- Consumes: Task 1 之前既有的 `_lock`、`_conn`、`_utc`、`warning`、`purge`、`shutdown`；Task 1 的 `reset`
- Produces:
  - `start_session(pid: int | None = None, alive: Callable[[int], bool] | None = None) -> list[int]`（回傳這次記下的異常結束警告的事件編號）
  - `end_session() -> None`
  - `_pid_alive(pid: int) -> bool`
  - `sessions` 資料表：`id INTEGER PRIMARY KEY AUTOINCREMENT, pid INTEGER NOT NULL, started TEXT NOT NULL, ended TEXT, abnormal INTEGER NOT NULL DEFAULT 0`

- [ ] **Step 1: 寫會失敗的測試**（`tests/test_eventlog.py`；import 區補 `import os`、`import subprocess`）

```python
def test_abnormal_exit_detected_on_next_start(events_db):
    eventlog.start_session(pid=111, alive=lambda p: True)
    last = eventlog.info("存檔", "當機前最後一個動作")
    # 沒有呼叫 end_session 就結束；下次啟動時 111 已不存在
    ids = eventlog.start_session(pid=222, alive=lambda p: False)
    [w] = eventlog.query({"warning"})
    assert ids == [w.id] and w.category == "程式"
    assert "上次程式未正常結束" in w.message and f"最後一筆紀錄 #{last}" in w.message
    assert eventlog.start_session(pid=333, alive=lambda p: p == 222) == []  # 同一次異常只報一次


def test_clean_exit_is_not_reported(events_db):
    eventlog.start_session(pid=111, alive=lambda p: True)
    eventlog.end_session()
    assert eventlog.start_session(pid=222, alive=lambda p: False) == []


def test_running_instance_is_not_reported(events_db):
    eventlog.start_session(pid=111, alive=lambda p: True)
    assert eventlog.start_session(pid=222, alive=lambda p: p == 111) == []


def test_pid_alive():
    assert eventlog._pid_alive(os.getpid())
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not eventlog._pid_alive(p.pid)


def test_purge_removes_old_ended_sessions(events_db):
    eventlog.start_session(pid=111, alive=lambda p: True)
    eventlog.end_session()
    eventlog.purge({"info": 1, "warning": 1, "error": 1}, now=datetime.now(timezone.utc) + timedelta(days=2))
    conn = sqlite3.connect(events_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    finally:
        conn.close()


def test_reset_keeps_current_session(events_db):
    eventlog.start_session(pid=111, alive=lambda p: True)
    eventlog.reset()
    eventlog.end_session()
    conn = sqlite3.connect(events_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE ended IS NOT NULL").fetchone()[0] == 1
    finally:
        conn.close()
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/test_eventlog.py`
Expected: 新的 6 個測試 FAIL（`AttributeError: ... 'start_session'`）

- [ ] **Step 3: 實作 eventlog**

import 區補 `import os`。`_SCHEMA` 結尾（`events_level` 索引之後）加：

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER NOT NULL,
    started TEXT NOT NULL,
    ended TEXT,
    abnormal INTEGER NOT NULL DEFAULT 0
);
```

模組全域變數區加 `_session_id: int | None = None`。`shutdown()` 的 `global` 宣告加入 `_session_id`，並在最後把它設回 `None`。

`purge()` 在 `for group, days in retention.items():` 迴圈結束後（同一個 `try` 內）加：

```python
            if retention:  # 已結束的工作階段保留到最長的保留天數
                _conn.execute("DELETE FROM sessions WHERE ended IS NOT NULL AND ended < ?",
                              (_utc(now - timedelta(days=max(retention.values()))),))
```

`reset()` 清空 events 的那段 `DELETE` 之後、`COMMIT` 之前加：

```python
            _conn.execute("DELETE FROM sessions WHERE id != ?", (_session_id or -1,))
```

在 `install_excepthook` 之前加：

```python
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
                if other == pid or alive(other):
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
```

- [ ] **Step 4: 修改 `__main__.py`**

`eventlog.setup(...)` 那行之後、`eventlog.info("程式", ...啟動...)` 之前加：

```python
    eventlog.start_session()  # 會順便記下上次是否異常結束
```

結尾改為：

```python
    code = app.exec()
    eventlog.end_session()  # app.exec() 拋出例外時不會執行到，下次啟動就會記成異常結束
    eventlog.shutdown()
    return code
```

- [ ] **Step 5: 確認通過**

Run: `uv run pytest -n0 tests/test_eventlog.py`
Expected: 全部通過

- [ ] **Step 6: 跑全部測試**

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 7: Commit**

```bash
git add pllangstudio/eventlog.py pllangstudio/__main__.py tests/test_eventlog.py
git commit -F <訊息檔>   # feat: 啟動時偵測上次程式是否異常結束並記成警告
```

---

### Task 3: 錯誤對話框可複製事件編號、開啟事件檢視器

**Files:**
- Create: `pllangstudio/ui/error_box.py`
- Modify: `pllangstudio/ui/main_window.py`
- Modify: `pllangstudio/__main__.py`
- Test: `tests/ui/test_error_box.py`、`tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `eventlog.error`、`eventlog.with_event_id`、`eventlog.crash_message`、`eventlog.install_excepthook`；既有 `MainWindow.event_viewer`、`EventViewer.search`（`QLineEdit`，`textChanged` 會觸發 `refresh`）、`EventViewer.refresh()`、`EventViewer.events`
- Produces:
  - `error_box(parent, title: str, text: str, event_id: int | None, open_viewer: Callable[[int], None] | None = None, icon=QMessageBox.Warning) -> QMessageBox`（呼叫端負責 `exec()`）
  - `MainWindow._info(title, text, error=False, event_id: int | None = None)`；`MainWindow.show_events(event_id: int | None = None)`

- [ ] **Step 1: 寫會失敗的測試**

新增 `tests/ui/test_error_box.py`：

```python
from PySide6.QtWidgets import QApplication

from pllangstudio.ui.error_box import error_box


def button(box, text):
    return next(b for b in box.buttons() if b.text() == text)


def test_copy_event_id(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", 42)
    qtbot.addWidget(box)
    button(box, "複製事件編號").click()
    assert QApplication.clipboard().text() == "#42"


def test_open_viewer_with_event_id(qtbot):
    opened = []
    box = error_box(None, "存檔失敗", "沒有存成功", 42, opened.append)
    qtbot.addWidget(box)
    button(box, "開啟事件檢視器").click()
    assert opened == [42]


def test_without_viewer_has_no_viewer_button(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", 42)
    qtbot.addWidget(box)
    assert [b.text() for b in box.buttons() if b.text() == "開啟事件檢視器"] == []


def test_without_event_id_only_ok(qtbot):
    box = error_box(None, "存檔失敗", "沒有存成功", None, lambda eid: None)
    qtbot.addWidget(box)
    assert len(box.buttons()) == 1
```

`tests/ui/test_main_window.py`：

1. `test_save_failure_dialog_shows_event_id` 的 `win.info = lambda title, text, error=False: shown.append((title, text, error))` 改為 `win.info = lambda title, text, error=False, event_id=None: shown.append((title, text, error, event_id))`，最後一行之後加 `assert shown[-1][3] == e.id`。
2. 檔尾加：

```python
def test_show_events_locates_event_id(win, events_db):
    eid = eventlog.error("測試", "要找的這筆")
    eventlog.info("測試", "其他")
    win.show_events(eid)
    assert [e.id for e in win.event_viewer.events] == [eid]
    win.show_events()  # 沒指定編號時保留目前的搜尋條件，只重新整理
    assert win.event_viewer.search.text() == f"#{eid}"
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/ui/test_error_box.py tests/ui/test_main_window.py -k "error_box or event_id or locates or copy or viewer or only_ok"`
Expected: FAIL（`ModuleNotFoundError: pllangstudio.ui.error_box`、`show_events() takes 1 positional argument`）

- [ ] **Step 3: 實作 `pllangstudio/ui/error_box.py`**

```python
"""有事件編號的錯誤對話框：多「複製事件編號」與「開啟事件檢視器」兩個按鈕，回報問題時不用自己抄編號（見 ADR-0018）。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QApplication, QMessageBox


def error_box(parent, title: str, text: str, event_id: int | None,
              open_viewer: Callable[[int], None] | None = None, icon=QMessageBox.Warning) -> QMessageBox:
    """建立對話框，由呼叫端 exec()。沒有事件編號時只有「確定」。按任何按鈕都會關閉對話框。"""
    box = QMessageBox(icon, title, text, QMessageBox.Ok, parent)
    if event_id is None:
        return box
    copy = box.addButton("複製事件編號", QMessageBox.ActionRole)
    view = box.addButton("開啟事件檢視器", QMessageBox.ActionRole) if open_viewer else None
    box.setDefaultButton(QMessageBox.Ok)

    def clicked(b) -> None:
        if b == copy:
            QApplication.clipboard().setText(f"#{event_id}")
        elif view is not None and b == view:
            open_viewer(event_id)
    box.buttonClicked.connect(clicked)
    return box
```

- [ ] **Step 4: 修改 `main_window.py`**

加 `from .error_box import error_box`。`_info` 與 `_error` 改為：

```python
    def _info(self, title: str, text: str, error: bool = False, event_id: int | None = None) -> None:
        if event_id is not None:
            error_box(self, title, text, event_id, self.show_events).exec()
            return
        (QMessageBox.warning if error else QMessageBox.information)(self, title, text)

    def _error(self, category: str, title: str, text: str, exc: BaseException | None = None) -> None:
        """錯誤一律記進事件紀錄，對話框附上事件編號，回報問題時用。"""
        eid = eventlog.error(category, f"{title}：{text}", exc)
        self.info(title, eventlog.with_event_id(text, eid), error=True, event_id=eid)
```

`show_events` 改為：

```python
    def show_events(self, event_id: int | None = None) -> None:
        """事件檢視器只開一個，再按一次就帶到前面並重新整理；指定事件編號時直接列出那一筆。"""
        if self.event_viewer is None:
            self.event_viewer = EventViewer(self.theme, self)
        if event_id is not None:
            self.event_viewer.search.setText(f"#{event_id}")
        self.event_viewer.refresh()
        self.event_viewer.show()
        self.event_viewer.raise_()
        self.event_viewer.activateWindow()
```

注意：主視窗建構時的 `info` 參數若是測試注入的 `lambda *a, **k: None` 仍相容；`SettingsDialog` 以無參數呼叫 `show_events()` 仍相容。

- [ ] **Step 5: 修改 `__main__.py` 的未預期錯誤對話框**

加 `from pllangstudio.ui.error_box import error_box`。把 `eventlog.install_excepthook(lambda eid: QMessageBox.critical(...))` 那段換成：

```python
    win = None  # 視窗建立前出錯時沒有事件檢視器可開

    def show_crash(eid: int | None) -> None:
        open_viewer = win.show_events if win is not None else None
        error_box(QApplication.activeWindow(), "發生未預期的錯誤", eventlog.crash_message(eid), eid, open_viewer,
                  QMessageBox.Critical).exec()
    eventlog.install_excepthook(show_crash)
```

後面 `win = MainWindow(...)` 維持原樣（重新指派同一個區域變數，`show_crash` 執行時讀到的是視窗）。

- [ ] **Step 6: 確認通過**

Run: `uv run pytest -n0 tests/ui/test_error_box.py tests/ui/test_main_window.py`
Expected: 全部通過

- [ ] **Step 7: 跑全部測試**

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 8: Commit**

```bash
git add pllangstudio/ui/error_box.py pllangstudio/ui/main_window.py pllangstudio/__main__.py tests/ui
git commit -F <訊息檔>   # feat(ui): 錯誤對話框可複製事件編號或直接開啟事件檢視器
```

---

### Task 4: 「紀錄事件」頁的維護功能

**Files:**
- Modify: `pllangstudio/ui/settings_dialog.py`
- Test: `tests/ui/test_settings_dialog.py`

**Interfaces:**
- Consumes: Task 1 的 `eventlog.summary / count_older_than / delete_older_than / compact / reset / backup_dir / log_dir`；既有 `eventlog.purge / info / error / with_event_id / GROUP_LABEL`、`appconfig.LOG_DAYS_RANGE / log_retention / remember_log_retention`
- Produces（`LogPage`）：
  - 屬性 `ask: Callable[[str, str], QMessageBox.StandardButton]`、`warn: Callable[[str, str], None]`、`open_folder: Callable[[str], None]`（預設分別為問答對話框、警告對話框、`os.startfile`，測試時換掉）
  - 元件 `days`（既有）、`stats`、`message`、`delete_days`、`delete_button`、`purge_button`、`viewer_button`、`folder_button`、`reset_button`
  - 方法 `refresh_stats()`（不再接受參數）、`apply()`、`purge_now()`、`delete_old()`、`reset_log()`；signal `viewerRequested`（既有）

- [ ] **Step 1: 寫會失敗的測試**（`tests/ui/test_settings_dialog.py`）

import 區補：`import sqlite3`、`from datetime import datetime, timedelta, timezone`、`from PySide6.QtWidgets import QApplication, QMessageBox`（取代原本只 import `QApplication` 的那行）。檔尾加：

```python
def answer(dialog, reply):
    """換掉確認對話框，記下問了什麼。"""
    asked = []
    dialog.log_page.ask = lambda title, text: asked.append(text) or reply
    return asked


def backdate(db, days):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE events SET time = ?",
                 ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds"),))
    conn.commit()
    conn.close()


def test_summary_shown(dialog):
    eventlog.warning("存檔", "有警告")
    dialog.log_page.refresh_stats()
    text = dialog.log_page.stats.text()
    assert "共 1 筆" in text and "警告 1" in text and "最舊" in text


def test_delete_old_asks_then_keeps_ids(dialog, events_db):
    first = eventlog.info("測試", "舊的")
    backdate(events_db, 40)
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.delete_days.setValue(30)
    dialog.log_page.delete_old()
    assert "1 筆" in asked[0]
    [e] = eventlog.query()
    assert e.id == first + 1 and "手動刪除 30 天前的紀錄 1 筆" in e.message
    assert "已刪除 1 筆" in dialog.log_page.message.text()


def test_delete_old_cancelled(dialog, events_db):
    eventlog.info("測試", "舊的")
    backdate(events_db, 40)
    answer(dialog, QMessageBox.No)
    dialog.log_page.delete_old()
    assert len(eventlog.query()) == 1


def test_delete_old_nothing_to_delete(dialog):
    eventlog.info("測試", "新的")
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.delete_old()
    assert asked == [] and "沒有" in dialog.log_page.message.text()


def test_reset_from_page(dialog, events_db):
    eventlog.info("測試", "一")
    eventlog.info("測試", "二")
    asked = answer(dialog, QMessageBox.Yes)
    dialog.log_page.reset_log()
    assert "2 筆" in asked[0] and "備份" in asked[0]
    [e] = eventlog.query()
    assert e.id == 1 and "已初始化" in e.message
    assert list((events_db.parent / "backup").glob("events-*.zip"))
    assert "共 1 筆" in dialog.log_page.stats.text()


def test_reset_cancelled(dialog):
    eventlog.info("測試", "一")
    answer(dialog, QMessageBox.No)
    dialog.log_page.reset_log()
    assert len(eventlog.query()) == 1


def test_reset_failure_keeps_events(dialog, monkeypatch):
    eid = eventlog.info("測試", "要保留")
    answer(dialog, QMessageBox.Yes)
    warned = []
    dialog.log_page.warn = lambda title, text: warned.append(text)

    def boom(*_args, **_kwargs):
        raise OSError("磁碟已滿")
    monkeypatch.setattr(eventlog, "export_zip", boom)
    dialog.log_page.reset_log()
    assert eid in [e.id for e in eventlog.query()]
    assert "沒有刪除任何紀錄" in warned[0] and "磁碟已滿" in warned[0] and "事件編號" in warned[0]


def test_open_folder(dialog, events_db):
    opened = []
    dialog.log_page.open_folder = opened.append
    dialog.log_page.folder_button.click()
    assert opened == [str(events_db.parent)]
```

- [ ] **Step 2: 確認失敗**

Run: `uv run pytest -n0 tests/ui/test_settings_dialog.py`
Expected: 新的 8 個 FAIL（`AttributeError: 'LogPage' object has no attribute 'delete_old'` 等）

- [ ] **Step 3: 實作 `LogPage`**

`settings_dialog.py` import 補 `import os`，`QGroupBox`、`QMessageBox` 加入 `PySide6.QtWidgets` 的 import。模組 docstring 第二段改為：「按「確定」或「套用」才生效；「還原預設字型」與紀錄事件頁的維護按鈕（刪除、清除、初始化）立即生效。」

整個 `LogPage` 類別換成：

```python
class LogPage(QWidget):
    viewerRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ask = self._ask  # 測試時可以換掉對話框與開資料夾
        self.warn = self._warn
        self.open_folder = os.startfile
        retention = appconfig.log_retention()
        self.days: dict[str, QSpinBox] = {}
        keep = QFormLayout()
        for group, label in (("info", "資訊"), ("warning", "警告"), ("error", "錯誤（含嚴重錯誤）")):
            box = QSpinBox()
            box.setRange(*appconfig.LOG_DAYS_RANGE)
            box.setSuffix(" 天")
            box.setValue(retention[group])
            keep.addRow(f"{label}保留", box)
            self.days[group] = box
        keep_box = QGroupBox("保留天數（超過會自動清除）")
        keep_box.setLayout(keep)

        self.stats = QLabel()
        self.stats.setWordWrap(True)
        stats_box = QGroupBox("目前紀錄")
        QVBoxLayout(stats_box).addWidget(self.stats)

        self.delete_days = QSpinBox()
        self.delete_days.setRange(*appconfig.LOG_DAYS_RANGE)
        self.delete_days.setSuffix(" 天")
        self.delete_days.setValue(30)
        self.delete_button = QPushButton("刪除")
        self.delete_button.clicked.connect(self.delete_old)
        delete_row = QHBoxLayout()
        delete_row.addWidget(QLabel("刪除"))
        delete_row.addWidget(self.delete_days)
        delete_row.addWidget(QLabel("前的紀錄（不分等級，事件編號不重設）"))
        delete_row.addWidget(self.delete_button)
        delete_row.addStretch()
        self.purge_button = QPushButton("立即清除過期紀錄")
        self.purge_button.clicked.connect(self.purge_now)
        self.viewer_button = QPushButton("開啟事件檢視器")
        self.viewer_button.clicked.connect(self.viewerRequested)
        self.folder_button = QPushButton("開啟紀錄資料夾")
        self.folder_button.clicked.connect(lambda: self.open_folder(str(eventlog.log_dir())))
        tools_row = QHBoxLayout()
        for b in (self.purge_button, self.viewer_button, self.folder_button):
            tools_row.addWidget(b)
        tools_row.addStretch()
        tools_box = QGroupBox("維護")
        tools = QVBoxLayout(tools_box)
        tools.addLayout(delete_row)
        tools.addLayout(tools_row)

        self.reset_button = QPushButton("初始化事件紀錄…")
        self.reset_button.clicked.connect(self.reset_log)
        reset_box = QGroupBox("初始化")
        reset = QHBoxLayout(reset_box)
        reset.addWidget(self.reset_button)
        reset.addWidget(QLabel("清空全部紀錄，事件編號從 #1 重新開始；刪除前會自動備份。"), 1)

        self.message = QLabel()  # 最近一次維護的結果
        self.message.setWordWrap(True)
        lay = QVBoxLayout(self)
        for w in (keep_box, stats_box, tools_box, reset_box, self.message):
            lay.addWidget(w)
        lay.addStretch()
        self.refresh_stats()

    def _ask(self, title: str, text: str) -> QMessageBox.StandardButton:
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

    def _warn(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def retention(self) -> dict[str, int]:
        return {g: b.value() for g, b in self.days.items()}

    def refresh_stats(self) -> None:
        s = eventlog.summary()
        groups = "｜".join(f"{eventlog.GROUP_LABEL[g]} {n:,}" for g, n in s.counts.items())
        oldest = f"，最舊 {s.oldest:%Y-%m-%d}" if s.oldest else ""
        self.stats.setText(f"共 {s.total:,} 筆（{groups}）{oldest}，佔 {s.size / 1024 / 1024:.1f} MB")

    def _done(self, text: str) -> None:
        self.message.setText(text)
        self.refresh_stats()

    def apply(self) -> None:
        new = self.retention()
        if new != appconfig.log_retention():
            appconfig.remember_log_retention(new)
            eventlog.info("配置", "保留天數改為 " + "、".join(f"{eventlog.GROUP_LABEL[g]} {d} 天" for g, d in new.items()))
        removed = eventlog.purge(new)
        if removed:
            self.message.setText(f"已清除 {removed:,} 筆過期紀錄。")
        self.refresh_stats()

    def purge_now(self) -> None:
        """依已儲存的天數清除；畫面上還沒套用的數字不算。"""
        removed = eventlog.purge(appconfig.log_retention())
        if removed:
            eventlog.compact()
        self._done(f"已清除 {removed:,} 筆過期紀錄。" if removed else "沒有過期的紀錄。")

    def delete_old(self) -> None:
        days = self.delete_days.value()
        n = eventlog.count_older_than(days)
        if n == 0:
            self._done(f"沒有 {days} 天前的紀錄。")
            return
        if self.ask("刪除紀錄", f"要刪除 {days} 天前的 {n:,} 筆紀錄嗎？\n（不分等級，事件編號不會重設）") != QMessageBox.Yes:
            return
        removed = eventlog.delete_older_than(days)
        eventlog.compact()
        eventlog.info("事件紀錄", f"手動刪除 {days} 天前的紀錄 {removed:,} 筆")
        self._done(f"已刪除 {removed:,} 筆。")

    def reset_log(self) -> None:
        total = eventlog.summary().total
        if self.ask("初始化事件紀錄", f"將刪除全部 {total:,} 筆紀錄，事件編號從 #1 重新開始。\n"
                    f"刪除前會先備份到：\n{eventlog.backup_dir()}\n\n確定要初始化嗎？") != QMessageBox.Yes:
            return
        try:
            n, backup = eventlog.reset()
        except (OSError, RuntimeError) as e:
            eid = eventlog.error("事件紀錄", f"初始化失敗：{e}", e)
            self.warn("初始化失敗", eventlog.with_event_id(f"沒有刪除任何紀錄。\n\n{e}", eid))
            return
        self._done(f"已初始化，刪除 {n:,} 筆；備份在：{backup}")
```

`SettingsDialog.__init__` 的 `self.resize(560, 360)` 改為 `self.resize(640, 520)`（新的頁面較高）。

- [ ] **Step 4: 確認通過**

Run: `uv run pytest -n0 tests/ui/test_settings_dialog.py`
Expected: 全部通過（含原本的 `test_stats_and_purge_now`：統計文字仍含「共 1 筆」）

- [ ] **Step 5: 跑全部測試**

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add pllangstudio/ui/settings_dialog.py tests/ui/test_settings_dialog.py
git commit -F <訊息檔>   # feat(ui): 紀錄事件頁可刪除超過 N 天的紀錄、初始化事件紀錄、顯示統計與開啟紀錄資料夾
```

---

### Task 5: 文件（ADR-0018、README、CONTEXT.md、AGENTS.md）

**Files:**
- Create: `docs/adr/0018-event-log-maintenance.md`
- Modify: `README.md`（第 11 節）、`CONTEXT.md`、`AGENTS.md`

- [ ] **Step 1: 新增 `docs/adr/0018-event-log-maintenance.md`**（格式比照 0017）

```markdown
---
status: accepted
---

# 事件紀錄的維護：初始化會重設編號並先備份，啟動時偵測異常結束

[ADR-0017](0017-event-log.md) 的事件紀錄只會依保留天數自動清除。實際使用時還需要手動維護，追查問題時也需要更多線索，所以在「配置 ▸ 紀錄事件」加入以下功能：

- **初始化事件紀錄**：清空全部紀錄並把事件編號歸零（SQLite 的 `sqlite_sequence`），之後的第一筆是「#1 事件紀錄已初始化」。這是唯一會重設編號的操作，所以一定**先把全部紀錄備份成 zip**，放在 events.db 旁的 `backup` 資料夾；**備份失敗就中止，不刪任何紀錄**。備份檔不自動清除，因為初始化很少做。
- **刪除超過 N 天的紀錄**：不分等級、編號不重設，確認時先顯示會刪幾筆，刪除後記一筆。
- **壓縮資料庫**：手動刪除、立即清除、初始化之後執行 VACUUM，檔案才會變小。啟動時的自動清除不壓縮，避免拖慢啟動。
- **統計**：顯示資訊／警告／錯誤各幾筆、最舊一筆的日期與檔案大小。
- **偵測異常結束**：`sessions` 資料表記下每次啟動的程序編號與時間，正常結束時標記。下次啟動時，未標記且程序已不存在的，就記一筆警告「上次程式未正常結束」，附上該次之後的最後一筆事件編號。被強制結束、當機、斷電這類情況 `sys.excepthook` 攔不到，這是唯一的線索。檢查程序是否還在，是為了在同時開兩個實例時不誤報。
- **錯誤對話框**多「複製事件編號」「開啟事件檢視器」兩個按鈕，後者直接以 `#編號` 列出那一筆。

## Considered Options

- **初始化不重設編號**：比較安全，但使用者明確想要「從 #1 重新開始」，例如交付給新使用者前清乾淨。以「先備份、失敗就中止」降低風險。
- **用一個「執行中」旗標偵測異常結束**：同時開兩個實例時，第二個會把第一個誤判成異常結束。改用每個實例一筆工作階段並檢查程序是否存在。
- **每次清除都壓縮**：啟動時資料庫大的話會拖慢開啟速度。只在使用者手動操作時壓縮。
```

- [ ] **Step 2: README 第 11 節**

用 Edit 工具，在「**配置 ▸ 配置… ▸ 紀錄事件**：設定保留天數…」那一項之後加：

```markdown
- 同一頁還有這些維護功能：
  - **目前紀錄**：資訊／警告／錯誤各幾筆、最舊一筆的日期、檔案大小。
  - **刪除 N 天前的紀錄**：不分等級刪除，事件編號不會重設。
  - **立即清除過期紀錄**：依保留天數立刻清一次。
  - **開啟紀錄資料夾**：開啟 events.db 與備份所在的資料夾。
  - **初始化事件紀錄…**：清空全部紀錄，事件編號從 #1 重新開始。刪除前會自動備份到 `backup` 資料夾，備份失敗就不會刪除。
- 錯誤對話框有 **複製事件編號** 和 **開啟事件檢視器** 兩個按鈕，按後者會直接列出這一筆。
- 如果上次程式被強制關閉或當機，下次開啟時事件紀錄會多一筆警告「上次程式未正常結束」，回報時一起提供。
```

並在第 15 節（檔案放在哪裡？）的事件紀錄那列之後加一列：`| 事件紀錄備份 | %APPDATA%\PLLangStudio\backup\ | 初始化事件紀錄前自動產生的 zip |`（節號以實際 README 為準，找「檔案放在哪裡」的表格）。

- [ ] **Step 3: CONTEXT.md**（在 **保留天數** 之後，格式同既有條目）

```markdown
**初始化事件紀錄**：
清空全部事件紀錄並讓事件編號從 #1 重新開始；執行前一定先自動備份。
_Avoid_: 重置 log、清除日誌

**異常結束**：
程式沒有經過正常關閉就停止（被強制結束、當機、斷電），下次啟動時會記成一筆警告。
_Avoid_: crash、閃退
```

- [ ] **Step 4: AGENTS.md**

`docs/adr/` 的說明「（0001～0017）」改為「（0001～0018）」。

- [ ] **Step 5: 驗證**

Run: `uv run python -c "import pathlib; [p.read_text(encoding='utf-8') for p in [*pathlib.Path('docs').rglob('*.md'), pathlib.Path('README.md'), pathlib.Path('CONTEXT.md'), pathlib.Path('AGENTS.md')]]; print('ok')"`
Expected: `ok`

Run: `uv run pytest`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add docs/adr/0018-event-log-maintenance.md README.md CONTEXT.md AGENTS.md
git commit -F <訊息檔>   # docs: 新增 ADR-0018 事件紀錄維護，README、CONTEXT.md 補上初始化與異常結束說明
```
