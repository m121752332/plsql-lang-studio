---
status: accepted
---

# 主程式改用資料夾形式（onedir）打包，啟動時先顯示視窗再載入語言檔

主程式原本打包成單一 exe（[ADR-0016](0016-build-and-package-commands.md)），從雙擊到看到視窗要 3 秒以上。量測（v0.5.0，同一台電腦，各量 5 次）拆開後：

- **onefile 解壓**：單一 exe 每次啟動都要把約 142 MB 解壓到暫存資料夾，防毒軟體還會逐一掃描，約多 1.3～1.5 秒。用 Python 直接執行約 1.9 秒，exe 約 3.2 秒。
- **Qt 字型**：第一次量字寬時建立字型資料庫，畫面上的 emoji 與符號（🔒 ✓ 💾 ⚠ 等）又要找備用字型，合計約 0.6 秒。換字型引擎（GDI、FreeType）或指定備用字型都沒有比較快，是固定成本。
- **載入語言檔**：解密、解析、比對 6,672 列並同步 .txt，約 0.5 秒。

我們做了三件事：

- **主程式改用 onedir**：`dist\PLLangStudio\` 裡是 `PLLangStudio.exe`、`_internal\`（程式本體）與說明程式 `PLLangHelp\`。開程式不必解壓，exe 啟動約 1.7 秒。
- **刪掉用不到的檔案**：建置後 `release.prune_main_dir` 刪掉軟體 OpenGL（`opengl32sw.dll`）、只被虛擬鍵盤外掛用到的 QML／Quick、只被 PDF 圖片外掛用到的 `Qt6Pdf.dll`、介面語言以外的 Qt 翻譯、OpenCC 的靜態函式庫與命令列工具；`PySide6.QtNetwork` 用 `--exclude-module` 排除。約省下 51 MB。
- **先顯示視窗再載入語言檔**：`MainWindow(None)` 不開啟工作區，`__main__` 先 `show()` 並畫出空的視窗，再呼叫 `open_workspace()`。用 Python 執行時看到視窗的時間從 1.9 秒降到約 1.45 秒。

發行 zip 的最外層就是 `PLLangStudio.exe`，不另外包一層資料夾。預設工作區是「exe 所在資料夾\workspace」，這樣解壓後 `workspace\` 仍在 exe 旁邊，與舊版相同；使用者升級時換掉 `PLLangStudio.exe`、`_internal\`、`PLLangHelp\` 即可。

說明程式先打包到 `build\dist\PLLangHelp\`，再複製進 `dist\PLLangStudio\`。它與它用到的檔案（`helpviewer\`、`core\helpdoc.py`、`resources\`、`release.py`、`uv.lock`、Python 版本）的指紋沒變時，下次打包直接沿用，不重新打包。PyInstaller 會把 `__main__` 直接加進我們傳入的排除清單，存進快取後與下次的清單比對不符，每次都重新分析；主程式先自己排除 `__main__`，沒改程式時重新打包只要幾秒。

## Considered Options

- **維持 onefile，只刪用不到的檔案**：解壓量少一半，預估仍要 2.5 秒左右，達不到 1～2 秒的目標。不採用。
- **zip 裡多包一層 `PLLangStudio\` 資料夾**：比較整齊，但預設工作區會變成程式資料夾裡面的 `workspace\`，使用者升級時若整個刪掉舊資料夾就會連修改一起刪掉。不採用。
- **把畫面上的 emoji 換成一般字型就有的符號**：只能省下找備用字型的時間，而工具列、狀態欄都用到 emoji，要全面改介面。不採用。

## Consequences

- 每次打包都會整個清掉重建 `dist\PLLangStudio\`，開發時不要把工作區放在裡面。
- 發行檔從一支 exe 變成 exe 加上 `_internal\` 資料夾，使用者不能只複製 exe 到別處執行。
- 刪檔清單是依目前的 PySide6 版本整理的；升級 PySide6 後要確認打包出來的程式仍能正常開啟、切換介面語言。
