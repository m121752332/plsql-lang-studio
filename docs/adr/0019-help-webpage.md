---
status: accepted
---

# 使用說明改用網頁，由獨立的說明程式以 Qt WebEngine 顯示

原本按 F1 只跳出一個 `QMessageBox`，七行純文字，沒有圖、沒有目錄，也看不出目前的對話框怎麼用。README 雖然有完整說明，但不在程式裡。我們把使用說明做成本機靜態網頁，由另一支「說明程式」顯示：

- **網頁**：`pllangstudio/resources/help/`（`index.html`、`help.css`、`help.js`、`img/`），內容以 README 第 1～15 節為底本改寫，加上介面截圖。左側目錄可搜尋；亮色與暗色兩組配色，暗色與主程式同為 GitHub Dark。不連外、不用 CDN，外部連結交給系統瀏覽器。
- **章節代號**：`core/helpdoc.TOPICS` 是主程式與網頁的約定，每個代號對應網頁裡同名的 `id`（有測試檢查）。主視窗按 F1 開頁首；尋找取代、批次預覽、用語對照表、配置、事件檢視器各自開對應章節。
- **說明程式**：`pllangstudio/helpviewer/`，打包成 `PLLangHelp\PLLangHelp.exe`（onedir），放在 `PLLangStudio.exe` 旁邊。主程式用 `QProcess` 啟動它，帶 `--listen --topic 代號 --theme light|dark`；已在執行時改從 stdin 送一行指令：`show <代號或 -> <light|dark>`、`theme <light|dark>`。說明程式讀到 stdin 結尾（主程式關閉）就結束。
- **主程式不載入 Qt WebEngine**：不 import 任何 `QtWebEngine*` 模組，打包時也明確排除。找不到說明程式或啟動失敗時，記一筆錯誤並改用系統預設瀏覽器開同一份網頁。

## Considered Options

- **CEF（cefpython3）**：使用者原本提議的方案。它的 Python 綁定已停止維護，不支援 Python 3.14。Qt WebEngine 核心同樣是 Chromium，而且 PySide6 已內建，不需新依賴。
- **WebEngine 直接放進主程式**：最簡單，但 Chromium 本體 `Qt6WebEngineCore.dll` 約 194 MB，加上資源檔，onefile 的 exe 會從約 53 MB 變成 200 MB 上下，每次啟動都要解壓，開程式明顯變慢。只把 `QtWebEngineProcess.exe` 放到外面沒有用，因為那支只有 0.8 MB，大的 DLL 仍由主程式載入。拆成獨立行程後，主程式大小與啟動速度不變，說明視窗也不會被主程式的模態對話框擋住，說明程式當掉也不影響主程式。
- **整個程式改成 onedir**：exe 會變小、啟動最快，但發行方式從「一支 exe」變成「一個資料夾」，推翻 ADR-0016 的做法。
- **QTextBrowser**：體積不變，但不支援 JavaScript 與較新的 CSS，做不出搜尋與版面。
- **只用系統瀏覽器開**：功能完整、體積不變，但說明不在程式視窗內、無法跟著主題即時切換；保留作為找不到說明程式時的退路。

## Consequences

- 實際大小（v0.3.0 開發中量測）：`PLLangStudio.exe` 約 54 MB；`PLLangHelp\` 約 414 MB；發行 zip 約 226 MB。說明程式建置後會刪掉用不到的檔案（除錯用 pak、開發者工具、其他語言的翻譯與 QML 模組，約 159 MB），見 `release.prune_help_dir`。
- 網頁內容與 README 分開維護，改功能時兩邊都要更新。
- 說明程式從 stdin 讀指令時直接用 `os.read` 讀檔案描述元：若在 daemon 執行緒裡卡在 `sys.stdin` 讀取，使用者先關掉說明視窗時，Python 結束會出現 Fatal Python error。
- 說明程式關閉 Chromium 的視窗遮蔽偵測（`--disable-features=CalculateNativeWinOcclusion`），否則被主程式蓋住後再帶到前面，可能一直是黑畫面或舊畫面。
- Windows 不讓背景行程自己搶到前景，主程式送 `show` 指令前會呼叫 `AllowSetForegroundWindow` 授權。
