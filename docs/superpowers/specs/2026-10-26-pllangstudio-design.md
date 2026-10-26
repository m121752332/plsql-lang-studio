# PLLangStudio：PL/SQL Developer 語言編輯與比對器 — 設計規格

- 日期：2026-10-26
- 狀態：待審閱
- 術語：依 [CONTEXT.md](../../../CONTEXT.md)
- 決策紀錄：[docs/adr/0001～0012](../../adr/)

## 1. 目的

PL/SQL Developer 的語言檔（`.lang`）是加密的，沒有官方編輯工具，也看不到英文原文跟翻譯的對應關係。PLLangStudio 讓使用者：

1. 檢視 PL/SQL Developer 的所有語言檔，以及工作區裡解密後的語言檔。
2. 把兩個語言檔逐字串對照（MASTER 唯讀、SLAVE 可編輯），同時看到英文原文。
3. 在表格裡或用記事本修改 SLAVE 的翻譯，並使用批次工具（尋找取代、簡轉繁、用語對照表）。
4. 檢查翻譯錯誤（佔位符、殘留簡體字、漏翻）。
5. 加密存回工作區，確認後再部署到 PL/SQL Developer。

典型用法：MASTER＝Chinese.lang（簡體）、SLAVE＝Taiwan.lang（繁體），逐筆修正台灣用語。

## 2. 範圍

### 要做
- 工作區管理：設定、匯入、存檔、備份、部署
- 檔案清單：PL/SQL 語言檔、工作區檔案
- MASTER／SLAVE 下拉選單，可以換成任何語言檔
- 逐字串對照表格：狀態標示、篩選、搜尋
- 詳細區：元件路徑、說明註解、字元級差異、多行編輯
- 表格內編輯、記事本 .txt 編輯與同步
- 批次操作：尋找取代、簡轉繁（OpenCC `s2twp`）、用語對照表
- 檢查規則：錯誤／警告兩級
- 復原／重做
- 打包成單一 exe

### 不做（YAGNI）
- 新增或刪除「筆」：筆的結構由 PL/SQL Developer 決定，只能改翻譯。
- 修改英文原文、說明註解、識別碼。
- 三方以上的比對（同時比對 3 個語言檔）。
- 機器翻譯／AI 翻譯。
- 多人協作、版本控制整合。
- 自動合併記事本與表格的衝突修改（見 ADR-0008，採用詢問）。

## 3. 語言檔格式（摘要，詳見 ADR-0001）

- 加密：明文（UTF-8 含 BOM、CRLF）與固定的 256 bytes 金鑰做循環 XOR。
- 結構：12 行檔頭（第 1 行 `:語言名稱`），之後是一筆一筆的資料，檔尾有一個空行。
- 每筆以 `||` 加 15 個兩位數欄位的旗標開頭：

| 欄位 | 意義 |
|---|---|
| p1 | 固定 01 |
| p2 | 上層元件行數 |
| p3 | 元件名稱行數 |
| p4 | 元件類型行數 |
| p5 | 說明註解行數 |
| p6／p7／p8 | 英文的標題／提示／清單項目行數 |
| p9／p10／p11 | 翻譯的標題／提示／清單項目行數 |
| p12～p15 | 保留，目前全部為 0；不是 0 時保留原樣，不解讀 |

- 筆的行順序：視窗名稱 → 上層元件 → 元件名稱 → 元件類型 → 說明註解 → 英文（標題、提示、項目）→ 翻譯（標題、提示、項目）。
- 識別碼 = (視窗名稱, 上層元件…, 元件名稱, 元件類型)。實測沒有重複的識別碼；萬一出現重複，就依出現順序加上序號。

實測數據（Chinese 對 Taiwan）：5,876 筆，展開成 6,672 個字串列。其中 49 列是「英文行數 ≠ 翻譯行數」的欄位，以整個欄位一列（多行）顯示；另有 134 筆沒有可翻譯的字串，不顯示。

## 4. 架構

```
pllangstudio/
├─ core/                 不依賴 PySide6，可單獨測試
│  ├─ langcrypt.py       加解密
│  ├─ langfile.py        解析／寫回
│  ├─ compare.py         對齊與狀態
│  ├─ validate.py        檢查規則
│  ├─ glossary.py        用語對照表、例外詞
│  ├─ batch.py           批次操作的預覽（尋找取代、簡轉繁、套用用語表）
│  ├─ convert.py         OpenCC 包裝
│  └─ workspace.py       工作區、匯入、存檔、備份、部署、txt 監看
├─ ui/
│  ├─ main_window.py     主視窗、工具列、狀態列
│  ├─ file_panel.py      左側兩個分頁的檔案清單
│  ├─ compare_model.py   QAbstractTableModel、篩選 proxy
│  ├─ detail_panel.py    詳細區、字元級差異、多行編輯
│  ├─ batch_dialog.py    批次操作預覽（尋找取代／簡轉繁／用語表共用）
│  ├─ glossary_dialog.py 用語對照表編輯器
│  ├─ commands.py        QUndoCommand：單一字串編輯、整批編輯
│  └─ theme.py           固定使用淺色主題
├─ elevate.py            Windows UAC 複製（ShellExecuteExW runas）
├─ appconfig.py          記住上次的工作區（%APPDATA%\PLLangStudio\app.json）
└─ __main__.py
tests/
```

