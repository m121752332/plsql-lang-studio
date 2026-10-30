# 使用說明改為內嵌網頁：設計

日期：2026-10-30
狀態：已確認設計，待寫實作計畫

## 背景

目前按 F1（關於 ▸ 使用說明）只會跳出一個 `QMessageBox`，內容是七行純文字（`pllangstudio/ui/main_window.py` 的 `show_help()`）。資訊量不足，也沒有圖。README.md 第 1～15 節已經有完整的使用者說明，但不在程式裡。

目標：按 F1 開啟一個用網頁呈現的使用說明，有目錄、搜尋、截圖、跟隨主題，並能依目前畫面開到對應章節。

## 決策摘要

| 項目 | 決定 | 理由 |
|---|---|---|
| 瀏覽器元件 | Qt WebEngine（Chromium） | CEF 的 Python 綁定（cefpython3）已停止維護，不支援 Python 3.14；PySide6 已內建 Qt WebEngine，核心同為 Chromium，不需新依賴 |
| 放在哪個行程 | 獨立的說明程式 `PLLangHelp` | Chromium 本體 `Qt6WebEngineCore.dll` 約 194 MB 且由載入它的行程使用，只把 `QtWebEngineProcess.exe` 移出去無法讓主程式變小；拆成獨立程式後主程式維持約 53 MB、啟動不變慢，且不會被模態對話框擋住 |
| 打包方式 | 主程式維持 `--onefile`；說明程式用 `--onedir` | 不推翻「一支 exe」的發行方式；說明程式用資料夾形式避免每次解壓 Chromium |
| 找不到說明程式時 | 用系統預設瀏覽器開同一份網頁 | 功能不消失，只是不能即時換主題 |

## 1. 網頁內容

檔案位置：`pllangstudio/resources/help/`

```text
help/
├─ index.html   單頁，全部章節
├─ help.css     亮色與暗色（GitHub Dark）兩組配色，以 html[data-theme] 切換
├─ help.js      目錄捲動同步、搜尋過濾、setTheme()、讀取網址參數
└─ img/*.png    介面截圖
```

- 內容改寫自 README.md 第 1～15 節；第 16、17 節（從原始碼執行、給開發者）不放。用詞遵守 CONTEXT.md。
- 版面：左側目錄＋搜尋框，右側內文。搜尋框輸入關鍵字時即時過濾章節並標示命中文字；捲動時目錄標示目前章節。
- 網址參數：`index.html?theme=light|dark#章節代號`。沒帶 `theme` 時依 `prefers-color-scheme`。
- 不連外、不用 CDN、不載入外部字型。外部連結（GitHub）由說明程式交給系統瀏覽器開。

### 章節代號

章節代號是主程式與網頁之間的約定，集中定義在 `core/helpdoc.py`，測試會檢查 `index.html` 內每個代號都有對應的 `id`。

| 代號 | 章節 | README 來源 |
|---|---|---|
| `overview` | 這個工具在做什麼 | §1 |
| `terms` | 先認識幾個名詞 | §2 |
| `quick-start` | 第一次使用 | §3 |
| `screen` | 畫面介紹 | §4 |
| `edit` | 修改一個翻譯 | §5 |
| `markers` | 表格符號、錯誤與警告、篩選 | §6 |
| `batch` | 批次工具總覽與預覽 | §7 |
| `replace` | 尋找取代 | §7 |
| `s2twp` | 簡→繁 | §7 |
| `glossary` | 用語對照表 | §7 |
| `save-deploy` | 存檔和部署 | §8 |
| `notepad` | 用記事本修改 | §9 |
| `theme-font` | 主題與字型 | §10 |
| `event-log` | 事件紀錄 | §11 |
| `safety` | 安全機制與備份 | §12 |
| `shortcuts` | 快速鍵一覽 | §13 |
| `faq` | 常見問題 | §14 |
| `files` | 檔案放在哪裡 | §15 |

### F1 對應的章節

| 按 F1 的位置 | 開啟章節 |
|---|---|
| 主視窗 | 無（頁首） |
| 尋找取代（`ReplaceDialog`） | `replace` |
| 批次預覽（`PreviewDialog`） | `batch` |
| 用語對照表（`GlossaryDialog`） | `glossary` |
| 配置（`SettingsDialog`） | `theme-font` |
| 事件檢視器（`EventViewer`） | `event-log` |

## 2. 程式結構

### `pllangstudio/core/helpdoc.py`（不依賴 Qt）

- `TOPICS`：章節代號清單。
- `help_url(index: Path, topic: str | None, theme: str) -> str`：組出 `file:///…/index.html?theme=dark#glossary`。未知的章節代號視為 `None`。
- 指令格式（主程式 → 說明程式的 stdin，一行一個，UTF-8）：
  - `show <章節代號或 -> <light|dark>`：切到章節（`-` 表示頁首）、套用主題、把視窗帶到前面。
  - `theme <light|dark>`：只換主題。
  - `format_command(...)` 產生、`parse_command(line)` 解析；無法解析的行忽略。
- `find_help_program(exe_dir: Path) -> Path | None`：exe 執行時找 `exe_dir / "PLLangHelp" / "PLLangHelp.exe"`。

### `pllangstudio/helpviewer/`（說明程式）

- `__main__.py`：入口。命令列參數 `--topic`、`--theme`；建立 `QApplication` 前設定 `Qt.AA_ShareOpenGLContexts`。
- `window.py`：`HelpWindow`，內含 `QWebEngineView`。
  - `apply(cmd)`：`show` 改網址片段（同頁時只用 JS 捲動，不重新載入）並 `setTheme()`；`theme` 只呼叫 `setTheme()`。
  - 外部連結：攔截非 `file:` 的導覽請求，改用 `QDesktopServices.openUrl`。
  - 視窗大小固定預設值（約 1100×760），置中於螢幕；不記憶位置（主程式也沒有記憶視窗位置）。
