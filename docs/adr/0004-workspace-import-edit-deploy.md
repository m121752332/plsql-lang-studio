---
status: accepted
---

# 工作區流程：匯入 → 編輯 → 部署，只有「部署」會寫入 Program Files

PL/SQL Developer 的 `Languages` 目錄位於 `C:\Program Files`，寫入需要系統管理員權限（UAC），而且那是正在使用中的語言檔。所以所有編輯和存檔都只在**工作區**進行。使用者確認沒問題後，按「部署」才會先備份舊檔，再透過 UAC 寫回 Program Files。

工作區結構：

```
workspace\
├─ lang\           匯入的 .lang（加密存檔寫回這裡）
├─ txt\            解密後的 .txt（檢視、記事本編輯）
├─ backup\         每次存檔／部署前的備份，檔名含日期時間
├─ glossary.json   用語對照表
└─ settings.json   PL/SQL 語言目錄、上次選的 MASTER/SLAVE
```

## Considered Options

- **直接存回原位置**（現有 LangEditor 的做法）：步驟少，但每次存檔都會跳 UAC，而且改到一半的檔案就會直接生效。不採用。
