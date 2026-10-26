# PL/SQL Developer 語言檔編輯器

解密 .lang → 檢視內文 → 用記事本編輯 → 加密存回 .lang。

1. 執行 dist/LangEditor.exe（也可以把 .lang 拖到 exe 上）
2. 開啟 .lang → 解密成 temp/<名稱>.txt 並顯示
3. 用記事本編輯 → 存檔後主視窗自動更新
4. 加密存回 .lang → 在 Program Files 時會跳 UAC 要求系統管理員權限

暫存目錄：exe 旁的 temp/（不能寫入時改用 %LOCALAPPDATA%/LangEditor/temp）；每次覆蓋前備份到 temp/backup/。

開發：uv run pytest ／ uv run pyinstaller --noconfirm --onefile --windowed --name LangEditor app.py
