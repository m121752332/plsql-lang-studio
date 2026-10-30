"""主視窗：選單列、工具列、檔案清單、對照表格、詳細區、狀態列。"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QAction, QFontMetrics, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QButtonGroup, QComboBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QSplitter, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import __version__, appconfig, elevate, eventlog
from ..core import batch, compare, i18n, langfile
from ..core.compare import STATUS_LABEL, Status
from ..core.langfile import LangFormatError
from ..core.workspace import ImportConflict, Workspace
from .batch_dialog import PreviewDialog, ReplaceDialog
from .compare_model import COL_FIELD, COL_KEY, COL_MASTER, COL_NO, COL_SLAVE, COL_SOURCE, COL_STATUS, \
    CompareFilter, CompareModel
from .detail_panel import DetailPanel
from .error_box import error_box
from .event_viewer import EventViewer
from .file_panel import FilePanel
from .fonts import FontManager
from .glossary_dialog import APPLY, GlossaryDialog
from .help_launcher import HelpLauncher, install_help
from .language import LanguageManager
from .settings_dialog import SettingsDialog
from .theme import ThemeManager
from .toast import ToastHost

FILTERS = [None, Status.DIFFERENT, Status.SIMPLIFIED, Status.UNTRANSLATED, Status.ONE_SIDED, Status.ERROR, Status.WARNING,
           Status.MODIFIED]  # None＝全部


class CompareTable(QTableView):
    """Enter 存入後自動跳到下一列；右鍵或 Ctrl+C 複製儲存格的完整內容。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def copy_cell(self, index) -> None:
        """複製完整文字；多行字串不能只複製表格上顯示的那一行。"""
        if index.isValid():
            QApplication.clipboard().setText(str(index.data(Qt.EditRole) or ""))

    def copy_row(self, index) -> None:
        """整列所有欄位以 Tab 分隔，每個欄位都是完整內容。"""
        if index.isValid():
            cells = (index.sibling(index.row(), c).data(Qt.EditRole) for c in range(self.model().columnCount()))
            QApplication.clipboard().setText("\t".join(str(v or "") for v in cells))

    def cell_menu(self, index) -> QMenu:
        menu = QMenu(self)
        header = self.model().headerData(index.column(), Qt.Horizontal)
        menu.addAction(self.tr("複製「{column}」").format(column=header), lambda: self.copy_cell(index))
        menu.addAction(self.tr("複製整列"), lambda: self.copy_row(index))
        return menu

    def _show_menu(self, pos) -> None:
        index = self.indexAt(pos)
        if index.isValid():
            self.cell_menu(index).exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_cell(self.currentIndex())
            return
        super().keyPressEvent(event)

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if hint == QAbstractItemDelegate.SubmitModelCache:
            cur = self.currentIndex()
            nxt = cur.sibling(cur.row() + 1, cur.column())
            if nxt.isValid():
                self.setCurrentIndex(nxt)


