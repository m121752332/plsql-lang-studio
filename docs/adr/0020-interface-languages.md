---
status: accepted
---

# 介面語言：繁體中文原文，用 Qt Linguist 翻成簡體中文、英文、日文，切換後立即生效

程式的介面文字原本全部直接寫成繁體中文。我們加上簡體中文、英文、日文三種介面語言，採用 Qt 官方的國際化做法，不自己做翻譯引擎：

- **原文就是繁體中文**：程式碼裡的字串維持繁體中文，用 `self.tr()`／`QCoreApplication.translate()` 包起來；選繁體中文時不載入本程式的 `.qm`，畫面跟以前逐字相同。
- **介面翻譯**：`translations\pllangstudio_<語言>.ts` 給翻譯者編輯（可用 PySide6 附的 `pyside6-linguist` 開啟），編成 `pllangstudio\resources\i18n\*.qm` 讓程式載入。兩種都提交進版本庫，從原始碼執行時不需要額外步驟。`uv run i18n` 一次完成收集新字串（lupdate）與編譯（lrelease）。
- **切換語言**：「配置 ▸ 外觀 ▸ 語言」，存在 `app.json`。`ui/language.LanguageManager` 換掉 `QTranslator`（本程式的 `.qm` 加上 Qt 自己的 `qtbase_<語言>.qm`），Qt 會送 `LanguageChange` 給所有視窗。
- **立即生效，不必重新啟動**：開著的視窗（主視窗、檔案清單、詳細區、事件檢視器、配置）把固定文字集中在 `_set_texts()`，建立畫面與收到 `LanguageChange` 時都呼叫它；表格標題與內容由 model 重新發出變更訊號。強制回應的對話框（尋找取代、預覽、用語對照表、訊息框）在配置視窗開著時不可能同時存在，只需要在建立時用 `tr()`。
- **core 不 import Qt**（ADR-0006）：`core/i18n.py` 提供 `translate(情境, 原文)` 與 `QT_TRANSLATE_NOOP` 標記，畫面層啟動時用 `install(QCoreApplication.translate)` 接上；核心測試沒接上時一律回傳原文。檢查結果的 `Issue.message` 在讀取時才翻譯，切換語言後表格提示會跟著換。
- **有變數的訊息用 `{名稱}` 佔位**，翻譯後再 `format()`；翻譯者可以調整語序，佔位名稱必須保留（有測試檢查）。
- **不翻譯的內容**：事件紀錄的類別與程式自己寫的紀錄內容維持繁體中文，回報問題時才看得懂；使用說明網頁與說明程式維持繁體中文（ADR-0019）；語言名稱在選單上一律用該語言自己的寫法。

## Considered Options

- **原文改成英文**：Qt 的慣例，但所有字串、測試與文件都要改寫，畫面也會跟目前不同；繁體中文是主要使用者的語言，維持原文最安全。
- **重新啟動後才生效**：只要建立畫面時用 `tr()` 就好，改動最少；使用者希望切換後立刻看到結果，所以改成每個常駐視窗都能重設文字。
- **自己做字串表（JSON／dict）**：不需要 Qt 工具，但沒有 Qt Linguist 可用，也翻不到 Qt 自己的標準按鈕與右鍵選單。
- **只翻譯 ui\\，core 的訊息維持中文**：切換成英文時會夾雜中文的錯誤與檢查訊息。

## Consequences

- pyside6-lupdate 只認得 `self.tr("原文")`、`某物.translate("情境", "原文")`（剛好兩個參數）與 `QT_TRANSLATE_NOOP("情境", "原文")`，原文必須是字面字串；f-string 不會被收集，要改成 `{名稱}` 佔位。
- `tests/test_translations.py` 會用 lupdate 重新掃描程式碼：新增或修改介面文字卻沒更新 `.ts`、有字串沒翻完、佔位名稱不一致、`.qm` 不是最新的，測試都會失敗。改了介面文字就要執行 `uv run i18n`、翻好新字串、再執行一次。
- `.ts` 不記錄原始碼行號（`-locations none`），否則程式改一行就會讓整份 `.ts` 變動。
- 復原／重做不再用 `QUndoStack.createUndoAction`：它的前置文字建立後不能換。已經做過的步驟保留當時的名稱。
- 錯誤對話框的標題與內容會照畫面上的語言記進事件紀錄；程式自己寫的紀錄（開啟、存檔、部署等）仍是繁體中文。
- 簡體中文是用 OpenCC（台灣→大陸用語）轉出初稿再人工修正；英文、日文由人工翻譯。之後新增語言只要在 `appconfig.LANGUAGES`、`ui/language.LANGUAGE_NAMES`、`release.TRANSLATION_LANGUAGES` 加上代號並翻好 `.ts`，不必改畫面程式。
