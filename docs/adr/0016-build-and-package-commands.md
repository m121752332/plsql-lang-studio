---
status: accepted
---

# 用 uv run build／uv run package 打包與產生發行 zip，靜態檔案放在 pllangstudio/resources

原本打包要手打一長串 PyInstaller 參數，而且搭配 `--specpath build` 時，`--add-data`、`--icon` 的相對路徑是從 `build\` 算起，很容易打錯。發行用 zip 也是手動壓縮。我們把這兩件事做成指令：

- `uv run build`：用固定參數執行 PyInstaller，產生 `dist\PLLangStudio.exe`。
- `uv run package`：先 build，再把 exe、`README.md`、`LICENSE` 壓成 `bin\PLLangStudio-v版本號-win64.zip`。版本號以 `pyproject.toml` 為準。zip 先寫 `.tmp` 再 `os.replace`，不會留下壞掉的一半。
- 邏輯放在 `pllangstudio/release.py`，用 `[project.scripts]` 註冊成指令。程式本身不 import 它，所以不會被包進 exe。參數一律用絕對路徑，避開 `--specpath` 的相對路徑問題。
- 為了讓 `[project.scripts]` 生效，`pyproject.toml` 加上建置後端 `uv_build`，uv 會把本專案以可編輯模式裝進 `.venv`。
- 說明程式加入後（[ADR-0019](0019-help-webpage.md)），`uv run build` 另外產生 `dist\PLLangHelp\` 資料夾，`uv run package` 的 zip 也一併帶入。主程式仍是一支 onefile exe。
- 圖示等靜態檔案放在 `pllangstudio/resources/`，用 `resources.path("檔名")` 取得路徑；打包時用 `--add-data` 整個資料夾帶進 exe。放在套件裡面，從原始碼執行和從 exe 執行都用同一段程式找得到檔案。

## Considered Options

- **PowerShell 或 .bat 腳本**：要另外記指令名稱，也沒辦法寫測試。不採用。
- **提交 PLLangStudio.spec**：`.spec` 已被 `.gitignore` 忽略，而且裡面寫死相對路徑，仍然要處理 `build\` 起算的問題。不採用。
- **靜態檔案放在專案根目錄的 assets/**：從原始碼執行時要另外推算路徑，和 exe 裡的位置不一致。不採用。