class MainWindow(QMainWindow):
    def __init__(self, workspace_root: Path | None, elevate_fn=elevate.elevated_copy, ask=None, info=None, toast=None,
                 theme_manager: ThemeManager | None = None, font_manager: FontManager | None = None,
                 help_launcher=None, language_manager: LanguageManager | None = None):
        super().__init__()
        self.theme = theme_manager or ThemeManager(QApplication.instance(), parent=self)
        self.fonts = font_manager or FontManager(QApplication.instance(), parent=self)
        self.language = language_manager or LanguageManager(QApplication.instance(), parent=self)
        self.help = help_launcher or HelpLauncher(self.theme, parent=self)
        self.elevate_fn = elevate_fn
        self.ask = ask or self._ask  # 測試時可以換掉對話框
        self.info = info or self._info
        self.toast_host = ToastHost(self)
        self.toast = toast or self.toast_host.show
        self.undo_stack = QUndoStack(self)
        self.model = CompareModel(self.undo_stack, self)
        self.proxy = CompareFilter(self)
        self.proxy.setSourceModel(self.model)
        self.master_name = self.slave_name = ""
        self._busy = 0  # 對話框或長操作進行中，poll_txt 先不要插手
        self.event_viewer = None
        self.ws: Workspace | None = None
        self.resize(1400, 860)
        self._build_ui()
        if workspace_root is not None:  # None：由呼叫端先顯示視窗再開啟，啟動時比較快看到畫面
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
        self.toolbar = tb = self.addToolBar("")
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
        for combo in (self.master_combo, self.slave_combo):  # 清單變動時重算寬度，長檔名才不會被截斷
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.master_combo.activated.connect(lambda: self.set_pair(self.master_combo.currentText(), self.slave_name))
        self.slave_combo.activated.connect(lambda: self.set_pair(self.master_name, self.slave_combo.currentText()))
        self.master_label, self.readonly_label, self.slave_label = QLabel(), QLabel(), QLabel()
        pick = QHBoxLayout()
        pick.addWidget(self.master_label)
        pick.addWidget(self.master_combo)
        pick.addWidget(self.readonly_label)
        pick.addSpacing(30)
        pick.addWidget(self.slave_label)
        pick.addWidget(self.slave_combo)
        pick.addStretch()

        self.filter_group = QButtonGroup(self)
        self.filter_buttons: dict = {}
        flt = QHBoxLayout()
        for status in FILTERS:
            b = QToolButton()
            b.setCheckable(True)
            self.filter_group.addButton(b)
            b.clicked.connect(lambda _=False, s=status: self.proxy.set_status(s))
            self.filter_buttons[status] = b
            flt.addWidget(b)
        self.filter_buttons[None].setChecked(True)
        flt.addSpacing(20)
        self.search = QLineEdit()
        self.scope = QComboBox()
        self.scope.setSizeAdjustPolicy(QComboBox.AdjustToContents)  # 切換介面語言後文字變長也不會被截斷
        for key in CompareFilter.SCOPES:
            self.scope.addItem("", key)
        self.search.textChanged.connect(self._apply_search)
        self.scope.currentIndexChanged.connect(self._apply_search)
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
        self.detail.applyRequested.connect(lambda i, t: self.apply_edits([(i, t)], self.tr("編輯字串")))
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
        self._set_texts()

    def _set_texts(self) -> None:
        """畫面上固定的文字；建立畫面時與切換介面語言時呼叫。"""
        texts = {
            "workspace": self.tr("切換工作區…"), "plsql_dir": self.tr("PL/SQL 語言目錄…"),
            "save": self.tr("💾 加密存檔"), "deploy": self.tr("🚀 部署到 PL/SQL Developer…"),
            "notepad": self.tr("📝 用記事本開啟副語系"), "open_ws": self.tr("開啟工作區資料夾"), "quit": self.tr("結束"),
            "find": self.tr("尋找"), "next_diff": self.tr("下一個不同"), "prev_diff": self.tr("上一個不同"),
            "replace": self.tr("🔍 尋找取代…"), "s2twp": self.tr("簡→繁（主語系 → 副語系）"),
            "glossary": self.tr("📖 用語對照表…"), "font_bigger": self.tr("放大字體"), "font_smaller": self.tr("縮小字體"),
            "font_reset": self.tr("還原預設字型"), "help": self.tr("使用說明"), "about": self.tr("關於 PLLangStudio"),
            "settings": self.tr("配置…"), "events": self.tr("事件檢視器…"),
        }
        for key, text in texts.items():
            self.act[key].setText(text)
        self._update_undo_texts()
        titles = (self.tr("檔案(&F)"), self.tr("編輯(&E)"), self.tr("配置(&S)"), self.tr("關於(&A)"))
        for menu, title in zip(self.menus, titles):
            menu.setTitle(title)
        self.toolbar.setWindowTitle(self.tr("主要"))
        self.master_label.setText(self.tr("主語系"))
        self.readonly_label.setText(self.tr("🔒 唯讀"))
        self.slave_label.setText(self.tr("副語系"))
        self.search.setPlaceholderText(self.tr("搜尋（Ctrl+F）"))
        for k, key in enumerate(CompareFilter.SCOPES):
            self.scope.setItemText(k, i18n.translate("CompareFilter", CompareFilter.SCOPE_LABEL[key]))

    def retranslate(self) -> None:
        """切換介面語言：固定文字、表格標題與狀態列都換成新的語言。"""
        self._set_texts()
        self.model.refresh_colors()
        self._update_counts()
        self._show_detail()
        if self.ws is not None:
            self._show_workspace_label()
            self.refresh_files()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    def _fit_row_height(self) -> None:
        """列高跟著字型走，字放大後才不會被切掉。"""
        self.table.verticalHeader().setDefaultSectionSize(max(22, QFontMetrics(QApplication.font()).height() + 8))

    def _build_actions(self) -> None:
        """選單與工具列共用同一組動作，快速鍵只註冊一次。"""
        def make(key, slot, shortcut=None):  # 文字在 _set_texts() 設定
            a = QAction(self)
            a.triggered.connect(lambda _=False: slot())
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            self.act[key] = a

        self.act: dict[str, QAction] = {}
        make("workspace", self.choose_workspace)
        make("plsql_dir", self.choose_plsql_dir)
        make("save", self.save, QKeySequence.Save)
        make("deploy", self.deploy)
        make("notepad", self.open_notepad)
        make("open_ws", lambda: os.startfile(self.ws.root))
        make("quit", self.close, "Alt+F4")
        # 不用 QUndoStack.createUndoAction：它的前置文字建立後就不能換，切換介面語言時會留在舊語言
        make("undo", self.undo_stack.undo, QKeySequence.Undo)
        make("redo", self.undo_stack.redo, "Ctrl+Y")
        for key, can_changed, text_changed in (("undo", self.undo_stack.canUndoChanged, self.undo_stack.undoTextChanged),
                                               ("redo", self.undo_stack.canRedoChanged, self.undo_stack.redoTextChanged)):
            self.act[key].setEnabled(False)
            can_changed.connect(self.act[key].setEnabled)
            text_changed.connect(self._update_undo_texts)
        make("find", lambda: self.search.setFocus(), QKeySequence.Find)
        make("next_diff", lambda: self.jump_different(1), "F3")
        make("prev_diff", lambda: self.jump_different(-1), "Shift+F3")
        make("replace", self.find_replace, "Ctrl+H")
        make("s2twp", self.convert_s2twp)
        make("glossary", self.edit_glossary)
        make("font_bigger", lambda: self.fonts.step(1))
        self.act["font_bigger"].setShortcuts([QKeySequence(QKeySequence.ZoomIn), QKeySequence("Ctrl+=")])  # 不按 Shift 也能放大
        make("font_smaller", lambda: self.fonts.step(-1), QKeySequence.ZoomOut)
        make("font_reset", self.fonts.reset, "Ctrl+0")
        for name in ("font_bigger", "font_smaller", "font_reset"):  # 不在選單上，快速鍵仍要有效
            self.addAction(self.act[name])
        make("help", self.show_help, "F1")
        make("about", self.show_about)
        make("settings", self.open_settings)
        make("events", self.show_events)

    def _update_undo_texts(self, *_args) -> None:
        for key, prefix, text in (("undo", self.tr("復原"), self.undo_stack.undoText()),
                                  ("redo", self.tr("重做"), self.undo_stack.redoText())):
            self.act[key].setText(f"{prefix} {text}" if text else prefix)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        self.menus = [bar.addMenu("") for _ in range(4)]  # 檔案、編輯、配置、關於；標題在 _set_texts() 設定
        file_menu, edit_menu, settings_menu, about_menu = self.menus
        for name in ("workspace", "plsql_dir", None, "save", "deploy", None, "notepad", "open_ws", None, "quit"):
            file_menu.addSeparator() if name is None else file_menu.addAction(self.act[name])
        for name in ("undo", "redo", None, "find", "next_diff", "prev_diff", "replace", None, "s2twp", "glossary"):
            edit_menu.addSeparator() if name is None else edit_menu.addAction(self.act[name])
        settings_menu.addAction(self.act["settings"])
        settings_menu.addAction(self.act["events"])
        about_menu.addAction(self.act["help"])
        about_menu.addAction(self.act["about"])

    def show_help(self) -> None:
        self.help.show(None)

    def open_settings(self) -> None:
        with self._working():
            dlg = SettingsDialog(self.theme, self.fonts, self.show_events, self, language=self.language)
            install_help(dlg, "theme-font", self.help.show)
            dlg.exec()
            dlg.deleteLater()  # 父物件是主視窗，不主動釋放會一直累積

    def show_events(self, event_id: int | None = None) -> None:
        """事件檢視器只開一個，再按一次就帶到前面並重新整理；指定事件編號時直接列出那一筆。"""
        if self.event_viewer is None:
            self.event_viewer = EventViewer(self.theme, self)
            install_help(self.event_viewer, "event-log", self.help.show)
        if event_id is not None:
            self.event_viewer.search.setText(f"#{event_id}")
        self.event_viewer.refresh()
        self.event_viewer.show()
        self.event_viewer.raise_()
        self.event_viewer.activateWindow()

    def show_about(self) -> None:
        QMessageBox.about(self, self.tr("關於 PLLangStudio"), self.tr(
            "<b>PLLangStudio {version}</b><br>PL/SQL Developer 語言編輯與比對器<br><br>"
            "工作區：{workspace}<br>PL/SQL 語言目錄：{plsql_dir}").format(
            version=__version__, workspace=self.ws.root, plsql_dir=self.ws.settings.plsql_lang_dir or self.tr("（未設定）")))

    def _ask(self, title: str, text: str, buttons=QMessageBox.Yes | QMessageBox.No,
             default=QMessageBox.No) -> QMessageBox.StandardButton:
        return QMessageBox.question(self, title, text, buttons, default)

    def _info(self, title: str, text: str, error: bool = False, event_id: int | None = None) -> None:
        if event_id is not None:
            error_box(self, title, text, event_id, self.show_events).exec()
            return
        (QMessageBox.warning if error else QMessageBox.information)(self, title, text)

    def _error(self, category: str, title: str, text: str, exc: BaseException | None = None) -> None:
        """錯誤一律記進事件紀錄，對話框附上事件編號，回報問題時用。"""
        eid = eventlog.error(category, f"{title}：{text}", exc)
        self.info(title, eventlog.with_event_id(text, eid), error=True, event_id=eid)

    # ---------- 工作區 ----------

    def open_workspace(self, root: Path) -> None:
        self.ws = Workspace(root)
        eventlog.info("工作區", f"開啟工作區：{self.ws.root}")
        appconfig.remember_workspace(self.ws.root)
        self._show_workspace_label()
        if not self.ws.installed_dir.is_dir():
            self.info(self.tr("找不到 PL/SQL Developer"), self.tr("找不到 PL/SQL Developer 的 Languages 目錄，請手動選擇。"))
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
                    self._error("匯入", self.tr("無法匯入"), f"{n}\n\n{e}", e)
        self.master_name = self.slave_name = ""
        self.set_pair(self.ws.settings.master, self.ws.settings.slave, confirm=False)

    def _show_workspace_label(self) -> None:
        self.ws_label.setText(self.tr(" 工作區：{path} ").format(path=self.ws.root))

    def choose_workspace(self) -> None:
        with self._working():
            if not self.confirm_discard():
                return
            d = QFileDialog.getExistingDirectory(self, self.tr("選擇工作區資料夾"), str(self.ws.root))
            if d:
                self.open_workspace(Path(d))

    def choose_plsql_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr("選擇 PL/SQL Developer 的 Languages 目錄"),
                                             self.ws.settings.plsql_lang_dir or "C:\\")
        if d:
            self.ws.settings.plsql_lang_dir = d
            self.ws.save_settings()
            eventlog.info("工作區", f"PL/SQL 語言目錄改為：{d}")
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
        self.st_deploy.setText(self.tr("已部署") if deployed else self.tr("工作區有尚未部署的修改"))

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
                if self.ask(self.tr("工作區已有同名檔"), self.tr(
                        "工作區的 {name} 跟 PL/SQL Developer 裡的不同。\n要覆蓋嗎？（舊檔會先備份）").format(name=name)) \
                        != QMessageBox.Yes:
                    return
                self.ws.import_lang(name, overwrite=True)
        except (OSError, ValueError) as e:  # LangFormatError 也是 ValueError
            self._error("匯入", self.tr("無法匯入"), f"{name}\n\n{e}", e)
            return
        eventlog.info("匯入", f"已匯入 {name}")
        if is_open:  # 正在看的檔案被換掉了，強制重新載入
            master, slave = self.master_name, self.slave_name
            self.master_name = self.slave_name = ""
            self.set_pair(master, slave, confirm=False)
        else:
            self.refresh_files()

    def remove_lang(self, name: str) -> None:
        with self._working():
            if name in (self.master_name, self.slave_name):
                text = (self.tr("{name} 目前是主語系，請先切換到別的檔案再移除。") if name == self.master_name
                        else self.tr("{name} 目前是副語系，請先切換到別的檔案再移除。"))
                self._error("移除", self.tr("無法移除"), text.format(name=name))
                return
            info = next((i for i in self.ws.list_workspace() if i.name == name), None)
            if info is None:
                return
            warn = "" if info.deployed else "\n\n" + self.tr("⚠ 這個檔案有尚未部署的修改，移除後只能從 backup 資料夾找回。")
            if self.ask(self.tr("從工作區移除"), self.tr(
                    "要把 {name} 從工作區移除嗎？\n會先備份到 backup 資料夾，PL/SQL Developer 裡的檔案不受影響。").format(name=name)
                    + warn) != QMessageBox.Yes:
                return
            try:
                self.ws.remove_lang(name)
            except OSError as e:
                self._error("移除", self.tr("無法移除"), f"{name}\n\n{e}", e)
            else:
                eventlog.info("移除", f"已從工作區移除 {name}")
            self.refresh_files()

    def _ensure_imported(self, name: str) -> bool:
        if (self.ws.lang_dir / name).exists():
            return True
        if not (self.ws.installed_dir / name).exists():
            self._error("匯入", self.tr("找不到檔案"), name)
            return False
        if self.ask(self.tr("尚未匯入"), self.tr("{name} 還沒匯入工作區，要現在匯入嗎？").format(name=name)) != QMessageBox.Yes:
            return False
        self.import_lang(name)
        return (self.ws.lang_dir / name).exists()

    # ---------- 主語系／副語系 ----------

    def confirm_discard(self) -> bool:
        if self.model.modified_count() == 0:
            return True
        return self.ask(self.tr("尚未存檔"), self.tr("有 {n} 個字串修改還沒存檔，確定要捨棄嗎？").format(
            n=self.model.modified_count())) == QMessageBox.Yes

    def current_row(self) -> int | None:
        idx = self.table.currentIndex()
        return self.proxy.mapToSource(idx).row() if idx.isValid() else None

    def set_pair(self, master: str, slave: str, confirm: bool = True) -> None:
        if not master or not slave:
            return
        if (master, slave) == (self.master_name, self.slave_name):
            return
        if master == slave:
            self.toast("warning", self.tr("不能選同一個檔案"), self.tr(
                "主語系和副語系都是 {name}。\n主語系是比對基準（唯讀），請選另一個檔案當副語系。").format(name=master))
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
            self._error("開啟", self.tr("無法開啟"), str(e), e)
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
                self._error("記事本", self.tr(".txt 無法讀取，已改用 .lang"), self.tr(
                    "{name} 對應的 .txt 讀取失敗：{error}\n\n原本的 .txt 已備份到：\n{backup}").format(
                    name=slave, error=e, backup=backup), e)
            else:
                self.model.load(m, new, exceptions, baseline=s)
                eventlog.info("記事本", f"{slave} 的 .txt 跟 .lang 不同，已載入 .txt 的內容")
                self.toast("info", self.tr("已載入記事本的修改"), self.tr(
                    "{name} 對應的 .txt 跟 .lang 不同，已載入 .txt 的內容。\n修改標示為 ✎，尚未存檔。").format(name=slave))
        else:
            self.model.load(m, s, exceptions)
            self.ws.sync_txt(slave, s)
        eventlog.info("開啟", f"主語系 {master}，副語系 {slave}，共 {self.model.rowCount():,} 列")
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
        self.st_pos.setText(self.tr("第 {row} / {total} 列").format(row=cur.row() + 1 if cur.isValid() else 0,
                                                                   total=self.proxy.rowCount()))

    def _update_counts(self) -> None:
        c = self.model.counts()
        for status, b in self.filter_buttons.items():
            label = self.tr("全部") if status is None else i18n.translate("Status", STATUS_LABEL[status])
            b.setText(f"{label} {c['ALL'] if status is None else c[status]:,}")
        self.st_unsaved.setText(self.tr("✎ {n} 個字串未存檔").format(n=self.model.modified_count()))
        self.st_issues.setText(self.tr("錯誤 {errors}／警告 {warnings}").format(errors=c[Status.ERROR],
                                                                            warnings=c[Status.WARNING]))

    def _apply_search(self) -> None:
        self.proxy.set_search(self.search.text(), self.scope.currentData())

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
            self._error("編輯", self.tr("無法套用修改"), str(e), e)
            return False

    # ---------- 存檔／部署 ----------

    def save(self) -> bool:
        with self._working():
            return self._save()

    def _save(self) -> bool:
        errors = self.model.has_errors()
        if errors:
            lines = [self.tr("第 {row} 列：{issues}").format(
                row=i + 1, issues="；".join(x.message for x in self.model.issues[i] if x.level == "error")) for i in errors[:10]]
            self._error("存檔", self.tr("有錯誤，不能存檔"), "\n".join(lines) + ("\n…" if len(errors) > 10 else ""))
            self.proxy.set_status(Status.ERROR)
            self.filter_buttons[Status.ERROR].setChecked(True)
            self.select_row(errors[0])
            return False
        warnings = sum(Status.WARNING in s and Status.MODIFIED in s for s in self.model.status)
        if warnings and self.ask(self.tr("有警告"), self.tr(
                "修改過的字串中有 {n} 個有警告（可在「警告」篩選查看）。\n仍要存檔嗎？").format(n=warnings)) != QMessageBox.Yes:
            return False
        count = self.model.modified_count()
        try:
            self.ws.save(self.slave_name, self.model.slave)
        except OSError as e:
            self._error("存檔", self.tr("存檔失敗"), self.tr("{name} 沒有存成功：{error}").format(name=self.slave_name, error=e), e)
            return False
        self.model.mark_saved()
        eventlog.success("存檔", f"已加密存檔到工作區：{self.slave_name}（{count} 個字串修改）")
        self.refresh_files()
        self.toast("success", self.tr("已存檔"), self.tr("已加密存檔到工作區：{name}").format(name=self.slave_name))
        return True

    def deploy(self) -> None:
        with self._working():
            self._deploy()

    def _deploy(self) -> None:
        if self.model.modified_count() and (self.ask(self.tr("尚未存檔"), self.tr("要先存檔再部署嗎？")) != QMessageBox.Yes
                                            or not self._save()):
            return
        target = self.ws.installed_dir / self.slave_name
        n, unreadable = None, False
        if target.exists():
            try:
                n = compare.count_differences(self.ws.load(self.slave_name), langfile.load(target))
            except (OSError, ValueError):
                unreadable = True
        if n is not None:
            text = self.tr("{name} 跟 PL/SQL Developer 裡的版本有 {n} 筆不同。").format(name=self.slave_name, n=n)
        elif unreadable:
            text = self.tr("PL/SQL Developer 裡的 {name} 讀不出來（可能已損壞），無法比較差異。").format(name=self.slave_name)
        else:
            text = self.tr("PL/SQL Developer 裡還沒有 {name}。").format(name=self.slave_name)
        if self.ask(self.tr("部署到 PL/SQL Developer"),
                    text + "\n\n" + self.tr("要部署到：\n{target}\n嗎？（舊檔會先備份）").format(target=target)) != QMessageBox.Yes:
            return
        try:
            res = self.ws.deploy(self.slave_name, self.elevate_fn)
        except (OSError, ValueError) as e:
            self._error("部署", self.tr("部署失敗"), self.tr("{name} 沒有部署成功：{error}").format(name=self.slave_name, error=e), e)
            return
        if res.ok:
            eventlog.success("部署", f"{self.slave_name}：{res.message}")
            self.toast("success", self.tr("已部署"), res.message)
        else:
            self._error("部署", self.tr("部署結果"), res.message)
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
            self._error("記事本", self.tr(".txt 編碼錯誤"), self.tr("請在記事本用「另存新檔」，編碼選 UTF-8 後再存一次。"))
            return
        except LangFormatError as e:
            self.ws.acknowledge_txt(name)
            self._error("記事本", self.tr(".txt 格式錯誤，沒有載入"), f"{e}\n\n" + self.tr("請修正後再存一次。"), e)
            return
        if self.model.modified_count() and self.ask(self.tr("兩邊都有修改"), self.tr(
                "表格和記事本都有尚未存檔的修改。\n\n是 → 改用記事本的內容（表格的修改會被捨棄）\n否 → 保留表格的修改（記事本的修改會被覆蓋）")) \
                != QMessageBox.Yes:
            self.ws.sync_txt(name, self.model.slave)
            return
        cur = self.current_row()
        key = self.model.rows[cur].key if cur is not None else None
        self.model.load(self.model.master, new, self.model.exceptions, baseline=self.ws.load(name))
        self.select_row(self.model.row_of_key(key) if key else 0)
        eventlog.info("記事本", f"已從記事本重新載入 {name}")
        self.toast("info", self.tr("已從記事本重新載入"), self.tr("{name} 的修改標示為 ✎，尚未存檔。").format(name=name))

    # ---------- 批次 ----------

    def _apply_changes(self, title: str, changes: list[batch.Change]) -> None:
        if not changes:
            self.toast("info", title, self.tr("沒有需要修改的字串。"))
            return
        with self._working():
            dlg = PreviewDialog(title, changes, self)
            install_help(dlg, "batch", self.help.show)
            if dlg.exec():
                edits = [(self.model.row_of_ref(c.row.ref), c.after) for c in dlg.checked()]
                applied = [e for e in edits if e[0] is not None]
                if self.apply_edits(applied, title):
                    eventlog.info("批次修改", f"{title}：套用 {len(applied)} 個字串")

    def find_replace(self) -> None:
        with self._working():
            dlg = ReplaceDialog(self)
            install_help(dlg, "replace", self.help.show)
            if dlg.exec() and dlg.find.text():
                try:
                    changes = batch.preview_replace(self.model.rows, self.model.master, self.model.slave,
                                                    dlg.find.text(), dlg.replace.text(), dlg.regex.isChecked(),
                                                    dlg.case.isChecked())
                except Exception as e:  # 規則運算式寫錯
                    self._error("批次修改", self.tr("尋找取代"), self.tr("規則運算式有誤：{error}").format(error=e), e)
                    return
                self._apply_changes(self.tr("尋找取代"), changes)

    def convert_s2twp(self) -> None:
        selected = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        rows = [self.model.rows[i] for i in sorted(selected)] if len(selected) > 1 else self.model.rows
        self._apply_changes(self.tr("簡轉繁（主語系 → 副語系）"), batch.preview_s2twp(rows, self.model.master, self.model.slave))

    def edit_glossary(self) -> None:
        with self._working():
            dlg = GlossaryDialog(self.ws.load_glossary(), self)
            install_help(dlg, "glossary", self.help.show)
            result = dlg.exec()
            if result in (1, APPLY):
                g = dlg.glossary()
                self.ws.save_glossary(g)
                eventlog.info("用語對照表", f"用語對照表已儲存，共 {len(g.rules)} 條規則")
                self.model.exceptions = g.simplified_exceptions
                if result == APPLY:
                    self._apply_changes(self.tr("套用用語表"), batch.preview_rules(
                        self.model.rows, self.model.master, self.model.slave, g.rules))

    # ---------- 關閉 ----------

    def closeEvent(self, event) -> None:
        if self.confirm_discard():
            self.help.close()
            event.accept()
        else:
            event.ignore()
