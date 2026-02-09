from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication, QCursor, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)


def build_song_editor_dialog(parent, title: str, initial_text: str, info_path: Path, is_copy: bool) -> QDialog:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    # --- Tag buttons row --------------------------------------------------------
    tag_row = QHBoxLayout()
    tag_row.setContentsMargins(0, 0, 0, 0)

    def _btn(label: str, on_click):
        b = QPushButton(label, dlg)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.clicked.connect(on_click)
        return b

    # Determine which screen the dialog should appear on
    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen is None:
        screen = QGuiApplication.primaryScreen()

    screen_geom = screen.availableGeometry()

    # Calculate desired size
    width = int(screen_geom.width() * 0.50)
    height = int(screen_geom.height() * 0.75)

    # Center the dialog on that screen
    x = screen_geom.x() + (screen_geom.width() - width) // 2
    y = screen_geom.y() + (screen_geom.height() - height) // 2

    dlg.setGeometry(QRect(x, y, width, height))

    # Remember focus so we can restore it after closing.
    prev_focus = QApplication.focusWidget()

    layout = QVBoxLayout(dlg)

    info = QLabel(dlg)
    if is_copy:
        info.setText(
            "Editing a local copy.\n"
            f"Save target: {info_path}\n\n"
            "Tip: your library copy stays unchanged."
        )
    else:
        info.setText(f"Save target: {info_path}")
    info.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(info)

    editor = QTextEdit(dlg)
    editor.setPlainText(initial_text)
    editor.setLineWrapMode(QTextEdit.NoWrap)
    editor.setFocusPolicy(Qt.StrongFocus)
    layout.addLayout(tag_row)
    layout.addWidget(editor, 1)

    def _insert_text(snippet: str, select_placeholder: str | None = None) -> None:
        cur = editor.textCursor()

        # If user has selected text and the snippet contains "{sel}", wrap it.
        if cur.hasSelection() and "{sel}" in snippet:
            selected = cur.selectedText()
            # selectedText() uses U+2029 for line breaks; normalize back to \n
            selected = selected.replace("\u2029", "\n")
            snippet_to_insert = snippet.replace("{sel}", selected)
        else:
            snippet_to_insert = snippet

        cur.beginEditBlock()
        cur.insertText(snippet_to_insert)
        cur.endEditBlock()

        # Optionally select a placeholder so user can type immediately
        if select_placeholder:
            doc = editor.document()
            full = doc.toPlainText()
            start = full.rfind(select_placeholder)
            if start != -1:
                cur = editor.textCursor()
                cur.setPosition(start)
                cur.setPosition(start + len(select_placeholder), QTextCursor.KeepAnchor)
                editor.setTextCursor(cur)

        editor.setFocus(Qt.OtherFocusReason)

    def _ensure_header_top() -> None:
        """If cursor isn't at top, jump to top before inserting title/artist metadata."""
        cur = editor.textCursor()
        if cur.position() != 0:
            cur.setPosition(0)
            editor.setTextCursor(cur)

    # Title / Artist
    tag_row.addWidget(_btn("Title", lambda: (_ensure_header_top(), _insert_text("{title: TITLE}\n", "TITLE"))))

    # In ChordPro, "artist" is commonly stored in {subtitle: ...}
    tag_row.addWidget(_btn("Artist", lambda: (_ensure_header_top(), _insert_text("{subtitle: ARTIST}\n", "ARTIST"))))

    # Tempo / Key
    tag_row.addWidget(_btn("Tempo", lambda: (_ensure_header_top(), _insert_text("{tempo: 120}\n", "120"))))

    tag_row.addWidget(_btn("Key", lambda: (_ensure_header_top(), _insert_text("{key: Am}\n", "Am"))))

    # Notes (comment meta)
    tag_row.addWidget(_btn("Notes", lambda: _insert_text("{comment: NOTES}\n", "NOTES")))

    # Chords helper (inserts a starter chord line; user can edit)
    tag_row.addWidget(_btn("Chords line", lambda: _insert_text("[Am] [F] [C] [G]\n")))

    # Section blocks (wrap selection if selected)
    tag_row.addWidget(_btn("Verse", lambda: _insert_text(
        "{start_of_verse}\n{sel}\n{end_of_verse}\n\n" if editor.textCursor().hasSelection()
        else "{start_of_verse}\nLYRICS...\n{end_of_verse}\n\n",
        "LYRICS..."
    )))

    tag_row.addWidget(_btn("Chorus", lambda: _insert_text(
        "{start_of_chorus}\n{sel}\n{end_of_chorus}\n\n" if editor.textCursor().hasSelection()
        else "{start_of_chorus}\nLYRICS...\n{end_of_chorus}\n\n",
        "LYRICS..."
    )))

    tag_row.addWidget(_btn("Bridge", lambda: _insert_text(
        "{start_of_bridge}\n{sel}\n{end_of_bridge}\n\n" if editor.textCursor().hasSelection()
        else "{start_of_bridge}\nLYRICS...\n{end_of_bridge}\n\n",
        "LYRICS..."
    )))

    tag_row.addStretch(1)

    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=dlg)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    # Make tab order predictable: editor -> Save -> Cancel -> editor
    save_btn = buttons.button(QDialogButtonBox.Save)
    cancel_btn = buttons.button(QDialogButtonBox.Cancel)
    if save_btn and cancel_btn:
        dlg.setTabOrder(editor, save_btn)
        dlg.setTabOrder(save_btn, cancel_btn)
        dlg.setTabOrder(cancel_btn, editor)

    # Dialog-local shortcuts only
    # Ctrl+S saves (accepts dialog)
    if save_btn:
        save_btn.setDefault(False)   # don’t steal Enter
        save_btn.setAutoDefault(False)
        save_sc = QShortcut(QKeySequence.Save, dlg)
        save_sc.setContext(Qt.WidgetWithChildrenShortcut)
        save_sc.activated.connect(dlg.accept)

    # Esc cancels (rejects dialog) — QDialog usually does this already, but make it explicit.
    esc_sc = QShortcut(QKeySequence.Cancel, dlg)
    esc_sc.setContext(Qt.WidgetWithChildrenShortcut)
    esc_sc.activated.connect(dlg.reject)

    # Focus editor reliably after show (important on some platforms/window managers)
    dlg.setFocusProxy(editor)
    QTimer.singleShot(0, editor.setFocus)

    # Restore prior focus when done
    def _restore_focus(_result: int):
        if prev_focus is not None:
            QTimer.singleShot(0, lambda: prev_focus.setFocus(Qt.OtherFocusReason))
    dlg.finished.connect(_restore_focus)

    dlg._editor = editor
    return dlg
