# PLLangStudio

PL/SQL Developer 語言編輯與比對器：主語系（唯讀）／副語系（可編輯）逐字串對照 `.lang` 語言檔，
可以編輯、批次修改、檢查錯誤，加密存回工作區後再部署。

- 規格：docs/superpowers/specs/2026-10-26-pllangstudio-design.md
- 決策紀錄：docs/adr/
- 術語：CONTEXT.md

## 使用
1. 執行 `PLLangStudio.exe`。第一次執行會在 exe 旁建立 `workspace\`，並自動匯入 Chinese.lang、Taiwan.lang。
   > `workspace\` 資料夾裡放的是你的修改與備份，更新或刪除 exe 資料夾時請不要連它一起刪掉。
2. 左側上方是工作區的語言檔，下方是 PL/SQL Developer 的語言檔（雙擊即可匯入）；按右鍵可設為主語系或副語系。
3. 在表格的副語系欄雙擊或按 F2 編輯；多行字串在下方詳細區編輯。
4. Ctrl+S 加密存檔（只寫工作區），確認後 檔案 ▸ 部署到 PL/SQL Developer（會跳 UAC），重新啟動 PL/SQL Developer 生效。
5. 編輯 ▸ 主題：亮色、暗色或跟隨系統（預設），選擇會記住。
6. 也可以用記事本修改副語系的 `.txt`，存檔後自動載入；只能改翻譯，不能新增或刪除筆，檔案損毀時會先備份再改回原本內容。

## 開發
    uv run pytest
    uv run python -m pllangstudio
    uv run pyinstaller --noconfirm --onefile --windowed --collect-all opencc --name PLLangStudio pllangstudio/__main__.py