- stdin 讀取：背景執行緒逐行讀 stdin，以 signal 送回主執行緒呼叫 `apply()`；讀到 EOF（主程式關閉或結束）就結束說明程式。
- 網頁檔路徑：原始碼執行時用 `resources.path("help/index.html")`；打包後由 `--add-data` 帶入，路徑規則相同。

### `pllangstudio/ui/help_launcher.py`（主程式端）

- `HelpLauncher(QObject)`：持有一個 `QProcess`。
  - `show(topic: str | None)`：行程沒在跑 → 啟動（帶 `--topic`、`--theme`）；在跑 → 寫 `show …` 到 stdin。
  - 連接 `ThemeManager.changed`：行程在跑時寫 `theme …`。
  - 啟動的程式：
    - 原始碼執行（`sys.frozen` 不存在）：`sys.executable -m pllangstudio.helpviewer`。
    - exe 執行：`find_help_program()` 找到的 `PLLangHelp.exe`。
    - 找不到：`QDesktopServices.openUrl(help_url(...))` 用系統瀏覽器開。onefile 解壓出來的網頁在暫存資料夾，程式結束後會被刪掉，瀏覽器已開的頁面不受影響，重新整理才會失效；這是退路，可接受。
  - 啟動的程式路徑可由建構子注入，供測試使用假程式。
  - 啟動失敗時記事件紀錄並改用系統瀏覽器開。
- 主程式**不 import** 任何 `QtWebEngine` 模組。

### 掛上 F1

- 主視窗：`show_help()` 改成 `self.help.show(None)`；原本的 `QMessageBox` 文字移除。
- 各對話框：提供一個小函式 `install_help(widget, topic, launcher)`，在該視窗加上 F1 的 `QShortcut`。對話框建構時需要拿到 launcher（由主視窗傳入）。
- 因為說明是另一個行程，模態對話框開著時說明視窗仍可操作。

## 3. 截圖

- 用 pyside6-mcp 在**暫存資料夾建立的工作區**操作與截圖，不讀寫使用者的工作區、不按部署、不存檔到使用者資料。
- 只拍亮色一套：主視窗全貌、檔案清單右鍵選單、詳細區、尋找取代與預覽、用語對照表、配置、事件檢視器。
- 存成 `resources/help/img/*.png`，必要時縮小以控制體積。

## 4. 打包

- `release.py`：
  - 主程式：沿用現有參數，另加 `--exclude-module` 排除 `PySide6.QtWebEngineCore`、`PySide6.QtWebEngineWidgets`、`PySide6.QtWebChannel`、`PySide6.QtWebEngineQuick`，確保不被誤帶進去。
  - 說明程式：`--onedir --windowed --name PLLangHelp`，入口 `pllangstudio/helpviewer/__main__.py`，`--add-data` 帶 `resources`，輸出到 `dist\PLLangHelp\`。
  - `uv run build` 依序建兩份。
  - `make_zip` 加入 `PLLangHelp\` 整個資料夾。
- 完成後實際量測 exe、說明程式資料夾、zip 的大小並回報。

## 5. 測試

先寫會失敗的測試，再實作。全部需可用 xdist 平行執行，暫存檔用 `tmp_path`。

- `tests/core/test_helpdoc.py`
  - `help_url` 對各章節與主題的結果；未知章節視為頁首。
  - `format_command` / `parse_command` 往返；錯誤格式回傳 `None`。
  - `find_help_program` 有檔案與沒檔案的情況。
  - `index.html` 內每個 `TOPICS` 代號都有對應 `id`；每個 `<img src>` 指向的檔案都存在（用 `html.parser` 解析）。
- `tests/ui/test_help_launcher.py`
  - 用假說明程式（`tmp_path` 下的 Python 腳本，把命令列參數與 stdin 收到的每行寫入檔案）：
    - 第一次 `show` 會啟動並帶正確參數；第二次只寫 `show` 指令，不重新啟動。
    - 切換主題時送出 `theme` 指令；行程沒在跑時不送。
    - 程式不存在時改走系統瀏覽器（攔截 `QDesktopServices.openUrl`）。
  - 主視窗與各對話框按 F1 時送出的章節代號正確。
- `tests/ui/test_help_viewer.py`
  - `HelpWindow.apply()` 收到 `show glossary dark` 後網址片段為 `glossary`、主題為 `dark`。
  - 外部連結不在視窗內導覽。
  - 此檔需在建立 `QApplication` 前設定 `AA_ShareOpenGLContexts`（於 `tests/ui/conftest.py` 或該檔處理）。
- 測試不依賴 Taiwan.lang 的內容，也不寫入真實的 Languages 目錄。

## 6. 文件

- 新增 `docs/adr/0019-help-webpage.md`：說明改用網頁、選 Qt WebEngine 而非 CEF、拆成獨立說明程式的理由與體積取捨。
- 更新 ADR-0016 的發行內容描述（zip 多了 `PLLangHelp\`）。
- CONTEXT.md 補「使用說明」「說明程式」兩個詞。
- README.md：開頭註明程式內按 F1 可看網頁版說明；第 15 節補上 `PLLangHelp\` 資料夾的用途。

## 不做的事

- 不做多語系說明（只有繁體中文）。
- 不拍暗色截圖。
- 不從 README 自動產生網頁（兩份分開維護，網頁以 README 為底本手動改寫）。
- 說明程式不做單獨啟動用的捷徑或安裝程式。
