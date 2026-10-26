---
status: accepted
---

# 介面改用 PySide6（Qt），不沿用 tkinter

比對器的核心是一張約 8,000 列的表格，需要在格子裡直接編輯、逐格上色、顯示多行文字、快速篩選。Qt 的 `QTableView` 加上 model 原生就支援這些功能，tkinter 的 `ttk.Treeview` 都做不到，要硬做的話成本很高。

依然用 uv 管理專案、PyInstaller 打包成單一 exe。

## Considered Options

- **tkinter**：exe 約 12 MB，現有 LangEditor 也是用它。但不能在格子裡編輯，只能整列上色，多行文字顯示也差。不採用。
- **pywebview（HTML 介面）**：外觀最自由，但要同時維護 Python 和 JavaScript 兩邊，除錯也比較困難。不採用。

## Consequences

- exe 會從約 12 MB 變大到約 52 MB（實測，含 OpenCC 設定檔）。
- 狀態底色和差異標色必須跟著主題一起換：Windows 深色模式下，系統白字配上淺色的狀態底色會看不見。最初的做法是固定使用淺色主題，後來改為支援亮色／暗色／跟隨系統三種主題，見 [ADR-0013](0013-theme-modes.md)。
