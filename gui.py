from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import os
import time

from manager import DownloadManager, DownloadStatus
from utils import load_config, save_config, load_history, save_history
from datetime import datetime

DOWNLOADED_COLOR = QColor(180, 180, 180)
CONFIG_SAVE_PATH_KEY = 'save_path'


class CookieDialog(QDialog):
    def __init__(self, parent=None, saved_cookie=''):
        super().__init__(parent)
        self.setWindowTitle("夸克网盘 Cookie")
        self.setModal(True)
        self.resize(500, 200)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请粘贴夸克网盘的 Cookie（浏览器 F12 → Network → 复制 Cookie）:"))

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(saved_cookie)
        self.text_edit.setMaximumHeight(80)
        layout.addWidget(self.text_edit)

        info = QLabel("提示：打开 https://pan.quark.cn ，F12 → Network → 刷新 → 点击任意请求 → 复制 Request Headers 中的 Cookie")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        self.remember_cb = QCheckBox("记住 Cookie")
        self.remember_cb.setChecked(bool(saved_cookie))
        layout.addWidget(self.remember_cb)

        btn = QPushButton("确认")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    def get_cookie(self):
        return self.text_edit.toPlainText().strip()

    def should_remember(self):
        return self.remember_cb.isChecked()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("歌曲海批量下载工具")
        self.setMinimumSize(950, 700)

        cfg = load_config()
        self.save_path = cfg.get(CONFIG_SAVE_PATH_KEY,
                                 os.path.join(os.path.expanduser("~"), "Downloads", "歌曲海"))
        self.quark_cookie = cfg.get('quark_cookie', '')
        self.manager: DownloadManager | None = None
        self.search_results: list[dict] = []

        self._init_ui()
        self._check_cookie()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("请输入搜索关键词...")
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(self.search_btn)

        self.path_btn = QPushButton("保存路径")
        self.path_btn.clicked.connect(self._choose_path)
        search_layout.addWidget(self.path_btn)

        self.cookie_btn = QPushButton("Cookie")
        self.cookie_btn.clicked.connect(self._show_cookie_dialog)
        search_layout.addWidget(self.cookie_btn)

        layout.addLayout(search_layout)

        self.path_label = QLabel(f"保存路径: {self.save_path}")
        layout.addWidget(self.path_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "序号", "歌曲名", "歌手", "状态"])
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(2, 280)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 130)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.select_all_cb = QCheckBox("全选")
        self.select_all_cb.stateChanged.connect(self._toggle_select_all)
        btn_layout.addWidget(self.select_all_cb)

        self.selected_label = QLabel("已选: 0 首")
        btn_layout.addWidget(self.selected_label)

        self.queue_label = QLabel("")
        btn_layout.addWidget(self.queue_label)
        btn_layout.addStretch()

        self.download_btn = QPushButton("下载选中")
        self.download_btn.clicked.connect(self._download_selected)
        btn_layout.addWidget(self.download_btn)

        self.download_all_btn = QPushButton("下载全部")
        self.download_all_btn.clicked.connect(self._download_all)
        btn_layout.addWidget(self.download_all_btn)

        layout.addLayout(btn_layout)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("日志:"))
        self.clear_log_btn = QPushButton("清空")
        self.clear_log_btn.setFixedWidth(60)
        self.clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        log_header.addWidget(self.clear_log_btn)
        log_header.addStretch()
        layout.addLayout(log_header)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        layout.addWidget(self.log_output)

    def _do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            return
        self._log(f"搜索 \"{keyword}\"...")
        try:
            from gequhai import search_songs
            self.search_results = search_songs(keyword)
            self._populate_table()
            self._log(f"找到 {len(self.search_results)} 条结果")
        except Exception as e:
            self._log(f"搜索失败: {e}")

    def _populate_table(self):
        self.table.setRowCount(len(self.search_results))
        history = load_history()
        history_ids = {h['id'] for h in history}

        for i, song in enumerate(self.search_results):
            cb = QCheckBox()
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb.stateChanged.connect(lambda: self._update_selected_count())
            self.table.setCellWidget(i, 0, cb_widget)

            for col, val in [(1, str(i + 1)), (2, song['title']),
                             (3, song['artist']), (4, "待下载")]:
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if song['id'] in history_ids:
                    item.setForeground(DOWNLOADED_COLOR)
                    if col == 4:
                        item.setText("已下载")
                self.table.setItem(i, col, item)

        self._update_selected_count()

    def _update_selected_count(self):
        count = sum(
            1 for i in range(self.table.rowCount())
            if self.table.cellWidget(i, 0).findChild(QCheckBox).isChecked()
        )
        self.selected_label.setText(f"已选: {count} 首")

    def _toggle_select_all(self, state):
        checked = state == Qt.CheckState.Checked.value
        for i in range(self.table.rowCount()):
            cb = self.table.cellWidget(i, 0).findChild(QCheckBox)
            if cb:
                cb.setChecked(checked)

    def _download_selected(self):
        selected = []
        for i in range(self.table.rowCount()):
            if self.table.cellWidget(i, 0).findChild(QCheckBox).isChecked():
                selected.append(self.search_results[i])
        if not selected:
            self._log("请至少选择一首歌曲")
            return
        self._start_download(selected)

    def _download_all(self):
        if not self.search_results:
            self._log("请先搜索歌曲")
            return
        self._start_download(self.search_results)

    def _start_download(self, song_list):
        if not self.quark_cookie:
            self._log("请先设置夸克 Cookie")
            self._show_cookie_dialog()
            if not self.quark_cookie:
                return

        self.manager = DownloadManager(self.save_path, self.quark_cookie)
        self.manager.add_tasks(song_list)

        self.manager.progress_updated.connect(self._on_progress)
        self.manager.status_changed.connect(self._on_status_change)
        self.manager.log_message.connect(self._log)
        self.manager.queue_finished.connect(self._on_queue_finished)
        self.manager.task_finished.connect(self._on_task_finished)

        self.download_btn.setEnabled(False)
        self.download_all_btn.setEnabled(False)
        self.queue_label.setText(f"队列: {len(song_list)} 首")

        self._log(f"开始下载 {len(song_list)} 首歌曲...")
        self.manager.start()

    def _on_progress(self, idx: int, progress: float, speed: str):
        if idx < self.table.rowCount():
            pct = int(progress * 100)
            self.table.item(idx, 4).setText(f"下载中 {pct}%  {speed}")

    def _on_status_change(self, idx: int, status: str):
        if idx < self.table.rowCount():
            self.table.item(idx, 4).setText(status)

    def _on_queue_finished(self):
        self._log("全部下载完成")
        self.download_btn.setEnabled(True)
        self.download_all_btn.setEnabled(True)
        self.queue_label.setText("")

    def _on_task_finished(self, idx: int):
        if idx < len(self.search_results):
            song = self.search_results[idx]
            history = load_history()
            if not any(h['id'] == song['id'] for h in history):
                history.append({
                    'id': song['id'], 'title': song['title'],
                    'artist': song['artist'], 'time': time.time()
                })
                save_history(history)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{ts}] {msg}")
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _choose_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存路径", self.save_path)
        if path:
            self.save_path = path
            self.path_label.setText(f"保存路径: {self.save_path}")
            cfg = load_config()
            cfg[CONFIG_SAVE_PATH_KEY] = self.save_path
            save_config(cfg)

    def _show_cookie_dialog(self):
        saved = load_config().get('quark_cookie', '')
        dialog = CookieDialog(self, saved)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.quark_cookie = dialog.get_cookie()
            if dialog.should_remember() and self.quark_cookie:
                cfg = load_config()
                cfg['quark_cookie'] = self.quark_cookie
                save_config(cfg)
            elif not dialog.should_remember() and 'quark_cookie' in load_config():
                cfg = load_config()
                cfg.pop('quark_cookie', None)
                save_config(cfg)

    def _check_cookie(self):
        cfg = load_config()
        self.quark_cookie = cfg.get('quark_cookie', '')
        if not self.quark_cookie:
            self._show_cookie_dialog()