現有的 tkinter `app.py` 和 `langcrypt.py` 在 PLLangStudio 達到同等功能後移除。`langcrypt.py` 搬進 `core/`，不修改內容。

### 4.1 核心資料結構（`langfile.py`）

```python
class Field(Enum): CAPTION, HINT, ITEMS

@dataclass
class Entry:
    flags: list[int]                  # 15 個欄位，寫回時重新計算 p9～p11
    window: str
    parents: list[str]
    component: list[str]              # 0 或 1 行
    ctype: list[str]                  # 0 或 1 行
    comments: list[str]
    source: dict[Field, list[str]]    # 英文
    target: dict[Field, list[str]]    # 翻譯
    @property
    def key(self) -> tuple[str, ...]: ...

@dataclass
class LangFile:
    header: list[str]                 # 12 行，原樣保留
    entries: list[Entry]
    trailing_newline: bool
    def set_target(self, index: int, field: Field, lines: list[str]) -> None: ...

def parse(plain: bytes) -> LangFile            # 格式錯誤時拋出 LangFormatError(line_no, msg)
def serialize(lf: LangFile) -> bytes
def load(path) -> LangFile                     # 解密＋解析
def save(path, lf) -> None                     # 序列化＋加密＋原子寫入
```

不變量：`serialize(parse(x)) == x`，對 Languages 目錄下 14 個檔案都必須成立。

### 4.2 對齊（`compare.py`）

```python
@dataclass
class Row:
    key: tuple[str, ...]
    field: Field
    item: int | None             # 第幾行；None = 整個欄位一列（多行，以 \n 連接）
    source: str                  # 英文
    m_index: int | None          # MASTER 的筆索引；None = MASTER 沒有這筆
    s_index: int | None          # SLAVE 的筆索引；None = SLAVE 沒有這筆

def align(master: LangFile, slave: LangFile) -> list[Row]
def get_text(lf, index, field, item) -> str | None     # 讀取某一列的翻譯
def set_text(lf, index, field, item, text) -> None     # 寫入某一列的翻譯
def row_status(row, master, slave, original, exceptions) -> tuple[set[Status], list[Issue]]
# Status：DIFFERENT, UNTRANSLATED, SIMPLIFIED, ONE_SIDED, MODIFIED, ERROR, WARNING
```

- 依識別碼配對。列的順序以 SLAVE 為主，只有 MASTER 有的筆插在相鄰位置（ADR-0002）。
- 拆列規則（逐欄位判斷）：某個欄位的英文、SLAVE 翻譯、MASTER 翻譯行數都相同時，每一行一列；不相同時，整個欄位一列，內容以換行連接（ADR-0007）。三者都是 0 行的欄位不產生列。
- 英文欄取自 MASTER；MASTER 沒有這筆時，改取自 SLAVE（ADR-0003）。

### 4.3 檢查（`validate.py`，ADR-0011）

```python
@dataclass
class Issue: level: Literal["error", "warning"]; code: str; message: str

def check(source: str, target: str, exceptions: list[str]) -> list[Issue]
def simplified_spans(text: str, exceptions: list[str]) -> list[tuple[int, int]]
```

| code | 等級 | 條件 |
|---|---|---|
| FORMAT | error | 解析時旗標行數不符（由 `parse` 回報） |
| PLACEHOLDER | error | `%1`～`%9` 的集合與英文不同 |
| ACCEL | warning | 英文含 `&`（`&&` 除外），翻譯沒有 |
| UNTRANSLATED | warning | 翻譯 == 英文，而且英文含有 2 個以上連續的小寫字母（DML、NLS 這類全大寫縮寫不算），並排除網址、路徑、檔名 |
| SIMPLIFIED | warning | 有字元經 OpenCC `s2t` 轉換後會改變，而且不在例外詞內 |
| SPACES | warning | 開頭或結尾的空白與英文不同 |

預設例外詞：`游標`、`批准`（來自實測，見 ADR-0011）。

### 4.4 用語對照表（`glossary.py`，ADR-0010）

`glossary.json`：

```json
{
  "rules": [
    {"find": "配置文件", "replace": "設定檔", "except": [], "enabled": true},
    {"find": "新建", "replace": "新增", "except": ["重新建立"], "enabled": true}
  ],
  "simplified_exceptions": ["游標", "批准"]
}
```

