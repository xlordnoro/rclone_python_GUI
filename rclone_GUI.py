import sys
import subprocess
import json
import posixpath
import os
import platform
import shutil

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QLabel, QHBoxLayout, QComboBox,
    QTreeWidget, QTreeWidgetItem, QProgressBar,
    QLineEdit, QMenu, QMessageBox, QInputDialog
)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt, QUrl, QMimeData
from PyQt6.QtGui import QDrag, QIcon
from PyQt6 import QtGui

def get_app_dir():
    # --------------------------------------------------
    # PyInstaller (onefile/onedir)
    # --------------------------------------------------
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    # --------------------------------------------------
    # AppImage
    # --------------------------------------------------
    if "APPIMAGE" in os.environ:
        # Path to the AppImage file itself
        return os.path.dirname(os.environ["APPIMAGE"])

    # --------------------------------------------------
    # Normal script
    # --------------------------------------------------
    return os.path.dirname(os.path.abspath(__file__))

def get_writable_dir():
    """
    Where we should store cache/config files.
    Always writable.
    """

    # AppImage → use where the AppImage is located
    if "APPIMAGE" in os.environ:
        return os.path.dirname(os.environ["APPIMAGE"])

    # Otherwise → same as app dir
    return get_app_dir()

APP_DIR = get_app_dir()
DATA_DIR = get_writable_dir()

def get_rclone_path():
    exe = "rclone.exe" if os.name == "nt" else "rclone"

    # 1. PyInstaller bundle
    bundled = os.path.join(getattr(sys, "_MEIPASS", ""), exe)
    if getattr(sys, "frozen", False) and os.path.exists(bundled):
        return bundled

    # 2. portable folder next to app
    local = os.path.join(APP_DIR, exe)
    if os.path.exists(local):
        return local

    # 3. AppImage embedded location
    appimage_bin = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "bin", exe
    )
    appimage_bin = os.path.abspath(appimage_bin)
    if os.path.exists(appimage_bin):
        return appimage_bin

    # 4. system PATH
    system = shutil.which("rclone")
    if system:
        return system

    raise FileNotFoundError(
        f"rclone not found.\nChecked:\n"
        f"  - {bundled}\n"
        f"  - {local}\n"
        f"  - {appimage_bin}\n"
        f"  - system PATH"
    )

RCLONE_PATH = get_rclone_path()

