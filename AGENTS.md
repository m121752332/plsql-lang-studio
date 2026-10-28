# AGENTS.md

給 AI 程式助理的專案規範。開始動手前請先讀完；人類使用說明在 [README.md](README.md)，術語在 [CONTEXT.md](CONTEXT.md)，設計決策在 [docs/adr/](docs/adr/)。

## 專案概述

PLLangStudio：檢視、比對、修改 PL/SQL Developer 介面翻譯（`.lang` 語言檔）的桌面工具。Python 3.14、PySide6、OpenCC，用 uv 管理。

```text
pllangstudio/
├─ core/   不依賴 Qt 的核心邏輯（加解密、解析、比對、工作區、用語表、檢查）
├─ ui/     PySide6 畫面，只負責呈現與操作
├─ resources/  靜態檔案（圖示等），用 resources.path("檔名") 取得路徑
├─ appconfig.py / eventlog.py / elevate.py / __main__.py
tests/
├─ core/   核心模組測試
└─ ui/     pytest-qt 畫面測試
docs/adr/  架構決策紀錄（0001～0017）
```

## 常用指令

一律用 uv，不要直接呼叫系統的 `python` 或 `pip`。

| 目的 | 指令 |
|---|---|
| 安裝／同步環境 | `uv sync` |
| 執行程式 | `uv run python -m pllangstudio` |
| 跑全部測試 | `uv run pytest`（預設已用 xdist 平行，約 11 秒） |
| 單獨除錯某個測試 | `uv run pytest -n0 路徑::測試名` |
| 打包成 exe | `uv run build`（產生 `dist\PLLangStudio.exe`） |
| 產生發行 zip | `uv run package`（build 後壓成 `bin\PLLangStudio-v版本號-win64.zip`） |
| 加依賴 | `uv add 套件`；開發用加 `--dev` |

## 架構規則

- **分層不可破壞**（ADR-0006）：`core/` 不可 import PySide6；邏輯放 `core/`，`ui/` 只呼叫它。新功能先想邏輯能不能放進 `core/` 並用測試覆蓋。
- **程式內的資料是唯一正本**（ADR-0008）：記事本 `.txt` 只是交換用副本，不可讓外部 `.txt` 未經格式檢查就進入正本。
- **未修改就逐 byte 相同**（ADR-0006）：`langfile.py` 寫回時只能替換翻譯行（必要時同步旗標 p9–p11），其餘一律原樣保留。
- **編輯只發生在工作區**（ADR-0004）：只有「部署」可以寫入 PL/SQL Developer 的 Languages 目錄（`C:\Program Files`）。
- **所有寫入遵守同一套流程**（ADR-0009）：先備份 → 寫 `.tmp` → `os.replace` 原子換檔 → 讀回驗證。不允許直接覆寫、不允許只寫一半。
- **有「錯誤」不能存檔，「警告」可以**（ADR-0011）。新增檢查規則時先決定它屬於哪一級，並補測試。
- 做重大設計決策時，在 `docs/adr/` 新增下一號 ADR（格式比照既有檔案，`status: accepted`），不要只留在對話裡。

## 安全紅線

- **測試與開發時絕不寫入真實的 Languages 目錄**。需要寫入時先複製到暫存資料夾。
- 不要動使用者的工作區與 `dev-appdata/`（已被 `.gitignore` 忽略）。
- 不要直接把 `langcrypt.py` 的加解密行為改成「看起來更合理」的版本；格式是逆向分析得來，任何改動都必須通過全部真實語言檔的逐 byte 往返測試。

## 術語

介面文字、文件、commit 訊息一律使用 [CONTEXT.md](CONTEXT.md) 的詞，並避開它列出的 _Avoid_ 詞。常用的：語言檔、筆、字串、識別碼、英文原文、說明註解、**主語系**／**副語系**（不要寫 MASTER／SLAVE）、工作區、部署、用語對照表、例外詞、錯誤、警告。新增概念時順手補進 CONTEXT.md。

## 測試規範

- 核心測試以真實語言檔為準（ADR-0012）；找不到 Languages 目錄時略過，不可失敗。
- **測試不可依賴 Taiwan.lang 目前的內容**（例如特定筆數或特定錯字），因為使用者會持續修改它。
- 新功能或修 bug：先寫會失敗的測試，再實作。畫面行為用 pytest-qt。
- 提交前 `uv run pytest` 必須全過；回報時要貼實際結果，不要只說「應該沒問題」。
- 測試要能平行執行（xdist）：不可共用固定路徑或全域狀態，暫存檔用 `tmp_path`。

## 撰寫風格

- 使用者介面、說明文件、註解、ADR 一律用**繁體中文（台灣用語）**。程式識別字用英文。
- 沿用周圍程式碼的命名、註解密度與慣用寫法，不要順手重構無關的程式。
- 不加沒被要求的功能、抽象層或過度的錯誤處理。

## 檔案編碼（Windows 陷阱）

- 所有文字檔都是 **UTF-8**。
- 此環境的 Bash 對中文的處理不可靠：`sed -i`、heredoc（`cat <<EOF`）、`echo` 寫入含中文的內容可能被轉成 Big5，把檔案弄壞。**含中文的檔案請用 Write／Edit 工具修改**，改完確認仍是合法 UTF-8。

## Git 與版本

- 主要分支是 `master`，遠端是 `origin`（GitHub：m121752332/plsql-lang-studio）。
- Commit 訊息用 Conventional Commits 前綴（`feat` `fix` `docs` `test` `chore`，可加範圍如 `feat(ui):`），描述用繁體中文。
- 未經使用者要求，不要 commit、push、建立 tag 或改寫歷史。版本號在 [pyproject.toml](pyproject.toml)，上 tag 時要與它一致（例如 `v0.1.0`）。
- 升級 Python 或依賴後，`uv.lock` 要一起提交。