```python
@dataclass
class Change: row_key: ...; before: str; after: str; checked: bool = True

def preview_rules(rows, rules) -> list[Change]
def preview_replace(rows, find, replace, regex: bool, case: bool) -> list[Change]
def preview_s2twp(rows) -> list[Change]
```

例外的比對方式：對每個符合的位置檢查周圍文字，只要該位置落在任何一個例外詞的範圍內，就跳過。規則依清單順序套用。

首次建立工作區時，預設規則就是這次手動整理過的那一批（配置→設定、會話→工作階段、事務→交易、首選項→偏好設定、常規→一般、宏→巨集……），附帶已知的例外（重新建立、通過計數、[通過]）。

### 4.5 工作區（`workspace.py`，ADR-0004、0008、0009）

```
workspace\
├─ lang\  txt\  backup\
├─ glossary.json
└─ settings.json   {"plsql_lang_dir": ..., "master": "Chinese.lang", "slave": "Taiwan.lang"}
```

```python
class Workspace:
    def __init__(self, root: Path): ...
    def list_installed(self) -> list[LangInfo]     # PL/SQL 語言目錄
    def list_workspace(self) -> list[LangInfo]     # 工作區 lang\ + txt\ 狀態
    def import_lang(self, name, overwrite: bool) -> None
    def save(self, name, lf: LangFile) -> Path     # 備份 → .tmp → os.replace → 重新產生 txt
    def deploy(self, name) -> DeployResult         # 備份 → 寫入或 UAC → 讀回比對
    def txt_changed(self, name) -> bool            # 依 mtime 與內容雜湊判斷
    def load_txt(self, name) -> LangFile           # 解析 txt，格式錯誤時拋出 LangFormatError
```

預設路徑：
- 工作區：exe 旁的 `workspace\`；不能寫入時，改用 `%USERPROFILE%\Documents\PLLangStudio\workspace`。
- PL/SQL 語言目錄：`C:\Program Files\PLSQL Developer 17\Languages`；不存在時，搜尋 `C:\Program Files*\PLSQL Developer*\Languages`，都找不到就請使用者選擇。

## 5. 畫面（ADR-0007）

```
┌ PLLangStudio ───────────────────────────────────────────────────────────────────────┐
│ 工作區：C:\...\workspace [切換] │ 匯入 │ 💾存檔 │ 🚀部署 │ 📝記事本 │ 🔍取代 │ 簡→繁 │ 📖用語表 │
├────────────────┬────────────────────────────────────────────────────────────────────┤
│[PL/SQL][工作區] │ MASTER [Chinese.lang ▼] 🔒       SLAVE [Taiwan.lang ▼]                │
│ Arabic.lang    │ [全部][不同][殘留簡體][疑似漏翻][單邊][錯誤][警告][已修改]  搜尋[____][範圍▼] │
│ Chinese.lang M ├──┬──┬────────────────┬────┬──────────┬──────────┬──────────┤
│ Taiwan.lang  S │# │狀│ 識別碼            │欄位 │ 英文      │ MASTER   │ SLAVE    │
│ ...            ├──┴──┴────────────────┴────┴──────────┴──────────┴──────────┤
│                │ 詳細：路徑／說明註解／字元級差異／SLAVE 多行編輯 [套用][還原]        │
├────────────────┴────────────────────────────────────────────────────────────────────┤
│ ✎ n 筆未存 │ 錯誤 n／警告 n │ 第 x / y 列 │ 部署狀態                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- **檔案清單**：右鍵選單有「設為 MASTER」「設為 SLAVE」「匯入工作區」「用記事本開 .txt」「開啟所在資料夾」。MASTER／SLAVE 的下拉選單只列出工作區裡的語言檔；選到還沒匯入的檔案時，會先詢問是否匯入。
- **表格**：MASTER 欄不能編輯。同一筆拆成的多列用相同底色分組。整個欄位一列（多行）的情況，格子裡唯讀，只能在詳細區編輯。
- **主題**：固定使用淺色主題（Fusion）。實測在 Windows 深色模式下，系統白字配上狀態的淺色底色會看不見。
- **篩選按鈕**顯示各狀態的筆數，可以和搜尋同時使用。搜尋範圍：全部／英文／MASTER／SLAVE／識別碼。
- **詳細區**：元件路徑、說明註解；MASTER 對 SLAVE 的字元級差異（用 `difflib.SequenceMatcher` 標色）；殘留簡體字標紅；SLAVE 的多行編輯框。
- **按鍵**：雙擊或 F2 編輯；Enter 存入並跳到下一列；F3／Shift+F3 跳到下一個或上一個「不同」；Ctrl+Z／Ctrl+Y 復原或重做；Ctrl+S 存檔；Ctrl+H 尋找取代；Ctrl+F 搜尋。
- 切換 MASTER 或 SLAVE、關閉程式時，如果有未存的修改，要先詢問。切換之後，選取停在原本那一筆的識別碼上。