# ---------------------------
# WORKER
# ---------------------------
class RcloneWorker(QThread):
    output_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(object)

    def __init__(self, source, destination, transfers="4"):
        super().__init__()
        self.source = source
        self.destination = destination
        self.transfers = transfers
        self.process = None

    def run(self):
        cmd = [
            RCLONE_PATH, "copy",
            self.source,
            self.destination,
            "--progress",
            "--stats=1s",
            "--transfers", str(self.transfers)
        ]

        # 🔥 DEBUG: show exact command
        pretty_cmd = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        self.output_signal.emit(f"[DEBUG] {pretty_cmd}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in self.process.stdout:
            self.output_signal.emit(line.strip())

            # parse: Transferred: 13 / 14, 93%
            if "Transferred:" in line and "%" in line:
                try:
                    percent_part = line.split(",")[-1].strip()
                    percent = int(percent_part.replace("%", ""))
                    self.progress_signal.emit(percent)
                except:
                    pass

        self.process.wait()
        self.finished_signal.emit(self)

    def cancel(self):
        if self.process:
            self.process.terminate()

class RcloneRenameWorker(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object)

    def __init__(self, source, destination):
        super().__init__()
        self.source = source
        self.destination = destination
        self.process = None

    def run(self):
        self.process = subprocess.Popen(
            [
                RCLONE_PATH, "moveto",
                self.source,
                self.destination,
                "--progress",
                "--stats=1s"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in self.process.stdout:
            self.output_signal.emit("[rename] " + line.strip())

        self.process.wait()
        self.finished_signal.emit(self)

    def cancel(self):
        if self.process:
            self.process.terminate()


# ---------------------------
# LOCAL TREE
# ---------------------------
class LocalTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setHeaderLabel("Local")
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            return

        menu = QMenu(self)

        new_folder_action = menu.addAction("New Folder")
        delete_action = menu.addAction("Delete")
        rename_action = menu.addAction("Rename")

        action = menu.exec(event.globalPos())

        if action == rename_action:
            self.parent().rename_local_item(item)

        elif action == new_folder_action:
            self.setCurrentItem(item)
            self.parent().create_local_folder()

        elif action == delete_action:
            items = self.selectedItems()

            if item not in items:
                items.append(item)

            self.parent().delete_local_items(items)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        urls = []

        for item in items:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                urls.append(QUrl.fromLocalFile(path))

        if not urls:
            return

        mime = QMimeData()
        mime.setUrls(urls)

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supportedActions)


# ---------------------------
# REMOTE TREE
# ---------------------------
class RemoteTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setHeaderLabel("Remote")
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

        self._highlight = None

        self.setStyleSheet("""
            QTreeWidget::item:hover {
                background-color: #2b6cb0;
                color: white;
            }
            QTreeWidget::item:selected {
                background-color: #1a4f8b;
                color: white;
            }
        """)

    # ---------------------------
    # CONTEXT MENU (MULTI-DELETE SUPPORT)
    # ---------------------------
    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            return

        menu = QMenu(self)

        new_folder_action = menu.addAction("New Folder")
        delete_action = menu.addAction("Delete")
        rename_action = menu.addAction("Rename")

        action = menu.exec(event.globalPos())

        if action == rename_action:
            self.parent().rename_remote_item(item)

        elif action == new_folder_action:
            # Ensure the clicked item is selected so folder goes there
            self.setCurrentItem(item)
            self.parent().create_remote_folder()

        elif action == delete_action:
            items = self.selectedItems()

            if item not in items:
                items.append(item)

            self.parent().delete_remote_items(items)

    def highlight(self, item):
        if self._highlight:
            self._highlight.setBackground(0, Qt.GlobalColor.transparent)

        self._highlight = item

        if item:
            item.setBackground(0, QtGui.QColor("#2b6cb0"))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.highlight(self.itemAt(event.position().toPoint()))
        event.acceptProposedAction()

    def dropEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if not item:
            return

        self.highlight(None)

        sources = list(set(u.toLocalFile() for u in event.mimeData().urls()))
        self.parent().handle_drag_upload(sources, item)

        event.acceptProposedAction()

class RcloneDeleteWorker(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.processes = []

    def _run_cmd(self, cmd, prefix):
        self.output_signal.emit(f"{prefix} Running: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        self.processes.append(process)

        for line in process.stdout:
            line = line.strip()
            if line:
                self.output_signal.emit(f"{prefix} {line}")

        return_code = process.wait()
        return return_code

    def run(self):
        for path in self.paths:

            # Try file delete first
            cmd = [RCLONE_PATH, "delete", path]
            code = self._run_cmd(cmd, "[delete]")

            # If it fails, assume directory → purge
            if code != 0:
                cmd = [RCLONE_PATH, "purge", path]
                self._run_cmd(cmd, "[delete][dir]")

        self.finished_signal.emit(self)

    def cancel(self):
        for p in self.processes:
            try:
                p.terminate()
            except:
                pass

# ---------------------------
# MAIN APP
# ---------------------------
class RcloneGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("rclone GUI")
        self.setGeometry(200, 200, 1200, 700)

        self.settings = QSettings("rclone_gui", "state")

        self.pending_uploads = set()
        self.active_jobs = set()
        self.workers = set()

        self.upload_queue = []
        self.upload_running = False

        self.total_uploads = 0
        self.completed_uploads = 0
        
        # Dark Mode Toggle
        self.dark_mode_btn = QPushButton("Dark Mode")
        self.dark_mode_btn.setCheckable(True)
        self.dark_mode_btn.clicked.connect(self.toggle_dark_mode)

        # CACHE
        self.remote_cache = {}
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.cache_file = os.path.join(DATA_DIR, "rclone_gui_cache.json")

        self.remote_cache = {}
        self._load_cache_from_disk()

        layout = QVBoxLayout()

        path_layout = QHBoxLayout()

        self.local_up_btn = QPushButton("⬆")
        self.remote_up_btn = QPushButton("⬆")

        self.local_path_bar = QLineEdit()
        self.remote_path_bar = QLineEdit()

        self.local_path_bar.returnPressed.connect(self.reload_local_root)
        self.remote_path_bar.returnPressed.connect(self.load_remote_from_bar)
        self.local_up_btn.clicked.connect(self.go_local_up)
        self.remote_up_btn.clicked.connect(self.go_remote_up)

        path_layout.addWidget(self.local_up_btn)
        path_layout.addWidget(self.local_path_bar)

        path_layout.addWidget(self.remote_up_btn)
        path_layout.addWidget(self.remote_path_bar)

        self.remote_dropdown = QComboBox()
        self.remote_dropdown.currentIndexChanged.connect(self.load_remote_root)

        pane = QHBoxLayout()

        self.local_tree = LocalTree()
        self.local_tree.setParent(self)

        self.remote_tree = RemoteTree()
        self.remote_tree.setParent(self)

        pane.addWidget(self.local_tree)
        pane.addWidget(self.remote_tree)

        self.upload_btn = QPushButton("Upload")
        self.cancel_btn = QPushButton("Cancel")
        self.refresh_btn = QPushButton("Refresh")
        self.mkdir_btn = QPushButton("New Folder")

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.transfers_dropdown = QComboBox()
        self.transfers_dropdown.addItems(["1", "2", "4", "8", "16"])
        self.transfers_dropdown.setCurrentText(
            self.settings.value("rclone_transfers", "4")
        )
        self.transfers_dropdown.currentTextChanged.connect(self.save_transfers_setting)

        layout.addWidget(QLabel("Remote"))
        layout.addWidget(self.remote_dropdown)
        layout.addLayout(path_layout)
        layout.addLayout(pane)

        btns = QHBoxLayout()
        btns.addWidget(self.upload_btn)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.mkdir_btn)
        btns.addWidget(self.dark_mode_btn)
        btns.addWidget(QLabel("Transfers:"))
        btns.addWidget(self.transfers_dropdown)

        layout.addLayout(btns)
        layout.addWidget(self.progress)
        layout.addWidget(self.log)

        self.setLayout(layout)
        #self.apply_dark_theme()

        self.local_tree.itemExpanded.connect(self.expand_local)
        self.remote_tree.itemExpanded.connect(self.load_remote_folder)

        self.upload_btn.clicked.connect(self.start_upload)
        self.cancel_btn.clicked.connect(self.cancel_upload)
        self.refresh_btn.clicked.connect(self.refresh_all)
        self.mkdir_btn.clicked.connect(self.create_remote_folder)

        dark_mode = self.settings.value("dark_mode", False, type=bool)

        self.dark_mode_btn.setChecked(dark_mode)

        if dark_mode:
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

        self.load_remotes()

        last = self.settings.value("last_local", "/")
        self.load_local_files(last)

        self.load_remote_root()

    # Go up functions for local & remote view
    def go_local_up(self):
        path = self.local_path_bar.text().strip()
        if not path:
            return

        parent = os.path.dirname(path.rstrip(os.sep))

        # Handle root edge case (Windows/Linux)
        if not parent:
            parent = path

        self.load_local_files(parent)

    def go_remote_up(self):
        path = self.remote_path_bar.text().strip()
        if not path:
            return

        # Split "remote:rest/of/path"
        if ":" not in path:
            return

        remote, _, subpath = path.partition(":")

        # No subpath = already at root
        if not subpath:
            return

        subpath = subpath.rstrip("/")

        parent = posixpath.dirname(subpath)

        # Rebuild path
        if parent:
            new_path = f"{remote}:{parent}"
        else:
            new_path = f"{remote}:"

        self.remote_tree.clear()
        self.remote_path_bar.setText(new_path)
        self._load_remote_children(self.remote_tree.invisibleRootItem(), new_path)

    # Dark & Light Mode palettes
    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #2f2f2f;
                color: #dddddd;
                font-size: 13px;
            }

            QLineEdit, QTextEdit, QComboBox, QTreeWidget {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #4a4a4a;
            }

            /* Tree headers (Local / Remote) */
            QHeaderView::section {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 4px;
                border: 1px solid #4a4a4a;
            }

            QPushButton {
                background-color: #444444;
                border: 1px solid #5a5a5a;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: #555555;
            }

            QPushButton:pressed {
                background-color: #2a82da;
            }

            QTreeWidget::item:selected {
                background-color: #2a82da;
            }

            QTreeWidget::item:hover {
                background-color: #505050;
            }

            QProgressBar {
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
                text-align: center;
            }

            QProgressBar::chunk {
                background-color: #2a82da;
            }
            QMenu {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
            }

            QMenu::item {
                padding: 6px 20px;
            }

            QMenu::item:selected {
                background-color: #2b6cb0;
                color: white;
            }

            QScrollBar:vertical {
                background-color: #2f2f2f;
                width: 12px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background-color: #5a5a5a;
                min-height: 20px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #777777;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                background: none;
                height: 0px;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: #2f2f2f;
                height: 12px;
                margin: 0px;
            }

            QScrollBar::handle:horizontal {
                background-color: #5a5a5a;
                min-width: 20px;
                border-radius: 5px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #777777;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                background: none;
                width: 0px;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

    def apply_light_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                color: #222222;
                font-size: 13px;
            }

            QLineEdit, QTextEdit, QComboBox, QTreeWidget {
                background-color: #ffffff;
                color: #222222;
                border: 1px solid #cfcfcf;
            }

            /* Tree headers (Local / Remote) */
            QHeaderView::section {
                background-color: #e6e6e6;
                color: #222222;
                padding: 4px;
                border: 1px solid #cfcfcf;
            }

            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #bdbdbd;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: #d0d0d0;
            }

            QPushButton:pressed {
                background-color: #a8c7ff;
            }

            QTreeWidget::item:selected {
                background-color: #a8c7ff;
            }

            QTreeWidget::item:hover {
                background-color: #e8e8e8;
            }

            QProgressBar {
                background-color: #ffffff;
                border: 1px solid #cfcfcf;
                text-align: center;
            }

            QProgressBar::chunk {
                background-color: #4a90e2;
            }

            QMenu {
                background-color: #ffffff;
                color: black;
                border: 1px solid #4a4a4a;
            }

            QMenu::item {
                padding: 6px 20px;
            }

            QMenu::item:selected {
                background-color: #2b6cb0;
                color: black;
            }
        """)

    # Theme switcher
    def toggle_dark_mode(self):
        enabled = self.dark_mode_btn.isChecked()

        if enabled:
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

        self.settings.setValue("dark_mode", enabled)

    # Transfers dropdown settings
    def save_transfers_setting(self, value):
        self.settings.setValue("rclone_transfers", value)

    def _is_valid_remote_path(self, path):
        try:
            r = subprocess.run(
                [RCLONE_PATH, "lsjson", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if r.returncode != 0:
                self.log.append(f"[rclone error] {r.stderr.strip() or r.stdout.strip()}")
                return False

            return True

        except Exception as e:
            self.log.append(f"[exception] {e}")
            return False

    # ---------------------------
    # CACHE
    # ---------------------------
    def _load_cache_from_disk(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    self.remote_cache = json.load(f)
        except:
            self.remote_cache = {}

    def _save_cache_to_disk(self):
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.remote_cache, f)
        except Exception as e:
            print("[cache] failed:", e)

    def _invalidate_cache_paths(self, paths):
        for p in paths:
            # remove exact path cache
            if p in self.remote_cache:
                del self.remote_cache[p]

            # also remove parent listing (important!)
            parent = posixpath.dirname(p)
            if parent in self.remote_cache:
                del self.remote_cache[parent]

    def _remove_items_from_tree(self, items):
        for item in items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                index = self.remote_tree.indexOfTopLevelItem(item)
                self.remote_tree.takeTopLevelItem(index)

    # ---------------------------
    # REMOTES
    # ---------------------------
    def load_remotes(self):
        r = subprocess.run(
            [RCLONE_PATH, "listremotes"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.remote_dropdown.addItems([x for x in r.stdout.splitlines() if x])

    # ---------------------------
    # LOCAL
    # ---------------------------
    def load_local_files(self, root):
        self.local_tree.clear()
        self.local_path_bar.setText(root)

        item = QTreeWidgetItem(self.local_tree, [root])
        item.setData(0, Qt.ItemDataRole.UserRole, root)
        item.addChild(QTreeWidgetItem(["..."]))

    def reload_local_root(self):
        self.load_local_files(self.local_path_bar.text())

    def expand_local(self, item):
        if item.childCount() != 1:
            return

        item.takeChildren()

        path = item.data(0, Qt.ItemDataRole.UserRole)
        self.local_path_bar.setText(path)

        self.settings.setValue("last_local", path)

        self._load_local_children(item, path)

    def _load_local_children(self, parent, path):
        try:
            for name in os.listdir(path):
                full = os.path.join(path, name)

                child = QTreeWidgetItem(parent, [name])
                child.setData(0, Qt.ItemDataRole.UserRole, full)

                if os.path.isdir(full):
                    child.addChild(QTreeWidgetItem(["..."]))
        except Exception as e:
            self.log.append(f"[local error] {e}")

    # ---------------------------
    # REMOTE
    # ---------------------------
    def load_remote_root(self):
        remote = self.remote_dropdown.currentText()
        if not remote:
            return

        if not remote.endswith(":"):
            remote += ":"

        self.remote_tree.clear()
        self.remote_path_bar.setText(remote)

        self._load_remote_children(self.remote_tree.invisibleRootItem(), remote)

    def load_remote_from_bar(self):
        path = self.remote_path_bar.text().strip()
        if not path:
            return

        if not self._is_valid_remote_path(path):
            self.log.append(f"[blocked] invalid remote path: {path}")
            QMessageBox.warning(self, "Invalid Path", f"Remote path not found:\n{path}")
            return

        self.remote_tree.clear()
        self._load_remote_children(self.remote_tree.invisibleRootItem(), path)

    def _get_remote_listing(self, path):
        if path in self.remote_cache:
            return self.remote_cache[path]

        r = subprocess.run(
            [RCLONE_PATH, "lsjson", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if r.returncode != 0:
            return None

        data = json.loads(r.stdout or "[]")
        self.remote_cache[path] = data
        self._save_cache_to_disk()
        return data

    def load_remote_folder(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return

        # HARD GUARD (fast path)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if is_dir is not True:
            return

        # Use cache first
        cached = self.remote_cache.get(path)

        if cached is None:
            # Only verify with rclone if NOT cached
            test = subprocess.run(
                [RCLONE_PATH, "lsjson", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if test.returncode != 0:
                # Not actually a directory → fix UI state
                self.log.append(f"[fix] not a directory: {path}")

                item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
                item.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator
                )
                item.takeChildren()
                return

            # Cache the successful result
            try:
                cached = json.loads(test.stdout or "[]")
                self.remote_cache[path] = cached
                self._save_cache_to_disk()
            except:
                cached = []

        # already expanded → do nothing
        if item.childCount() != 1:
            return

        # remove placeholder
        item.takeChildren()

        # Only validate if we don't find the files/folders in the cache
        # (you can remove this entirely if confident in lsjson)
        if path not in self.remote_cache:
            if not self._is_valid_remote_path(path):
                self.log.append(f"[blocked] invalid folder: {path}")
                return

        self.remote_path_bar.setText(path)

        # Pass cached data directly to avoid another lookup
        self._load_remote_children(item, path)

    def _load_remote_children(self, parent, path):
        if not self._is_valid_remote_path(path):
            self.log.append(f"[blocked] invalid path: {path}")
            return

        data = self._get_remote_listing(path)
        if data is None:
            return

        for entry in data:
            name = entry["Name"]

            if name == ".bzEmpty":
                continue

            is_dir = entry.get("IsDir")

            # fallback: if IsDir is missing, infer from Size (dirs usually have no Size)
            if is_dir is None:
                is_dir = entry.get("Size") in (None, 0) and entry.get("MimeType") == "inode/directory"

            child_path = posixpath.join(path, name)

            child = QTreeWidgetItem(parent, [name])

            child.setData(0, Qt.ItemDataRole.UserRole, child_path)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)

            if is_dir:
                # ONLY directories get lazy-loading placeholder
                child.addChild(QTreeWidgetItem(["..."]))
                child.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )
            else:
                # FORCE files to NEVER show expand arrow
                child.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator
                )

    def is_dir_item(self, item):
        return item.data(0, Qt.ItemDataRole.UserRole + 1) is True

    def _update_expand_flags(self, item):
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1) is True

        item.setChildIndicatorPolicy(
            QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            if is_dir
            else QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator
        )

    # ---------------------------
    # MULTI UPLOAD (UNCHANGED)
    # ---------------------------
    def handle_drag_upload(self, sources, remote_item):
        base = remote_item.data(0, Qt.ItemDataRole.UserRole)
        if not base:
            return

        for src in sources:
            if os.path.isfile(src):
                # 🔥 file → copy INTO directory (not as a directory)
                dest = base
            else:
                # folder → keep name
                dest = posixpath.join(base, os.path.basename(src))

            self.upload_queue.append((src, dest))

        # If nothing running, initialize FULL-QUEUE progress
        if not self.upload_running:
            self.total_uploads = len(self.upload_queue)
            self.completed_uploads = 0

            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("0%")

            self.process_next_upload()

    def process_next_upload(self):
        if not self.upload_queue:
            self.upload_running = False
            self.reset_progress()

            print("✅ Upload queue complete.")  # <-- ADD THIS
            self.log.append("Upload queue complete.")  # optional GUI log

            return

        self.upload_running = True

        src, dest = self.upload_queue.pop(0)

        worker = RcloneWorker(src, dest, transfers=self.transfers_dropdown.currentText())
        worker.dest = dest
        worker.output_signal.connect(self.log.append)
        worker.progress_signal.connect(self.update_progress)
        #worker.progress_signal.connect(self.progress.setValue)
        worker.finished_signal.connect(lambda w=worker: self.on_upload_finished(w))

        self.workers.add(worker)
        worker.start()

    def on_upload_finished(self, worker):
        self.completed_uploads += 1

        # show percentage
        if self.total_uploads > 0:
            percent = int((self.completed_uploads / self.total_uploads) * 100)
            self.progress.setValue(percent)
            self.progress.setFormat(f"{percent}%")

        # get destination path from worker
        dest = getattr(worker, "dest", None)

        if dest:
            # invalidate only affected paths
            self._invalidate_cache_paths([
                dest,
                posixpath.dirname(dest)
            ])

        self._save_cache_to_disk()

        self.refresh_remote()
        self.process_next_upload()

    def start_upload(self):
        src = self.local_tree.currentItem()
        dst = self.remote_tree.currentItem()

        if not src or not dst:
            return

        self.handle_drag_upload(
            [src.data(0, Qt.ItemDataRole.UserRole)],
            dst
        )

    def cancel_upload(self):
        for w in list(self.workers):
            w.cancel()

        self.upload_queue.clear()
        self.upload_running = False

    def update_progress(self, percent):
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}%")

    def reset_progress(self):
        self.upload_running = False
        self.upload_queue.clear()
        self.workers.clear()

        self.total_uploads = 0
        self.completed_uploads = 0

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")

    # ---------------------------
    # REFRESH
    # ---------------------------
    def refresh_remote(self):
        path = self.remote_path_bar.text().strip()
        item = self._find_item(self.remote_tree.invisibleRootItem(), path)

        if item:
            expanded = item.isExpanded()

            item.takeChildren()
            self._load_remote_children(item, path)

            item.setExpanded(expanded)
        else:
            self.load_remote_root()

    def refresh_local(self):
        path = self.local_path_bar.text().strip()
        if not path:
            return

        item = self._find_item(self.local_tree.invisibleRootItem(), path)

        if item:
            item.takeChildren()
            self._load_local_children(item, path)
        else:
            self.local_tree.clear()
            self.load_local_files(path)

    def _find_item(self, parent, path):
        for i in range(parent.childCount()):
            item = parent.child(i)

            if item.data(0, Qt.ItemDataRole.UserRole) == path:
                return item

            found = self._find_item(item, path)
            if found:
                return found

        return None

    # Local
    def rename_local_item(self, item):
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path:
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Rename remote item")
        dialog.setLabelText("New name:")
        dialog.setTextValue(os.path.basename(old_path))

        dialog.setMinimumWidth(700)
        dialog.resize(700, 160)

        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            line_edit.setMinimumWidth(650)

        ok = dialog.exec()
        new_name = dialog.textValue()

        if not ok or not new_name:
            return

        new_path = os.path.join(os.path.dirname(old_path), new_name)

        try:
            os.rename(old_path, new_path)
            parent_path = os.path.dirname(old_path)
            parent_item = self._find_item(self.local_tree.invisibleRootItem(), parent_path)

            if parent_item:
                parent_item.takeChildren()
                self._load_local_children(parent_item, parent_path)

        except Exception as e:
            QMessageBox.critical(self, "Rename failed", str(e))

    def delete_local_items(self, items):
        paths = [
            i.data(0, Qt.ItemDataRole.UserRole)
            for i in items if i.data(0, Qt.ItemDataRole.UserRole)
        ]

        if not paths:
            return

        preview = "\n".join(paths[:10])
        if len(paths) > 10:
            preview += f"\n... (+{len(paths) - 10} more)"

        confirm = QMessageBox.question(
            self,
            "Delete",
            f"Delete these files?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                self.log.append(f"[local delete error] {e}")

        for item in items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)

    def create_local_folder(self):
        item = self.local_tree.currentItem()

        base_path = None
        if item:
            base_path = item.data(0, Qt.ItemDataRole.UserRole)

        if not base_path:
            base_path = self.local_path_bar.text().strip()

        if not base_path:
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Create Folder")
        dialog.setLabelText(f"Create in:\n{base_path}\n\nFolder name:")

        # Make it wide
        dialog.setMinimumWidth(500)
        dialog.resize(500, 160)

        # Make input field wider too
        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            line_edit.setMinimumWidth(500)

        ok = dialog.exec()
        name = dialog.textValue()

        if not ok or not name:
            return

        new_path = os.path.join(base_path, name)

        try:
            os.makedirs(new_path, exist_ok=True)
            parent_item = self.local_tree.currentItem()

            if parent_item:
                base_path = parent_item.data(0, Qt.ItemDataRole.UserRole)
                parent_item.takeChildren()
                self._load_local_children(parent_item, base_path)

        except Exception as e:
            QMessageBox.critical(self, "Create folder failed", str(e))

    def refresh_all(self):
        self.refresh_local()
        self.refresh_remote()

    # ---------------------------
    # RENAME
    # ---------------------------
    def rename_remote_item(self, item):
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path:
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Rename remote item")
        dialog.setLabelText("New name:")
        dialog.setTextValue(os.path.basename(old_path))

        dialog.setMinimumWidth(700)
        dialog.resize(700, 160)

        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            line_edit.setMinimumWidth(650)

        ok = dialog.exec()
        new_name = dialog.textValue()

        if not ok or not new_name:
            return

        parent = posixpath.dirname(old_path)
        new_path = posixpath.join(parent, new_name)

        # ---- START ASYNC RENAME ----
        worker = RcloneRenameWorker(old_path, new_path)

        worker.output_signal.connect(self.log.append)

        def on_done(w):
            self.remote_cache.clear()
            self._save_cache_to_disk()
            self.refresh_remote()
            self.log.append("[rename] completed")

        worker.finished_signal.connect(on_done)

        self.workers.add(worker)
        worker.start()

    # ---------------------------
    # DELETE (SINGLE + MULTI)
    # ---------------------------
    def delete_remote_items(self, items):
        if not items:
            return

        paths = [
            i.data(0, Qt.ItemDataRole.UserRole)
            for i in items
            if i.data(0, Qt.ItemDataRole.UserRole)
        ]

        if not paths:
            return

        preview = "\n".join(paths[:10])
        if len(paths) > 10:
            preview += f"\n... (+{len(paths) - 10} more)"

        confirm = QMessageBox.question(
            self,
            "Delete the following",
            f"Are you sure you want to delete these files?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        worker = RcloneDeleteWorker(paths)

        worker.output_signal.connect(self.log.append)

        def on_done(w):
            self.log.append("✅ Delete complete")

            # remove from cache ONLY what changed
            self._invalidate_cache_paths(paths)
            self._save_cache_to_disk()

            # remove from UI instantly
            self._remove_items_from_tree(items)

        worker.finished_signal.connect(on_done)

        self.workers.add(worker)
        worker.start()

    # Create folder button
    def create_remote_folder(self):
        item = self.remote_tree.currentItem()

        # fallback to current path bar if nothing selected
        base_path = None
        if item:
            base_path = item.data(0, Qt.ItemDataRole.UserRole)

        if not base_path:
            base_path = self.remote_path_bar.text().strip()

        if not base_path:
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Create Folder")
        dialog.setLabelText(f"Create in:\n{base_path}\n\nFolder name:")

        # Make it wide
        dialog.setMinimumWidth(500)
        dialog.resize(500, 160)

        # Make input field wider too
        line_edit = dialog.findChild(QLineEdit)
        if line_edit:
            line_edit.setMinimumWidth(500)

        ok = dialog.exec()
        name = dialog.textValue()

        if not ok or not name:
            return

        new_path = posixpath.join(base_path, name)

        self.log.append(f"[mkdir] Creating: {new_path}")

        r = subprocess.run(
            [RCLONE_PATH, "mkdir", new_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        marker = posixpath.join(new_path, ".bzEmpty")

        r = subprocess.run(
            [RCLONE_PATH, "touch", marker],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if r.returncode != 0:
            QMessageBox.critical(self, "Create folder failed", r.stderr or r.stdout)
            return

        self.log.append(f"[mkdir] Created: {new_path}")

        # refresh view
        self.remote_cache.clear()
        self._save_cache_to_disk()
        self.refresh_remote()


# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Global app icon (fixes most "default Qt icon" issues)
    app.setWindowIcon(QIcon("icon.png"))

    w = RcloneGUI()

    # Window icon (ensures main window always uses it)
    w.setWindowIcon(QIcon("icon.png"))

    app.aboutToQuit.connect(w._save_cache_to_disk)

    w.show()
    sys.exit(app.exec())
