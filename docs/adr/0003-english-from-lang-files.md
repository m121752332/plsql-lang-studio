---
status: accepted
---

# 不需要 English.lang：英文原文直接取自 MASTER，MASTER 預設為 Chinese.lang 且唯讀

PL/SQL Developer 的英文介面內建在 `plsqldev.exe` 裡，`Languages` 目錄沒有 English.lang。但每個 `.lang` 的每一筆都附有英文原文（見 [ADR-0001](0001-lang-file-format.md)），而且各語言的英文完全一致。所以表格的「英文」欄直接取自 MASTER，不另外產生 English 檔案。

MASTER 預設是簡體 Chinese.lang，SLAVE 預設是繁體 Taiwan.lang。兩邊都可以用下拉選單換成任何語言檔。MASTER 一律唯讀，避免把比對的基準改掉。

## Considered Options

- **從 .lang 抽出英文，另存成虛擬的 English.lang 當 MASTER**：英文本來就在每一列的「英文」欄裡，再多一份 MASTER 是重複資訊。不採用。
