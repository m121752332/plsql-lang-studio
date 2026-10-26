"""主視窗：選單列、工具列、檔案清單、對照表格、詳細區、狀態列。"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFontMetrics, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QButtonGroup, QComboBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QSplitter, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import __version__, appconfig, elevate
from ..core import batch, compare, langfile
from ..core.compare import STATUS_LABEL, Status
from ..core.langfile import LangFormatError
from ..core.workspace import ImportConflict, Workspace
from .batch_dialog import PreviewDialog, ReplaceDialog
from .compare_model import COL_FIELD, COL_KEY, COL_MASTER, COL_NO, COL_SLAVE, COL_SOURCE, COL_STATUS, \
    CompareFilter, CompareModel
from .detail_panel import DetailPanel
from .file_panel import FilePanel
from .font_dialog import FontDialog
from .fonts import FontManager
from .glossary_dialog import APPLY, GlossaryDialog
from .theme import MODE_LABEL, ThemeManager

FILTERS = [(None, "全部"), (Status.DIFFERENT, None), (Status.SIMPLIFIED, None), (Status.UNTRANSLATED, None),
           (Status.ONE_SIDED, None), (Status.ERROR, None), (Status.WARNING, None), (Status.MODIFIED, None)]


class CompareTable(QTableView):
    """Enter 存入後自動跳到下一列。"""

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if hint == QAbstractItemDelegate.SubmitModelCache:
            cur = self.currentIndex()
            nxt = cur.sibling(cur.row() + 1, cur.column())
            if nxt.isValid():
                self.setCurrentIndex(nxt)


class MainWindow(QMainWindow):
    def __init__(self, workspace_root: Path, elevate_fn=elevate.elevated_copy, ask=None, info=None,
                 theme_manager: ThemeManager | None = None, font_manager: FontManager | None = None):
        super().__init__()
        self.theme = theme_manager or ThemeManager(QApplication.instance(), parent=self)
        self.fonts = font_manager or FontManager(QApplication.instance(), parent=self)
        self.elevate_fn = elevate_fn
        self.ask = ask or self._ask  # 測試時可以換掉對話框
        self.info = info or self._info
        self.undo_stack = QUndoStack(self)
        self.model = CompareModel(self.undo_stack, self)
        self.proxy = CompareFilter(self)
        self.proxy.setSourceModel(self.model)
        self.master_name = self.slave_name = ""
        self._busy = 0  # 對話框或長操作進行中，poll_txt 先不要插手
        self.resize(1400, 860)
        self._build_ui()
        self.open_workspace(workspace_root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_txt)
        self.timer.start(1000)

    @contextmanager
    def _working(self):
        self._busy += 1
        try:
            yield
        finally:
            self._busy -= 1

    # ---------- 畫面 ----------

    def _build_ui(self) -> None:
        self._build_actions()
        self._build_menus()
        tb = self.addToolBar("主要")
        tb.setMovable(False)
        self.ws_label = QLabel()
        tb.addWidget(self.ws_label)
        tb.addAction(self.act["workspace"])
        tb.addSeparator()
        for name in ("save", "deploy", "notepad", None, "undo", "redo", None, "replace", "s2twp", "glossary"):
            tb.addSeparator() if name is None else tb.addAction(self.act[name])

        self.files = FilePanel()
        self.files.setMaster.connect(lambda n: self.set_pair(n, self.slave_name))
        self.files.setSlave.connect(lambda n: self.set_pair(self.master_name, n))
        self.files.importRequested.connect(self.import_lang)
        self.files.openTxt.connect(lambda n: self.open_notepad(n))
        self.files.openFolder.connect(lambda p: subprocess.Popen(["explorer", "/select,", p]))
        self.files.removeRequested.connect(self.remove_lang)

        self.master_combo, self.slave_combo = QComboBox(), QComboBox()
        self.master_combo.activated.connect(lambda: self.set_pair(self.master_combo.currentText(), self.slave_name))
        self.slave_combo.activated.connect(lambda: self.set_pair(self.master_name, self.slave_combo.currentText()))
        pick = QHBoxLayout()
        pick.addWidget(QLabel("主語系"))
        pick.addWidget(self.master_combo)
        pick.addWidget(QLabel("🔒 唯讀"))
        pick.addSpacing(30)
        pick.addWidget(QLabel("副語系"))
        pick.addWidget(self.slave_combo)
        pick.addStretch()

        self.filter_group = QButtonGroup(self)
        self.filter_buttons: dict = {}
        flt = QHBoxLayout()
        for status, label in FILTERS:
            b = QToolButton()
            b.setCheckable(True)
            b.setProperty("label", label or STATUS_LABEL[status])
            self.filter_group.addButton(b)
            b.clicked.connect(lambda _=False, s=status: self.proxy.set_status(s))
            self.filter_buttons[status] = b
            flt.addWidget(b)
        self.filter_buttons[None].setChecked(True)
        flt.addSpacing(20)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋（Ctrl+F）")
        self.scope = QComboBox()
        self.scope.addItems(list(CompareFilter.SCOPES))
        self.search.textChanged.connect(self._apply_search)
        self.scope.currentTextChanged.connect(self._apply_search)
        flt.addWidget(self.search, 1)
        flt.addWidget(self.scope)

        self.table = CompareTable()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().hide()
        self._fit_row_height()
        self.fonts.changed.connect(self._fit_row_height)
        for col, w in ((COL_NO, 50), (COL_STATUS, 50), (COL_KEY, 260), (COL_FIELD, 70),
                       (COL_SOURCE, 260), (COL_MASTER, 260), (COL_SLAVE, 260)):
            self.table.setColumnWidth(col, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self._show_detail())

        self.detail = DetailPanel()
        self.detail.applyRequested.connect(lambda i, t: self.apply_edits([(i, t)], "編輯字串"))
        self.undo_stack.indexChanged.connect(lambda *_: self._show_detail())
        self.model.countsChanged.connect(self._update_counts)
        self.theme.changed.connect(self.model.refresh_colors)
        self.theme.changed.connect(self.detail.refresh_colors)

        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(pick)
        lay.addLayout(flt)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(self.table)
        vsplit.addWidget(self.detail)
        vsplit.setStretchFactor(0, 4)
        lay.addWidget(vsplit)
        hsplit = QSplitter()
        hsplit.addWidget(self.files)
        hsplit.addWidget(center)
        hsplit.setSizes([300, 1100])
        self.setCentralWidget(hsplit)

        self.st_unsaved, self.st_issues, self.st_pos, self.st_deploy = QLabel(), QLabel(), QLabel(), QLabel()
        for w in (self.st_unsaved, self.st_issues, self.st_pos, self.st_deploy):
            self.statusBar().addWidget(w)
            self.statusBar().addWidget(QLabel("｜"))

    def _fit_row_height(self) -> None:
        """列高跟著字型走，字放大後才不會被切掉。"""
        self.table.verticalHeader().setDefaultSectionSize(max(22, QFontMetrics(QApplication.font()).height() + 8))

    def _build_actions(self) -> None:
        """選單與工具列共用同一組動作，快速鍵只註冊一次。"""
        def make(key, text, slot, shortcut=None):
            a = QAction(text, self)
            a.triggered.connect(lambda _=False: slot())
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            self.act[key] = a

        self.act: dict[str, QAction] = {}
        make("workspace", "切換工作區…", self.choose_workspace)
        make("plsql_dir", "PL/SQL 語言目錄…", self.choose_plsql_dir)
        make("save", "💾 加密存檔", self.save, QKeySequence.Save)
        make("deploy", "🚀 部署到 PL/SQL Developer…", self.deploy)
        make("notepad", "📝 用記事本開啟副語系", self.open_notepad)
        make("open_ws", "開啟工作區資料夾", lambda: os.startfile(self.ws.root))
        make("quit", "結束", self.close, "Alt+F4")
        undo = self.undo_stack.createUndoAction(self, "復原")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.undo_stack.createRedoAction(self, "重做")
        redo.setShortcut(QKeySequence("Ctrl+Y"))
        self.act["undo"], self.act["redo"] = undo, redo
        make("find", "尋找", lambda: self.search.setFocus(), QKeySequence.Find)
        make("next_diff", "下一個不同", lambda: self.jump_different(1), "F3")
        make("prev_diff", "上一個不同", lambda: self.jump_different(-1), "Shift+F3")
        make("replace", "🔍 尋找取代…", self.find_replace, "Ctrl+H")
        make("s2twp", "簡→繁（主語系 → 副語系）", self.convert_s2twp)
        make("glossary", "📖 用語對照表…", self.edit_glossary)
        make("font", "字型與大小…", lambda: FontDialog(self.fonts, self).exec())
        make("font_bigger", "放大字體", lambda: self.fonts.step(1))
        self.act["font_bigger"].setShortcuts([QKeySequence(QKeySequence.ZoomIn), QKeySequence("Ctrl+=")])  # 不按 Shift 也能放大
        make("font_smaller", "縮小字體", lambda: self.fonts.step(-1), QKeySequence.ZoomOut)
        make("font_reset", "還原預設字型", self.fonts.reset, "Ctrl+0")
        make("help", "使用說明", self.show_help, "F1")
        make("about", "關於 PLLangStudio", self.show_about)
        self.theme_group = QActionGroup(self)
        for mode, label in MODE_LABEL.items():
            a = QAction(label, self, checkable=True)
            a.setChecked(self.theme.mode == mode)
            a.triggered.connect(lambda _=False, m=mode: self.theme.set_mode(m))
            self.theme_group.addAction(a)
            self.act[f"theme_{mode}"] = a

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("檔案(&F)")
        for name in ("workspace", "plsql_dir", None, "save", "deploy", None, "notepad", "open_ws", None, "quit"):
            file_menu.addSeparator() if name is None else file_menu.addAction(self.act[name])
        edit_menu = bar.addMenu("編輯(&E)")
        for name in ("undo", "redo", None, "find", "next_diff", "prev_diff", "replace", None, "s2twp", "glossary", None):
            edit_menu.addSeparator() if name is None else edit_menu.addAction(self.act[name])
        theme_menu = edit_menu.addMenu("主題")
        for mode in MODE_LABEL:
            theme_menu.addAction(self.act[f"theme_{mode}"])
        font_menu = edit_menu.addMenu("字型")
        for name in ("font", None, "font_bigger", "font_smaller", "font_reset"):
            font_menu.addSeparator() if name is None else font_menu.addAction(self.act[name])
        about_menu = bar.addMenu("關於(&A)")
        about_menu.addAction(self.act["help"])
        about_menu.addAction(self.act["about"])

    def show_help(self) -> None:
        self.info("使用說明", (
            "1. 主語系（唯讀）是比對的基準，副語系是要修改的語言檔；可以用上方下拉選單或左側清單切換。\n"
            "2. 在表格的副語系欄雙擊或按 F2 修改；多行字串在下方詳細區修改後按「套用」。\n"
            "3. 批次修改：編輯 ▸ 尋找取代、簡→繁、用語對照表，套用前都會先預覽。\n"
            "4. Ctrl+S 加密存檔（只寫工作區），確認無誤後 檔案 ▸ 部署到 PL/SQL Developer，重新啟動 PL/SQL Developer 生效。\n"
            "5. 也可以用記事本修改副語系的 .txt，存檔後會自動載入；只能改翻譯，不能新增或刪除筆。\n\n"
            "快速鍵：Ctrl+S 存檔、Ctrl+Z／Ctrl+Y 復原重做、Ctrl+F 尋找、Ctrl+H 尋找取代、F3／Shift+F3 下一個／上一個不同。"))

    def show_about(self) -> None:
        QMessageBox.about(self, "關於 PLLangStudio", (
            f"<b>PLLangStudio {__version__}</b><br>PL/SQL Developer 語言編輯與比對器<br><br>"
            f"工作區：{self.ws.root}<br>PL/SQL 語言目錄：{self.ws.settings.plsql_lang_dir or '（未設定）'}"))

    def _ask(self, title: str, text: str, buttons=QMessageBox.Yes | QMessageBox.No,
             default=QMessageBox.No) -> QMessageBox.StandardButton:
        return QMessageBox.question(self, title, text, buttons, default)

    def _info(self, title: str, text: str, error: bool = False) -> None:
        (QMessageBox.warning if error else QMessageBox.information)(self, title, text)

    # ---------- 工作區 ----------

    def open_workspace(self, root: Path) -> None:
        self.ws = Workspace(root)
        appconfig.remember_workspace(self.ws.root)
        self.ws_label.setText(f" 工作區：{self.ws.root} ")
        if not self.ws.installed_dir.is_dir():
            self.info("找不到 PL/SQL Developer", "找不到 PL/SQL Developer 的 Languages 目錄，請手動選擇。")
            self.choose_plsql_dir()
        names = {i.name for i in self.ws.list_workspace()}
        s = self.ws.settings
        if s.master == s.slave:  # 設定檔被改成同一個檔案：副語系改用另一個
            others = sorted((names | {i.name for i in self.ws.list_installed()}) - {s.master})
            if others:
                s.slave = others[0]
        for n in (self.ws.settings.master, self.ws.settings.slave):  # 第一次使用：自動匯入預設的兩個檔案
            if n not in names and (self.ws.installed_dir / n).exists():
                try:
                    self.ws.import_lang(n)
                except (OSError, ValueError) as e:
                    self.info("無法匯入", f"{n}\n\n{e}", error=True)
        self.master_name = self.slave_name = ""
        self.set_pair(self.ws.settings.master, self.ws.settings.slave, confirm=False)

    def choose_workspace(self) -> None:
        with self._working():
            if not self.confirm_discard():
                return
            d = QFileDialog.getExistingDirectory(self, "選擇工作區資料夾", str(self.ws.root))
            if d:
                self.open_workspace(Path(d))

    def choose_plsql_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "選擇 PL/SQL Developer 的 Languages 目錄",
                                             self.ws.settings.plsql_lang_dir or "C:\\")
        if d:
            self.ws.settings.plsql_lang_dir = d
            self.ws.save_settings()
            self.refresh_files()

    def refresh_files(self) -> None:
        names = [i.name for i in self.ws.list_workspace()]
        for combo, cur, other in ((self.master_combo, self.master_name, self.slave_name),
                                  (self.slave_combo, self.slave_name, self.master_name)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if other in names:  # 已經是另一邊的檔案不能再選
                combo.model().item(names.index(other)).setEnabled(False)
            combo.setCurrentText(cur)
            combo.blockSignals(False)
        self.files.refresh(self.ws.list_installed(), self.ws.list_workspace(), self.master_name, self.slave_name)
        deployed = next((i.deployed for i in self.ws.list_workspace() if i.name == self.slave_name), None)
        self.st_deploy.setText("已部署" if deployed else "工作區有尚未部署的修改")

    def import_lang(self, name: str) -> None:
        with self._working():
            self._import_lang(name)

    def _import_lang(self, name: str) -> None:
        is_open = name in (self.master_name, self.slave_name)
        if is_open and not self.confirm_discard():
            return
        try:
            try:
                self.ws.import_lang(name)
            except ImportConflict:
                if self.ask("工作區已有同名檔", f"工作區的 {name} 跟 PL/SQL Developer 裡的不同。\n要覆蓋嗎？（舊檔會先備份）") \
                        != QMessageBox.Yes:
                    return
                self.ws.import_lang(name, overwrite=True)
        except (OSError, ValueError) as e:  # LangFormatError 也是 ValueError
            self.info("無法匯入", f"{name}\n\n{e}", error=True)
            return
        if is_open:  # 正在看的檔案被換掉了，強制重新載入
            master, slave = self.master_name, self.slave_name
            self.master_name = self.slave_name = ""
            self.set_pair(master, slave, confirm=False)
        else:
            self.refresh_files()

    def remove_lang(self, name: str) -> None:
        with self._working():
            if name in (self.master_name, self.slave_name):
                self.info("無法移除", f"{name} 目前是{'主語系' if name == self.master_name else '副語系'}，"
                          "請先切換到別的檔案再移除。", error=True)
                return
            info = next((i for i in self.ws.list_workspace() if i.name == name), None)
            if info is None:
                return
            warn = "" if info.deployed else "\n\n⚠ 這個檔案有尚未部署的修改，移除後只能從 backup 資料夾找回。"
            if self.ask("從工作區移除", f"要把 {name} 從工作區移除嗎？\n"
                        f"會先備份到 backup 資料夾，PL/SQL Developer 裡的檔案不受影響。{warn}") != QMessageBox.Yes:
                return
            try:
                self.ws.remove_lang(name)
            except OSError as e:
                self.info("無法移除", f"{name}\n\n{e}", error=True)
            self.refresh_files()

    def _ensure_imported(self, name: str) -> bool:
        if (self.ws.lang_dir / name).exists():
            return True
        if not (self.ws.installed_dir / name).exists():
            self.info("找不到檔案", name, error=True)
            return False
        if self.ask("尚未匯入", f"{name} 還沒匯入工作區，要現在匯入嗎？") != QMessageBox.Yes:
            return False
        self.import_lang(name)
        return (self.ws.lang_dir / name).exists()

    # ---------- 主語系／副語系 ----------

    def confirm_discard(self) -> bool:
        if self.model.modified_count() == 0:
            return True
        return self.ask("尚未存檔", f"有 {self.model.modified_count()} 個字串修改還沒存檔，確定要捨棄嗎？") == QMessageBox.Yes

    def current_row(self) -> int | None:
        idx = self.table.currentIndex()
        return self.proxy.mapToSource(idx).row() if idx.isValid() else None

    def set_pair(self, master: str, slave: str, confirm: bool = True) -> None:
        if not master or not slave:
            return
        if (master, slave) == (self.master_name, self.slave_name):
            return
        if master == slave:
            self.info("不能選同一個檔案", f"主語系和副語系都是 {master}。\n主語系是比對基準（唯讀），請選另一個檔案當副語系。")
            self.refresh_files()
            return
        if confirm and not self.confirm_discard():
            self.refresh_files()
            return
        if not (self._ensure_imported(master) and self._ensure_imported(slave)):
            self.refresh_files()
            return
        cur = self.current_row()
        key = self.model.rows[cur].key if cur is not None else None
        try:
            m, s = self.ws.load(master), self.ws.load(slave)
        except (LangFormatError, ValueError) as e:
            self.info("無法開啟", str(e), error=True)
            return
        self.master_name, self.slave_name = master, slave
        self.ws.settings.master, self.ws.settings.slave = master, slave
        self.ws.save_settings()
        exceptions = self.ws.load_glossary().simplified_exceptions
        if self.ws.txt_differs(slave, s):  # ADR-0008 規則 2：程式關閉時在記事本改的內容不能被蓋掉
            try:
                new = self.ws.load_txt(slave)
            except (UnicodeDecodeError, LangFormatError) as e:
                backup = self.ws.backup_txt(slave)
                self.model.load(m, s, exceptions)
                self.ws.sync_txt(slave, s)
                self.info(".txt 無法讀取，已改用 .lang", f"{slave} 對應的 .txt 讀取失敗：{e}\n\n"
                          f"原本的 .txt 已備份到：\n{backup}", error=True)
            else:
                self.model.load(m, new, exceptions, baseline=s)
                self.info("已載入記事本的修改", f"{slave} 對應的 .txt 跟 .lang 不同，已載入 .txt 的內容。\n"
                          "修改標示為 ✎，尚未存檔。")
        else:
            self.model.load(m, s, exceptions)
            self.ws.sync_txt(slave, s)
        self.setWindowTitle(f"PLLangStudio — {master} ↔ {slave}")
        self.refresh_files()
        self.select_row(self.model.row_of_key(key) if key else 0)

    def select_row(self, source_row: int | None) -> None:
        if source_row is None:
            return
        idx = self.proxy.mapFromSource(self.model.index(source_row, COL_NO))
        if idx.isValid():
            self.table.selectionModel().setCurrentIndex(
                idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            self.table.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def _show_detail(self) -> None:
        self.detail.show_row(self.model, self.current_row())
        cur = self.table.currentIndex()
        self.st_pos.setText(f"第 {cur.row() + 1 if cur.isValid() else 0} / {self.proxy.rowCount()} 列")

    def _update_counts(self) -> None:
        c = self.model.counts()
        for status, b in self.filter_buttons.items():
            b.setText(f"{b.property('label')} {c['ALL'] if status is None else c[status]:,}")
        self.st_unsaved.setText(f"✎ {self.model.modified_count()} 個字串未存檔")
        self.st_issues.setText(f"錯誤 {c[Status.ERROR]}／警告 {c[Status.WARNING]}")

    def _apply_search(self) -> None:
        self.proxy.set_search(self.search.text(), self.scope.currentText())

    def jump_different(self, step: int) -> None:
        start = self.table.currentIndex().row()
        n = self.proxy.rowCount()
        r = start + step
        while 0 <= r < n:
            if Status.DIFFERENT in self.model.status[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]:
                self.select_row(self.proxy.mapToSource(self.proxy.index(r, 0)).row())
                return
            r += step

    # ---------- 編輯 ----------

    def apply_edits(self, edits: list[tuple[int, str]], label: str) -> bool:
        try:
            self.model.request_edit(edits, label)
            return True
        except ValueError as e:
            self.info("無法套用修改", str(e), error=True)
            return False

    # ---------- 存檔／部署 ----------

    def save(self) -> bool:
        with self._working():
            return self._save()

    def _save(self) -> bool:
        errors = self.model.has_errors()
        if errors:
            lines = [f"第 {i + 1} 列：{'；'.join(x.message for x in self.model.issues[i] if x.level == 'error')}"
                     for i in errors[:10]]
            self.info("有錯誤，不能存檔", "\n".join(lines) + ("\n…" if len(errors) > 10 else ""), error=True)
            self.proxy.set_status(Status.ERROR)
            self.filter_buttons[Status.ERROR].setChecked(True)
            self.select_row(errors[0])
            return False
        warnings = sum(Status.WARNING in s and Status.MODIFIED in s for s in self.model.status)
        if warnings and self.ask("有警告", f"修改過的字串中有 {warnings} 個有警告（可在「警告」篩選查看）。\n仍要存檔嗎？") \
                != QMessageBox.Yes:
            return False
        try:
            self.ws.save(self.slave_name, self.model.slave)
        except OSError as e:
            self.info("存檔失敗", f"{self.slave_name} 沒有存成功：{e}", error=True)
            return False
        self.model.mark_saved()
        self.refresh_files()
        self.statusBar().showMessage(f"已加密存檔到工作區：{self.slave_name}", 5000)
        return True

    def deploy(self) -> None:
        with self._working():
            self._deploy()

    def _deploy(self) -> None:
        if self.model.modified_count() and (self.ask("尚未存檔", "要先存檔再部署嗎？") != QMessageBox.Yes or not self._save()):
            return
        target = self.ws.installed_dir / self.slave_name
        n, unreadable = None, False
        if target.exists():
            try:
                n = compare.count_differences(self.ws.load(self.slave_name), langfile.load(target))
            except (OSError, ValueError):
                unreadable = True
        if n is not None:
            text = f"{self.slave_name} 跟 PL/SQL Developer 裡的版本有 {n} 筆不同。"
        elif unreadable:
            text = f"PL/SQL Developer 裡的 {self.slave_name} 讀不出來（可能已損壞），無法比較差異。"
        else:
            text = f"PL/SQL Developer 裡還沒有 {self.slave_name}。"
        if self.ask("部署到 PL/SQL Developer", f"{text}\n\n要部署到：\n{target}\n嗎？（舊檔會先備份）") != QMessageBox.Yes:
            return
        try:
            res = self.ws.deploy(self.slave_name, self.elevate_fn)
        except (OSError, ValueError) as e:
            self.info("部署失敗", f"{self.slave_name} 沒有部署成功：{e}", error=True)
            return
        self.info("部署結果", res.message, error=not res.ok)
        self.refresh_files()

    # ---------- 記事本 ----------

    def open_notepad(self, name: str | None = None) -> None:
        name = name or self.slave_name
        if name == self.slave_name and self.model.modified_count():
            self.ws.sync_txt(name, self.model.slave)  # 讓記事本看到表格裡還沒存檔的修改
        subprocess.Popen(["notepad.exe", str(self.ws.txt_path(name))])

    def poll_txt(self) -> None:
        if self._busy:
            return
        name = self.slave_name
        if not name or not self.ws.txt_changed(name):
            return
        with self._working():
            self._reload_txt(name)

    def _reload_txt(self, name: str) -> None:
        try:
            new = self.ws.load_txt(name)
        except UnicodeDecodeError:
            self.ws.acknowledge_txt(name)
            self.info(".txt 編碼錯誤", "請在記事本用「另存新檔」，編碼選 UTF-8 後再存一次。", error=True)
            return
        except LangFormatError as e:
            self.ws.acknowledge_txt(name)
            self.info(".txt 格式錯誤，沒有載入", f"{e}\n\n請修正後再存一次。", error=True)
            return
        if self.model.modified_count() and self.ask(
                "兩邊都有修改", "表格和記事本都有尚未存檔的修改。\n\n是 → 改用記事本的內容（表格的修改會被捨棄）\n否 → 保留表格的修改（記事本的修改會被覆蓋）") \
                != QMessageBox.Yes:
            self.ws.sync_txt(name, self.model.slave)
            return
        cur = self.current_row()
        key = self.model.rows[cur].key if cur is not None else None
        self.model.load(self.model.master, new, self.model.exceptions, baseline=self.ws.load(name))
        self.select_row(self.model.row_of_key(key) if key else 0)
        self.statusBar().showMessage("已從記事本重新載入", 5000)

    # ---------- 批次 ----------

    def _apply_changes(self, title: str, changes: list[batch.Change]) -> None:
        if not changes:
            self.info(title, "沒有需要修改的字串。")
            return
        with self._working():
            dlg = PreviewDialog(title, changes, self)
            if dlg.exec():
                edits = [(self.model.row_of_ref(c.row.ref), c.after) for c in dlg.checked()]
                self.apply_edits([e for e in edits if e[0] is not None], title)

    def find_replace(self) -> None:
        with self._working():
            dlg = ReplaceDialog(self)
            if dlg.exec() and dlg.find.text():
                try:
                    changes = batch.preview_replace(self.model.rows, self.model.master, self.model.slave,
                                                    dlg.find.text(), dlg.replace.text(), dlg.regex.isChecked(),
                                                    dlg.case.isChecked())
                except Exception as e:  # 規則運算式寫錯
                    self.info("尋找取代", f"規則運算式有誤：{e}", error=True)
                    return
                self._apply_changes("尋找取代", changes)

    def convert_s2twp(self) -> None:
        selected = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        rows = [self.model.rows[i] for i in sorted(selected)] if len(selected) > 1 else self.model.rows
        self._apply_changes("簡轉繁（主語系 → 副語系）", batch.preview_s2twp(rows, self.model.master, self.model.slave))

    def edit_glossary(self) -> None:
        with self._working():
            dlg = GlossaryDialog(self.ws.load_glossary(), self)
            result = dlg.exec()
            if result in (1, APPLY):
                g = dlg.glossary()
                self.ws.save_glossary(g)
                self.model.exceptions = g.simplified_exceptions
                if result == APPLY:
                    self._apply_changes("套用用語表", batch.preview_rules(
                        self.model.rows, self.model.master, self.model.slave, g.rules))

    # ---------- 關閉 ----------

    def closeEvent(self, event) -> None:
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()
