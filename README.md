# PLLangStudio

PL/SQL Developer 語言編輯與比對器：MASTER（唯讀）／SLAVE（可編輯）逐字串對照 `.lang` 語言檔，
可以編輯、批次修改、檢查錯誤，加密存回工作區後再部署。

- 規格：docs/superpowers/specs/2026-10-26-pllangstudio-design.md
- 決策紀錄：docs/adr/
- 術語：CONTEXT.md

## 使用
1. 執行 `PLLangStudio.exe`。第一次執行會在 exe 旁建立 `workspace\`，並自動匯入 Chinese.lang、Taiwan.lang。
   > `workspace\` 資料夾裡放的是你的修改與備份，更新或刪除 exe 資料夾時請不要連它一起刪掉。
2. 在表格的 SLAVE 欄雙擊或按 F2 編輯；多行字串在下方詳細區編輯。
3. Ctrl+S 加密存檔（只寫工作區），確認後按「部署」寫回 PL/SQL Developer（會跳 UAC），重新啟動 PL/SQL Developer 生效。

## 開發
    uv run pytest
    uv run python -m pllangstudio
    uv run pyinstaller --noconfirm --onefile --windowed --collect-all opencc --name PLLangStudio pllangstudio/__main__.py
