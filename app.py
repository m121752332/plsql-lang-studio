"""PL/SQL Developer 語言檔編輯器：解密 .lang → 檢視 → 用記事本編輯 → 加密存回。"""

import ctypes
import os
import shutil
import subprocess
import sys
import tkinter as tk
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pllangstudio.core import langcrypt

APP_TITLE = "PL/SQL Developer 語言檔編輯器"
DEFAULT_DIR = r"C:\Program Files\PLSQL Developer 17\Languages"
POLL_MS = 1000


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def make_temp_dir() -> Path:
    """優先用 exe 旁邊的 temp 目錄；沒有寫入權限時改用 %LOCALAPPDATA%。"""
    for d in (app_dir() / "temp", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LangEditor" / "temp"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_bytes(b"")
            probe.unlink()
            return d
        except OSError:
            continue
    raise RuntimeError("找不到可寫入的暫存目錄")


# ---- 以系統管理員權限複製檔案（寫入 Program Files 時使用） ----

class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def elevated_copy(src: Path, dst: Path) -> bool:
    """跳出 UAC 視窗，以系統管理員身分執行 copy。回傳是否成功。"""
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "cmd.exe"
    info.lpParameters = f'/c copy /y "{src}" "{dst}"'
    info.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return False  # 使用者在 UAC 按了「否」
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return code.value == 0


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.temp_dir = make_temp_dir()
        self.lang_path: Path | None = None
        self.txt_path: Path | None = None
        self.saved_plain = b""  # 最後一次載入／存檔時的明文，用來判斷是否有未存回的修改
        self.txt_mtime = 0.0
        self.dirty = False

        root.title(APP_TITLE)
        root.geometry("1000x700")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.set_buttons()
        root.after(POLL_MS, self.poll)

    # ---------- UI ----------

    def build_ui(self):
        bar = ttk.Frame(self.root, padding=(6, 6, 6, 0))
        bar.pack(fill="x")
        self.btn_open = ttk.Button(bar, text="開啟 .lang…", command=self.open_dialog)
        self.btn_edit = ttk.Button(bar, text="用記事本編輯", command=self.edit_in_notepad)
        self.btn_reload = ttk.Button(bar, text="重新整理檢視", command=self.reload_view)
        self.btn_save = ttk.Button(bar, text="加密存回 .lang", command=self.save)
        self.btn_save_as = ttk.Button(bar, text="另存新檔…", command=self.save_as)
        self.btn_temp = ttk.Button(bar, text="開啟暫存目錄", command=lambda: os.startfile(self.temp_dir))
        for b in (self.btn_open, self.btn_edit, self.btn_reload, self.btn_save, self.btn_save_as, self.btn_temp):
            b.pack(side="left", padx=(0, 4))

        find = ttk.Frame(self.root, padding=6)
        find.pack(fill="x")
        ttk.Label(find, text="尋找：").pack(side="left")
        self.find_var = tk.StringVar()
        entry = ttk.Entry(find, textvariable=self.find_var, width=40)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.find_next())
        ttk.Button(find, text="下一個", command=self.find_next).pack(side="left", padx=4)
        self.path_var = tk.StringVar(value="尚未開啟檔案")
        ttk.Label(find, textvariable=self.path_var, foreground="#555").pack(side="left", padx=12)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=6)
        self.text = tk.Text(body, wrap="none", font=("Microsoft JhengHei UI", 11), undo=False)
        ys = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        xs = ttk.Scrollbar(body, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set, state="disabled")
        self.text.tag_configure("hit", background="#ffe066")
        self.text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.text.bind("<ButtonRelease-1>", lambda e: self.update_status())

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, padding=6, anchor="w").pack(fill="x")
        self.update_status()

    def set_buttons(self):
        state = "normal" if self.lang_path else "disabled"
        for b in (self.btn_edit, self.btn_reload, self.btn_save, self.btn_save_as):
            b.configure(state=state)

    def update_status(self):
        parts = [f"暫存目錄：{self.temp_dir}"]
        if self.lang_path:
            line = self.text.index("insert").split(".")[0]
            parts.insert(0, f"游標第 {line} 行（記事本 Ctrl+G 可跳行）")
            parts.insert(0, "● 有修改尚未加密存回" if self.dirty else "✓ 已與 .lang 同步")
        self.status_var.set("    |    ".join(parts))
        title = APP_TITLE + (f" - {self.lang_path.name}" if self.lang_path else "")
        self.root.title(("* " if self.dirty else "") + title)

    def show_text(self, plain: bytes, keep_position: bool):
        pos, cursor = self.text.yview()[0], self.text.index("insert")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", plain.decode("utf-8-sig", errors="replace").replace("\r\n", "\n"))
        self.text.configure(state="disabled")
        if keep_position:
            self.text.yview_moveto(pos)
            self.text.mark_set("insert", cursor)
        else:
            self.text.mark_set("insert", "1.0")

    # ---------- 檔案操作 ----------

    def open_dialog(self):
        if not self.confirm_discard():
            return
        initial = DEFAULT_DIR if Path(DEFAULT_DIR).is_dir() else None
        path = filedialog.askopenfilename(
            title="開啟語言檔", initialdir=initial, filetypes=[("PL/SQL Developer 語言檔", "*.lang"), ("所有檔案", "*.*")]
        )
        if path:
            self.open_lang(Path(path))

    def open_lang(self, path: Path):
        try:
            plain = langcrypt.decrypt(path.read_bytes())
        except Exception as e:
            messagebox.showerror("無法開啟", f"{path}\n\n{e}")
            return
        txt = self.temp_dir / (path.stem + ".txt")
        if txt.exists() and langcrypt.normalize_text(txt.read_bytes()) != plain:
            keep = messagebox.askyesno(
                "發現未存回的修改",
                f"暫存目錄裡的 {txt.name} 跟 {path.name} 內容不同（可能是上次編輯後沒有加密存回）。\n\n"
                "是 → 保留暫存檔的修改繼續編輯\n否 → 捨棄修改，重新從 .lang 解密",
            )
            if not keep:
                txt.write_bytes(plain)
        else:
            txt.write_bytes(plain)
        self.lang_path, self.txt_path, self.saved_plain = path, txt, plain
        self.path_var.set(str(path))
        self.reload_view(keep_position=False)
        self.set_buttons()

    def reload_view(self, keep_position=True):
        if not self.txt_path or not self.txt_path.exists():
            return
        raw = self.txt_path.read_bytes()
        self.txt_mtime = self.txt_path.stat().st_mtime
        try:
            self.dirty = langcrypt.normalize_text(raw) != self.saved_plain
        except UnicodeDecodeError:
            self.dirty = True
        self.show_text(raw, keep_position)
        self.update_status()

    def edit_in_notepad(self):
        subprocess.Popen(["notepad.exe", str(self.txt_path)])

    def poll(self):
        """記事本存檔後自動重新整理檢視。"""
        try:
            if self.txt_path and self.txt_path.exists() and self.txt_path.stat().st_mtime != self.txt_mtime:
                self.reload_view()
        finally:
            self.root.after(POLL_MS, self.poll)

    def build_encrypted(self) -> tuple[bytes, bytes] | None:
        raw = self.txt_path.read_bytes()
        try:
            plain = langcrypt.normalize_text(raw)
        except UnicodeDecodeError as e:
            messagebox.showerror("編碼錯誤", f"{self.txt_path.name} 不是 UTF-8 編碼，請在記事本「另存新檔」選 UTF-8 後再試。\n\n{e}")
            return None
        old_lines, new_lines = self.saved_plain.count(b"\n"), plain.count(b"\n")
        if old_lines != new_lines and not messagebox.askyesno(
            "行數不同",
            f"原本 {old_lines + 1} 行，現在 {new_lines + 1} 行。\n"
            "每筆翻譯的行數必須固定，增減行數可能讓 PL/SQL Developer 讀不到翻譯。\n\n確定還是要存檔嗎？",
        ):
            return None
        return plain, langcrypt.encrypt(plain)

    def write_lang(self, dst: Path) -> bool:
        built = self.build_encrypted()
        if not built:
            return False
        plain, data = built
        if dst.exists():
            backup = self.temp_dir / "backup"
            backup.mkdir(exist_ok=True)
            shutil.copy2(dst, backup / f"{dst.stem}_{datetime.now():%Y%m%d_%H%M%S}.lang")
        try:
            dst.write_bytes(data)
        except PermissionError:
            staged = self.temp_dir / (dst.stem + ".lang")
            staged.write_bytes(data)
            if not messagebox.askyesno(
                "需要系統管理員權限",
                f"沒有權限寫入：\n{dst}\n\n要用系統管理員身分寫入嗎？（會跳出 UAC 確認視窗）",
            ):
                messagebox.showinfo("已存到暫存目錄", f"加密後的檔案已存到：\n{staged}\n\n可以自行複製過去。")
                return False
            if not elevated_copy(staged, dst) or dst.read_bytes() != data:
                messagebox.showerror("寫入失敗", f"系統管理員複製沒有成功。\n加密後的檔案在：\n{staged}")
                return False
        self.saved_plain = plain
        self.reload_view()
        return True

    def save(self):
        if self.write_lang(self.lang_path):
            messagebox.showinfo("完成", f"已加密存回：\n{self.lang_path}\n\n重新啟動 PL/SQL Developer 後生效。")

    def save_as(self):
        path = filedialog.asksaveasfilename(
            title="另存語言檔", initialdir=self.lang_path.parent, initialfile=self.lang_path.name,
            defaultextension=".lang", filetypes=[("PL/SQL Developer 語言檔", "*.lang")],
        )
        if path and self.write_lang(Path(path)):
            self.lang_path = Path(path)
            self.path_var.set(path)
            self.update_status()
            messagebox.showinfo("完成", f"已加密存成：\n{path}")

    # ---------- 尋找 ----------

    def find_next(self):
        word = self.find_var.get()
        if not word:
            return
        self.text.tag_remove("hit", "1.0", "end")
        start = self.text.index("insert +1c")
        pos = self.text.search(word, start, stopindex="end", nocase=True) or self.text.search(word, "1.0", stopindex="end", nocase=True)
        if not pos:
            self.status_var.set(f"找不到「{word}」")
            return
        end = f"{pos}+{len(word)}c"
        self.text.tag_add("hit", pos, end)
        self.text.mark_set("insert", end)
        self.text.see(pos)
        self.update_status()

    # ---------- 關閉 ----------

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        return messagebox.askyesno(
            "尚未存回", "有修改還沒加密存回 .lang。\n（修改仍保留在暫存目錄的 .txt，下次開啟可以繼續）\n\n確定要繼續嗎？"
        )

    def on_close(self):
        if self.confirm_discard():
            self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 高解析度螢幕不模糊
    except Exception:
        pass
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:  # 支援把 .lang 拖到 exe 上開啟
        app.open_lang(Path(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
