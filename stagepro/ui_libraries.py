from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QMessageBox,
)

from .libraries.model import (
    LibrarySource,
    LibrariesConfig,
    LibrarySyncState,
    load_libraries_config,
    load_state,
    save_libraries_config,
    save_state,
)
from .libraries import git_client
from .libraries.sync_service import sync_source
from .paths import libraries_sources_dir, libraries_published_dir


class SyncWorker(QObject):
    finished = Signal(str, bool, str)
    progress = Signal(str, str)

    def __init__(self, source_id: str) -> None:
        super().__init__()
        self.source_id = source_id
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, SyncWorker] = {}

    def run(self) -> None:
        def _progress(msg: str) -> None:
            self.progress.emit(self.source_id, msg)

        result = sync_source(self.source_id, progress_cb=_progress)
        self.finished.emit(self.source_id, result.success, result.message)


class LibrariesManagerDialog(QDialog):
    def __init__(self, parent: QWidget, on_sync_complete: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Libraries Manager")
        self.setMinimumWidth(900)
        self.on_sync_complete = on_sync_complete

        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, SyncWorker] = {}

        layout = QVBoxLayout(self)

        self.git_banner = QLabel(self)
        self.git_banner.setStyleSheet("color: #D97706;")
        layout.addWidget(self.git_banner)

        form_row = QHBoxLayout()
        self.repo_input = QLineEdit(self)
        self.repo_input.setPlaceholderText("GitHub repo URL")
        self.branch_input = QLineEdit(self)
        self.branch_input.setPlaceholderText("Branch (default: main)")
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Display name (optional)")
        self.add_btn = QPushButton("Add", self)
        self.add_btn.clicked.connect(self._on_add_clicked)

        form_row.addWidget(self.repo_input, 2)
        form_row.addWidget(self.branch_input, 1)
        form_row.addWidget(self.name_input, 1)
        form_row.addWidget(self.add_btn)
        layout.addLayout(form_row)

        self.table = QTableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Repo", "Branch", "Synced", "Unsynced", "Last Sync", "Status", "Actions"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.progress_label = QLabel(self)
        self.progress_label.setText("")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self._refresh()

    def _refresh(self) -> None:
        git_available = git_client.is_git_available()
        if not git_available:
            self.git_banner.setText("Git is required to sync GitHub libraries. Install Git and restart StagePro.")
        else:
            self.git_banner.setText("")

        cfg = load_libraries_config()
        self.table.setRowCount(len(cfg.library_sources))
        for row, source in enumerate(cfg.library_sources):
            state = load_state(source.source_id)
            self._populate_row(row, source, state, git_available)

        self.table.resizeColumnsToContents()

    def _populate_row(self, row: int, source: LibrarySource, state: LibrarySyncState, git_available: bool) -> None:
        def _item(text: str) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            item.setData(Qt.UserRole, source.source_id)
            return item

        self.table.setItem(row, 0, _item(source.name or source.source_id))
        self.table.setItem(row, 1, _item(source.repo_url))
        self.table.setItem(row, 2, _item(source.default_branch))
        self.table.setItem(row, 3, _item(str(state.files_indexed)))
        self.table.setItem(row, 4, _item(self._unsynced_label(source, state, git_available)))
        self.table.setItem(row, 5, _item(state.last_success_at or "—"))
        self.table.setItem(row, 6, _item(state.status))

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        sync_btn = QPushButton("Sync", actions)
        sync_btn.setEnabled(git_available)
        sync_btn.setProperty("source_id", source.source_id)
        sync_btn.clicked.connect(self._on_sync_clicked)
        delete_btn = QPushButton("Delete", actions)
        delete_btn.setProperty("source_id", source.source_id)
        delete_btn.clicked.connect(self._on_delete_clicked)
        actions_layout.addWidget(sync_btn)
        actions_layout.addWidget(delete_btn)
        self.table.setCellWidget(row, 7, actions)

    def _unsynced_label(self, source: LibrarySource, state: LibrarySyncState, git_available: bool) -> str:
        mirror = source.mirror_dir()
        if not git_available or not mirror.exists() or not (mirror / ".git").exists():
            return "—"
        try:
            remote = git_client.head_commit(mirror, f"origin/{source.default_branch}")
            if state.last_commit and remote != state.last_commit:
                return "Updates"
            return "0"
        except Exception:
            return "—"

    def _on_sync_clicked(self) -> None:
        button = self.sender()
        source_id = button.property("source_id") if button else None
        if source_id:
            self._start_sync(str(source_id))

    def _on_delete_clicked(self) -> None:
        button = self.sender()
        source_id = button.property("source_id") if button else None
        if source_id:
            self._delete_source(str(source_id))

    def _on_add_clicked(self) -> None:
        repo = self.repo_input.text().strip()
        if not repo:
            QMessageBox.warning(self, "Missing repo", "Please enter a repository URL.")
            return
        branch = self.branch_input.text().strip() or "main"
        name = self.name_input.text().strip() or repo.rsplit("/", 1)[-1]

        cfg = load_libraries_config()
        source_id = self._make_source_id(repo)
        if any(s.source_id == source_id for s in cfg.library_sources):
            QMessageBox.warning(self, "Duplicate", "This repository already exists in your libraries.")
            return

        source = LibrarySource(
            source_id=source_id,
            name=name,
            repo_url=repo,
            default_branch=branch,
            include_globs=["**/*.cho", "**/*.chopro", "**/*.pro", "**/*.txt"],
            exclude_globs=["**/.git/**"],
            sync={"mode": "manual", "pin": {"enabled": False, "ref": None}},
            auth={"mode": "none", "token_keychain_id": None},
            local={},
        )
        cfg.library_sources.append(source)
        save_libraries_config(cfg)
        save_state(source_id, LibrarySyncState())

        self.repo_input.clear()
        self.branch_input.clear()
        self.name_input.clear()
        self._refresh()

    def _start_sync(self, source_id: str) -> None:
        if source_id in self._threads:
            return

        thread = QThread(self)
        worker = SyncWorker(source_id)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_sync_finished)

        # IMPORTANT: ensure proper shutdown/cleanup order
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._threads[source_id] = thread
        self._workers[source_id] = worker  # <-- keep a strong reference

        thread.start()
        self._set_status(source_id, "syncing")
        self.progress_label.setText("Syncing…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)


    def _on_progress(self, source_id: str, message: str) -> None:
        self._set_status(source_id, message)
        self.progress_label.setText(f"{source_id}: {message}")

    def _on_sync_finished(self, source_id: str, success: bool, message: str) -> None:
        self._threads.pop(source_id, None)
        self._workers.pop(source_id, None)  # <-- release worker ref now that thread is quitting
        state = load_state(source_id)
        if not success:
            QMessageBox.warning(self, "Sync failed", message)
        state.status = "idle" if success else "error"
        state.last_error = None if success else message
        save_state(source_id, state)
        self._refresh()
        if not self._threads:
            self.progress_label.setText(message if message else "")
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1 if success else 0)
            self.progress_bar.setVisible(False)
        if success and self.on_sync_complete:
            self.on_sync_complete()

    def _set_status(self, source_id: str, status: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == source_id:
                status_item = self.table.item(row, 6)
                if status_item:
                    status_item.setText(status)
                break

    def _delete_source(self, source_id: str) -> None:
        resp = QMessageBox.question(
            self,
            "Delete library",
            "Delete this library source? This will remove local mirror and published files.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        cfg = load_libraries_config()
        cfg.library_sources = [s for s in cfg.library_sources if s.source_id != source_id]
        save_libraries_config(cfg)

        self._delete_source_dirs(source_id)
        self._refresh()
        if self.on_sync_complete:
            self.on_sync_complete()

    def _delete_source_dirs(self, source_id: str) -> None:
        for path in (libraries_sources_dir() / source_id, libraries_published_dir() / source_id):
            if path.exists():
                try:
                    if path.is_dir():
                        for child in path.rglob("*"):
                            if child.is_file():
                                child.unlink()
                        for child in sorted(path.rglob("*"), reverse=True):
                            if child.is_dir():
                                child.rmdir()
                        path.rmdir()
                    else:
                        path.unlink()
                except Exception:
                    pass

    @staticmethod
    def _make_source_id(repo_url: str) -> str:
        digest = hashlib.sha1(repo_url.encode("utf-8")).hexdigest()[:8]
        return f"gh_{digest}"