## 6. 資料流程

```
Languages\*.lang ──匯入──▶ workspace\lang\X.lang ──load──▶ LangFile（正本）◀── 表格／批次編輯
                                    ▲                          │
                                    └──── save（備份＋原子）◀────┤
workspace\txt\X.txt ◀── 每次 save 重新產生 ─────────────────────┘
workspace\txt\X.txt ──記事本修改──▶ 監看 mtime ──▶ load_txt ──▶ 依 ADR-0008 合併或詢問
workspace\lang\X.lang ──部署（UAC、讀回驗證）──▶ Languages\X.lang
```

- 編輯（單一字串或整批）都透過 `QUndoCommand` 修改 `LangFile`，然後通知 model 更新那幾列的狀態。
- 監看 .txt：每 1 秒檢查 mtime。程式自己 save 產生的 .txt 會記下雜湊值，不會被誤判成外部修改。

## 7. 錯誤處理

| 情況 | 處理 |
|---|---|
| 解密後沒有 BOM | 不是語言檔，顯示錯誤，不載入 |
| 格式錯誤（旗標行數不符） | 顯示第幾行、哪一筆有問題，不載入（.txt 也一樣） |
| .txt 不是 UTF-8 | 提示使用者用記事本「另存新檔」選 UTF-8 |
| 存檔時有「錯誤」 | 不能存檔，列出問題並可以點擊跳到該列 |
| 存檔時有「警告」 | 列出警告，讓使用者選擇是否繼續存檔 |
| 寫入失敗（磁碟、權限） | 原子寫入保證原檔不變，顯示錯誤 |
| 部署時權限不足 | 詢問是否用 UAC；使用者按「否」時，修改保留在工作區 |
| 部署後讀回不一致 | 報錯，並顯示備份位置 |
| PL/SQL 語言目錄不存在 | 請使用者選擇目錄，記錄在 settings.json |
| 程式內與 .txt 同時有修改 | 詢問要用哪一邊（ADR-0008） |

## 8. 測試（ADR-0012）

- `tests/core/`：以 Languages 目錄的真實檔案做測試，找不到目錄時略過（`pytest.mark.skipif`）。
  - 14 個檔案 `serialize(parse(x)) == x`
  - 筆數：13 個檔案 5,876 筆、Hungarian 5,695 筆；Chinese 對 Taiwan 展開成 6,672 列，其中 49 列是多行欄位
  - 各語言的英文原文一致
  - `align(Chinese, Hungarian)` 能標出單邊的筆
  - `set_target` 只改變目標行；翻譯行數改變時，p9～p11 同步更新，而且能再次解析
  - 例外詞：「新建→新增」不會改到「重新建立」
  - 檢查規則：佔位符缺漏要判為 error；「天后」要判為 SIMPLIFIED；「游標」不能被標出
  - 原子存檔：模擬 `os.replace` 前失敗，原檔不變
  - ADR-0008：程式內與 .txt 同時修改時，能正確偵測到衝突
- `tests/ui/`（pytest-qt）：開啟 Chinese／Taiwan 後列數正確；MASTER 不能編輯；編輯後狀態變成 ✎，Ctrl+Z 能還原；切換 SLAVE 後選取停在同一個識別碼。
- 人工驗收：UAC 部署流程；在沒有安裝 Python 的環境啟動打包後的 exe。

## 9. 打包

- `uv` 管理相依套件：`pyside6`、`opencc`；開發用 `pytest`、`pytest-qt`、`pyinstaller`。
- `uv run pyinstaller --onefile --windowed --name PLLangStudio pllangstudio/__main__.py`，需要包含 OpenCC 的設定檔（`--collect-data opencc`）。
- 實測 exe 約 52 MB（ADR-0005）。

## 10. 驗收標準

1. 啟動後，預設 MASTER＝Chinese、SLAVE＝Taiwan，表格顯示 6,672 列；捲動時兩邊永遠在同一列。
2. 修改一個字串、存檔、部署後，在 PL/SQL Developer 重新啟動後能看到修改。
3. 把 Chinese.lang 用 `s2twp` 轉換，再套用預設用語表，得到的每個字串都要跟目前的 Taiwan.lang 相同（檔頭的語言名稱除外）。如果有差異，必須逐條列出並說明原因。
4. 刻意刪掉一個 `%1`，存檔會被擋下。
5. 「%1 天后過期」會出現在「殘留簡體」篩選裡；「游標」不會。
6. 所有自動測試通過。
