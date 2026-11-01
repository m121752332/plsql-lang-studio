---
status: accepted
---

# 程式內附 Taiwan.lang，PL/SQL Developer 沒有時放進工作區

PL/SQL Developer 原本只附簡體的 Chinese.lang，沒有繁體的 Taiwan.lang。副語系預設是 Taiwan.lang（[ADR-0003](0003-english-from-lang-files.md)），新安裝的電腦上第一次開程式時，Languages 目錄找不到它，就沒辦法自動匯入，也沒有檔案可以部署。

我們把 Taiwan.lang 放進 `pllangstudio/resources/`，跟著程式一起版控與打包（**內附語言檔**）。開啟工作區時，主語系或副語系不在工作區的話：

- Languages 目錄有這個檔：照舊從那裡匯入。
- Languages 目錄沒有、但程式內附：把內附的版本放進工作區（`Workspace.add_bundled`），並寫一筆事件紀錄。之後照一般流程編輯、存檔、部署；部署時 Languages 目錄沒有同名檔，直接寫入，不需要備份。

工作區已經有同名檔時一律不動，避免蓋掉使用者的修改。內附的版本是由 Chinese.lang 複製、改檔頭語言名稱並轉成繁體而來；更新它時直接換掉 `resources/Taiwan.lang` 並提交。`.gitattributes` 把 `*.lang` 標成二進位，避免 Git 轉換換行把加密內容弄壞。

測試的 `langdata.lang_path()` 也一樣：Languages 目錄沒有的檔案改讀內附的版本，讓需要 Taiwan.lang 的測試在沒有它的電腦上仍能執行。

## Considered Options

- **第一次啟動時自動把 Chinese.lang 複製成 Taiwan.lang**：不必內附檔案，但得到的是簡體內容，使用者要從頭轉換與校對，已經修好的翻譯無法帶到別台電腦。不採用。
- **直接把內附的 Taiwan.lang 寫進 Languages 目錄**：違反「只有部署可以寫入 Languages 目錄」（[ADR-0004](0004-workspace-import-edit-deploy.md)），而且要提升權限。不採用。

## Consequences

- 安裝包多了約 0.8 MB。說明程式也帶著整個 `resources/`，所以會多一份，並且換掉內附的 Taiwan.lang 時說明程式會重新打包。
- 內附的版本跟著 PL/SQL Developer 的版本走；PL/SQL Developer 升級、筆的組成改變時，要重新產生並提交。
