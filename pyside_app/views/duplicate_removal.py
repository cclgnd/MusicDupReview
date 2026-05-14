import os
import html
from difflib import SequenceMatcher
import hashlib
import re
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRect, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from db_repository import duplicate_group_ids, duplicate_group_rows
from duplicate_rules import apply_rule_to_groups, rule_label
from file_actions import FileActionError, send_to_recycle_bin
from pyside_app.config import APP_DIR, MATCH_OPTIONS, RULE_OPTIONS
from pyside_app.data_sources import all_file_rows, duplicate_extension_values, duplicate_group_summaries, file_extension_values
from pyside_app.db import open_conn
from pyside_app.formatting import decision_label, format_bytes
from pyside_app.settings import load_app_settings, save_app_settings
from review_state import save_decision, save_decisions_bulk
from undo_service import UndoStack


BG_DEEP = "#0a0a10"
BG_BASE = "#13131a"
BG_CARD = "#1a1a24"
BG_CARD_HI = "#22222e"
BG_HEADER = "#0d0d12"
FG_TEXT = "#d4d4dc"
FG_MUTED = "#888894"
FG_HINT = "#555560"
ACCENT_BLUE = "#3b5bdb"
ACCENT_AMBER = "#e07b39"
ACCENT_SAGE = "#34c478"
ACCENT_BORDER = "#252530"
ACCENT_DIVIDER = "#1e1e28"
MISSING_BG = "#2a1116"
MISSING_BORDER = "#9b3030"
MISSING_FG = "#e06060"

EXTENSION_COLORS = {
    ".mp3": "#6ea8fe",
    ".flac": "#e07b39",
    ".wav": "#e06090",
    ".ogg": "#8fd0c0",
    ".m4a": "#a9c7f0",
    ".jpg": "#34c478",
    ".jpeg": "#34c478",
    ".png": "#9fd89f",
    ".flp": "#e07b39",
    ".pkf": "#34c478",
}

HASH_COLORS = [
    "#6ea8fe",
    "#e07b39",
    "#34c478",
    "#e06090",
    "#c4a7ff",
    "#e3cf86",
    "#8fd0c0",
    "#a9c7f0",
    "#9fd89f",
    "#d2b6e8",
]

AUDIO_HASH_COLORS = [
    "#3b5bdb",
    "#8fd0c0",
    "#a9c7f0",
    "#9fd89f",
    "#d2b6e8",
    "#b8d8d8",
    "#6ea8fe",
    "#e3cf86",
    "#c4a7ff",
    "#34c478",
]

PREVIEW_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".ico", ".tif", ".tiff"}
THUMB_CACHE_DIR = APP_DIR / "artifacts" / "thumb_cache"
THUMB_MAX_SIZE = (220, 140)


class ImagePreviewOverlay(QWidget):
    def __init__(self, parent, path):
        super().__init__(parent.window(), Qt.Window | Qt.FramelessWindowHint)
        self.original = QPixmap(path)
        self.zoom = 1.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setObjectName("ImagePreviewFull")
        self.close_button = QPushButton("X")
        self.close_button.setObjectName("ImagePreviewClose")
        self.close_button.clicked.connect(self.close)
        self.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 225);
            }
            QLabel#ImagePreviewFull {
                background: transparent;
            }
            QPushButton#ImagePreviewClose {
                background: #181818;
                color: #d4d4dc;
                border: 1px solid #444;
                font-weight: 900;
                min-width: 34px;
                max-width: 34px;
                min-height: 30px;
                max-height: 30px;
            }
            QPushButton#ImagePreviewClose:hover {
                color: #e07b39;
                border-color: #e07b39;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(self.close_button)
        layout.addLayout(top)
        layout.addWidget(self.image_label, 1)
        screen = parent.window().screen()
        if screen:
            self.setGeometry(screen.geometry())
        self.render_image()
        self.setFocusPolicy(Qt.StrongFocus)

    def render_image(self):
        if self.original.isNull():
            self.image_label.setText("Image preview unavailable")
            return
        width = max(1, int(self.original.width() * self.zoom))
        height = max(1, int(self.original.height() * self.zoom))
        pixmap = self.original.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def wheelEvent(self, event):
        step = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
        self.zoom = max(0.1, min(8.0, self.zoom * step))
        self.render_image()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Space):
            self.close()
            return
        super().keyPressEvent(event)


class InlineImagePreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original = QPixmap()
        self.setObjectName("InlineImagePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip("Image preview. Select row and press Space for full preview.")
        self.setMinimumWidth(72)
        self.setMaximumWidth(160)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        self.setText("")

    def set_thumbnail(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.original = pixmap
        self.render_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_pixmap()

    def render_pixmap(self):
        if self.original.isNull():
            self.clear()
            return
        target = self.contentsRect().size()
        if target.width() <= 0 or target.height() <= 0:
            return
        self.setPixmap(self.original.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class ThumbnailWorker(QThread):
    thumbnail_ready = Signal(int, str, int)

    def __init__(self, jobs, generation):
        super().__init__()
        self.jobs = jobs
        self.generation = generation

    def run(self):
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return
        for file_id, source_path, cache_path in self.jobs:
            try:
                cache = Path(cache_path)
                if not cache.exists():
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    with Image.open(source_path) as image:
                        image = ImageOps.exif_transpose(image)
                        image.thumbnail(THUMB_MAX_SIZE)
                        if image.mode not in ("RGB", "RGBA"):
                            image = image.convert("RGBA")
                        image.save(cache, format="PNG", optimize=True)
                self.thumbnail_ready.emit(file_id, str(cache), self.generation)
            except (OSError, ValueError):
                continue


class ToolbarHandle(QFrame):
    def __init__(self, item):
        super().__init__(item)
        self.item = item
        self.setObjectName("ToolbarDragHandle")
        self.setFixedHeight(4)
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return
        drag = QDrag(self)
        data = QMimeData()
        data.setData("application/x-dup-toolbar-item", str(id(self.item)).encode("ascii"))
        drag.setMimeData(data)
        drag.exec(Qt.MoveAction)


class DraggableToolbarItem(QFrame):
    def __init__(self, owner, key, child, label_text, description, hideable=True):
        super().__init__()
        self.owner = owner
        self.key = key
        self.child = child
        self.hideable = hideable
        self.setObjectName("ToolbarDraggableItem")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.handle = ToolbarHandle(self)
        self.label = QLabel(label_text)
        self.label.setObjectName("ToolbarItemTag")
        self.label.mouseDoubleClickEvent = self.rename_label
        self.label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.label.customContextMenuRequested.connect(self.show_label_menu)
        self.setToolTip(description)
        self.label.setToolTip(description)
        child.setToolTip(description)
        layout.addWidget(self.handle)
        layout.addWidget(self.label)
        layout.addWidget(child)
        self.handle.setProperty("active", False)

    def rename_label(self, _event):
        text, accepted = QInputDialog.getText(self, "Rename toolbar label", "Label", text=self.label.text())
        if accepted and text.strip():
            self.owner.rename_toolbar_item(self, text.strip())

    def show_label_menu(self, position):
        menu = QMenu(self)
        menu.addAction("Rename", lambda: self.rename_label(None))
        if self.hideable:
            menu.addAction("Hide", lambda: self.owner.hide_toolbar_item(self))
        menu.exec(self.label.mapToGlobal(position))

    def enterEvent(self, event):
        self.handle.setProperty("active", True)
        self.handle.style().unpolish(self.handle)
        self.handle.style().polish(self.handle)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.handle.setProperty("active", False)
        self.handle.style().unpolish(self.handle)
        self.handle.style().polish(self.handle)
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-dup-toolbar-item"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        source_id = int(bytes(event.mimeData().data("application/x-dup-toolbar-item")).decode("ascii"))
        self.owner.move_toolbar_item(source_id, id(self))
        event.acceptProposedAction()


class FileNameLabel(QWidget):
    def __init__(self, owner, row, group_rows, path_label=None):
        super().__init__()
        self.owner = owner
        self.row = row
        self.group_rows = group_rows
        self.path_label = path_label
        self.editing_active = False
        self.commit_in_progress = False
        self.display = QLabel()
        self.display.setObjectName("FileNameReadOnly")
        self.display.setTextFormat(Qt.RichText)
        self.display.setTextInteractionFlags(Qt.NoTextInteraction)
        self.editor = QLineEdit(row.get("nombre") or Path(row.get("ruta") or "").name)
        self.editor.setObjectName("FileRenameEditor")
        self.editor.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.display)
        layout.addWidget(self.editor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.display.setContextMenuPolicy(Qt.CustomContextMenu)
        self.display.mousePressEvent = self.display_mouse_press
        self.display.customContextMenuRequested.connect(self.show_file_menu)
        self.customContextMenuRequested.connect(self.show_file_menu)
        self.editor.editingFinished.connect(self.commit_rename)
        self.editor.installEventFilter(self)
        self.setText(self.editor.text())
        self.sync_width()

    def text(self):
        return self.editor.text()

    def setText(self, text):
        self.editor.setText(text)
        self.display.setText(html.escape(text))

    def sync_width(self):
        text_width = self.editor.fontMetrics().horizontalAdvance(self.text())
        self.setFixedWidth(max(260, text_width + 42))

    def display_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.start_edit()
            return
        super().mousePressEvent(event)

    def start_edit(self):
        if self.editing_active:
            return
        self.editing_active = True
        self.display.hide()
        self.editor.show()
        self.sync_width()
        self.editor.setFocus(Qt.MouseFocusReason)
        self.editor.selectAll()

    def eventFilter(self, watched, event):
        if watched is self.editor and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape and self.editing_active:
            self.cancel_rename()
            return True
        return super().eventFilter(watched, event)

    def commit_rename(self):
        if not self.editing_active or self.commit_in_progress:
            return
        self.commit_in_progress = True
        self.editing_active = False
        new_name = self.text().strip()
        old_name = Path(self.row.get("ruta") or "").name
        self.finish_label_mode()
        if not new_name or new_name == old_name:
            self.setText(old_name)
            self.sync_width()
            self.commit_in_progress = False
            return
        if not self.owner.rename_file(self.row, self.group_rows, new_name, refresh=False):
            self.setText(old_name)
            self.sync_width()
            self.commit_in_progress = False
            return
        self.setText(self.row.get("nombre") or new_name)
        self.apply_master_highlight()
        self.sync_width()
        if self.path_label:
            self.path_label.setText(self.owner.file_path_suffix(self.row))
        self.owner.status.setText(f"Renamed file: {self.text()}")
        self.commit_in_progress = False

    def cancel_rename(self):
        self.editing_active = False
        self.setText(Path(self.row.get("ruta") or "").name)
        self.sync_width()
        self.finish_label_mode()

    def finish_label_mode(self):
        self.editor.hide()
        self.display.show()
        self.editor.deselect()
        self.editor.setCursorPosition(0)
        self.editor.clearFocus()
        self.apply_master_highlight()
        self.sync_width()

    def show_file_menu(self, position):
        menu = QMenu(self)
        menu.addAction("Rename", self.start_edit)
        sender = self.sender()
        target = sender if isinstance(sender, QWidget) else self
        menu.exec(target.mapToGlobal(position))

    def apply_master_highlight(self):
        master = next((row for row in self.group_rows if (row.get("decision") or "") == "master"), None)
        if not master or master.get("id") == self.row.get("id"):
            self.display.setText(html.escape(self.text()))
            self.display.setToolTip("")
            return
        self.display.setText(self.owner.highlight_filename_against_master(self.text(), master))
        self.display.setToolTip("In test: highlighted filename parts differ from Master.")


class PathLabel(QLabel):
    def __init__(self, owner, row, group_rows):
        super().__init__(owner.file_path_suffix(row))
        self.owner = owner
        self.row = row
        self.group_rows = group_rows

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.owner.select_row(self.row, self.group_rows)
            return
        super().mousePressEvent(event)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=8):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self.items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self.spacing()
            if next_x - self.spacing() > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self.spacing()
                next_x = x + hint.width() + self.spacing()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()

MATCH_BADGES = {
    "md5": ("EXACT FILE", ACCENT_SAGE, "#062218"),
    "audio_md5": ("SAME AUDIO", ACCENT_BLUE, "#0e2040"),
    "image_ahash": ("SAME IMAGE", ACCENT_SAGE, "#062218"),
    "nombre_tamano": ("NAME SIZE", ACCENT_AMBER, "#2a1608"),
    "nombre_normalizado": ("SIMILAR NAME", ACCENT_AMBER, "#2a1608"),
    "nombre_exacto": ("SIMILAR NAME", ACCENT_AMBER, "#2a1608"),
    "nombre_identico": ("EXACT FILENAME", "#6ea8fe", "#0e2040"),
}

CONFIDENCE_DETAILS = {
    "md5": "100% confidence. Same file MD5 means exact byte-for-byte clone.",
    "audio_md5": "100% confidence. Based on Exact audio info, total file sizes may differ due to (IDTags) differences.",
    "nombre_identico": "100% confidence. Same filename only; content can still differ.",
    "nombre_tamano": "95% confidence. Same normalized name and same file size.",
    "image_ahash": "92% confidence. Same image perceptual hash from image metadata.",
    "nombre_normalizado": "80% confidence. Same normalized filename; review manually before deleting.",
}

MATCH_RULE_DETAILS = {
    "all": "Show every duplicate group except disabled image-size-only groups.",
    "md5": "Exact file clone rule. Groups files with identical MD5 bytes.",
    "audio_md5": "Exact audio rule. Based on Exact audio info, total file sizes may differ due to (IDTags) differences.",
    "image_ahash": "Same image rule. Groups images with identical perceptual image hash.",
    "nombre_tamano": "Name + size rule. Groups files with same normalized filename and same byte size.",
    "nombre_normalizado": "Similar name rule. Groups files with same normalized filename; confidence lower.",
    "nombre_identico": "Exact filename rule. Groups files with identical filename text.",
}

GROUP_SORT_OPTIONS = [
    ("Biggest first", "biggest file"),
    ("Smallest first", "smallest file"),
    ("A to Z", "name"),
    ("Z to A", "name desc"),
    ("Newest first", "date"),
    ("Same file hash", "same_file_hash"),
    ("Same Audio hash", "same_audio_hash"),
]

ROW_SORT_VALUES = {"same_file_hash", "same_audio_hash"}


class DuplicateRefreshWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path, match_filter, extension_filter, search_text, group_sort, hide_resolved):
        super().__init__()
        self.db_path = db_path
        self.match_filter = match_filter
        self.extension_filter = extension_filter
        self.search_text = search_text
        self.group_sort = group_sort
        self.hide_resolved = hide_resolved

    def run(self):
        try:
            if self.match_filter == "all":
                rows = all_file_rows(
                    self.db_path,
                    extension_filter=self.extension_filter,
                    search_text=self.search_text,
                    sort_value=self.group_sort,
                    limit=500,
                )
                self.finished_ok.emit({
                    "mode": "all_files",
                    "extensions": file_extension_values(self.db_path),
                    "group_ids": [],
                    "visible_group_ids": [],
                    "group_rows": [],
                    "groups": [],
                    "files": rows,
                    "total_files": len(rows),
                })
                return
            group_sort = "group_id" if self.group_sort in ROW_SORT_VALUES else self.group_sort
            row_sort = self.group_sort if self.group_sort in ROW_SORT_VALUES else "hash"
            group_ids, visible_group_ids, group_rows, total_files = duplicate_group_summaries(
                self.db_path,
                match_filter=self.match_filter,
                extension_filter=self.extension_filter,
                search_text=self.search_text,
                group_sort=group_sort,
                limit=50,
            )
            groups = []
            with open_conn(self.db_path) as conn:
                for group_id in visible_group_ids:
                    rows = duplicate_group_rows(conn, group_id, row_sort)
                    if len(rows) >= 2:
                        if self.hide_resolved and sum(1 for row in rows if os.path.exists(row.get("ruta") or "")) <= 1:
                            continue
                        groups.append(rows)
            self.finished_ok.emit({
                "mode": "duplicate_groups",
                "extensions": duplicate_extension_values(self.db_path),
                "group_ids": group_ids,
                "visible_group_ids": visible_group_ids,
                "group_rows": group_rows,
                "groups": groups,
                "files": [],
                "total_files": total_files,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class DuplicateRemovalView(QWidget):
    new_search_requested = Signal()
    release_playback_requested = Signal(str)
    loading_finished = Signal()

    def __init__(self, db_path_getter):
        super().__init__()
        self.db_path_getter = db_path_getter
        self.current_group_id = None
        self.current_rows = []
        self.current_row = None
        self.loaded_group_ids = []
        self.all_files_mode = False
        self.refresh_worker = None
        self.undo_stack = UndoStack(maxlen=400)
        self.row_widgets = {}
        self.rows_by_id = {}
        self.preview_labels = {}
        self.thumbnail_memory_cache = {}
        self.thumbnail_pending = set()
        self.thumbnail_worker = None
        self.thumbnail_generation = 0
        self.hash_ids = {}
        self.audio_hash_ids = {}
        self.image_preview = None
        self.base_text_size = 10
        self.text_scale_offset = 0
        self.app_settings = load_app_settings()
        self.toolbar_labels = dict(self.app_settings.get("duplicate_toolbar_labels") or {})
        self.hidden_toolbar_keys = set(self.app_settings.get("duplicate_toolbar_hidden") or [])
        self.toolbar_order = list(self.app_settings.get("duplicate_toolbar_order") or [])
        self.toolbar_items_by_key = {}

        self.match = QComboBox()
        for label, value in MATCH_OPTIONS:
            self.match.addItem(label, value)
            self.match.setItemData(self.match.count() - 1, MATCH_RULE_DETAILS.get(value, ""), Qt.ToolTipRole)
        match_value = self.app_settings.get("filter_type") or "all"
        self.match.setCurrentIndex(max(0, self.match.findData(match_value)))
        self.match.setObjectName("HeaderCombo")
        self.update_match_tooltip()

        self.rule = QComboBox()
        for label, value in RULE_OPTIONS:
            self.rule.addItem(label, value)
        self.rule.setObjectName("HeaderCombo")

        self.extension_value = "ALL"
        self.all_extensions = []
        self.sort_value = "biggest file"
        self.hide_resolved = False
        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("Search")

        self.summary_left = QLabel("")
        self.summary_center = QLabel("")
        self.summary_right = QLabel("")
        self.status = QLabel("Ready")

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(14, 10, 14, 14)
        self.cards_layout.setSpacing(16)
        self.cards_layout.addStretch(1)
        self.apply_text_scale()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.cards_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self.schedule_visible_thumbnail_load)

        self.refresh_button = self.ghost_button("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.prev_button = self.ghost_button("Prev")
        self.next_button = self.ghost_button("Next")
        self.apply_button = self.primary_button("Apply")
        self.apply_button.clicked.connect(self.apply_loaded_page)
        self.reset_button = self.ghost_button("Reset")
        self.reset_button.clicked.connect(self.reset_loaded_page)
        self.new_search_button = self.primary_button("Search")
        self.new_search_button.clicked.connect(self.new_search_requested.emit)
        self.hide_resolved_button = self.segment_button("Hide Resolved", checked=False)
        self.hide_resolved_button.clicked.connect(self.toggle_hide_resolved)
        self.add_function_button = self.ghost_button("Add function")
        self.add_function_button.clicked.connect(self.show_add_function_menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_toolbar_container())
        root.addWidget(self.build_summary())
        root.addWidget(self.scroll, 1)

        self.match.currentIndexChanged.connect(self.update_match_tooltip)
        self.match.currentIndexChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.refresh)
        QShortcut(QKeySequence("K"), self, activated=lambda: self.set_selected_file_state("master"))
        QShortcut(QKeySequence("T"), self, activated=lambda: self.set_selected_file_state("delete"))
        QShortcut(QKeySequence("P"), self, activated=lambda: self.set_selected_file_state("protected"))
        QShortcut(QKeySequence("I"), self, activated=lambda: self.set_selected_file_state("ignored"))
        QShortcut(QKeySequence("U"), self, activated=lambda: self.set_selected_file_state(""))
        QShortcut(QKeySequence("D"), self, activated=self.recycle_selected_files_direct)
        QShortcut(QKeySequence("Esc"), self, activated=self.clear_selection)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_last_action)

    def build_toolbar_container(self):
        toolbar = self.build_toolbar()
        toolbar.setMinimumWidth(0)
        toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        return toolbar

    def build_toolbar(self):
        bar = QFrame()
        bar.setObjectName("DuplicateToolbar")
        layout = FlowLayout(bar, margin=10, spacing=8)
        self.toolbar_layout = layout
        self.toolbar_items = []
        self.toolbar_items_by_key = {}
        self.extension_button = self.segment_button("All", checked=True)
        self.extension_button.clicked.connect(self.show_extension_menu)
        self.add_toolbar_item("extension", self.extension_button, "Extension", "Choose one file extension filter from current database results.")
        self.sort_button = self.segment_button("Biggest first", checked=True)
        self.sort_button.clicked.connect(self.show_sort_menu)
        self.add_toolbar_item("sort", self.sort_button, "Sort", "Choose one duplicate-group sort order.")
        self.add_toolbar_item("match_rule", self.match, "Rule", "Choose duplicate match rule. Menu items show exact rule details on hover.")
        self.add_toolbar_item("path_search", self.search, "Path search", "Filter visible duplicate groups by file path text.")
        details = self.ghost_button("Filters")
        details.clicked.connect(self.show_filter_details)
        self.add_toolbar_item("filters", details, "Filters", "Show current filter state and loaded result count.")
        self.add_toolbar_item("text_size", self.build_text_scale_widget(), "Text size", "Increase or decrease duplicate review text size.")
        self.add_toolbar_item(
            "new_search",
            self.new_search_button,
            "Search",
            "New search patterns:\n"
            "- Opens folder picker.\n"
            "- Scans selected folder recursively.\n"
            "- Reads file path, size, date, extension, file MD5, audio hash when possible.\n"
            "- Creates a separate database for each new search.\n"
            "- Keeps previous search databases separate, then shrinks previous database when possible.\n"
            "- Switches app to new database after scan.\n"
            "- Rebuilds duplicate groups inside new database.\n"
            "- Current Rule, Extension, Sort, Path search, Hide Resolved filters affect visible results after refresh.",
        )
        self.add_toolbar_item("hide_resolved", self.hide_resolved_button, "Resolved", "Hide groups where only one file remains on disk.")
        self.add_toolbar_item("reset", self.reset_button, "Reset", "Clear review choices from loaded groups.")
        self.add_toolbar_item("add_function", self.add_function_button, "Add function", "Show hidden toolbar functions.", hideable=False)
        self.restore_toolbar_order()
        return bar

    def add_toolbar_item(self, key, widget, label_text, description, hideable=True):
        label = self.toolbar_labels.get(key, label_text)
        item = DraggableToolbarItem(self, key, widget, label, description, hideable=hideable)
        self.toolbar_items_by_key[key] = item
        if key not in self.hidden_toolbar_keys or not hideable:
            self.toolbar_items.append(item)
            self.toolbar_layout.addWidget(item)
        else:
            item.hide()

    def rename_toolbar_item(self, item, text):
        item.label.setText(text)
        self.toolbar_labels[item.key] = text
        self.save_toolbar_settings()

    def hide_toolbar_item(self, item):
        if not item.hideable:
            return
        if item in self.toolbar_items:
            self.toolbar_layout.removeWidget(item)
            self.toolbar_items.remove(item)
        item.hide()
        self.hidden_toolbar_keys.add(item.key)
        self.persist_toolbar_order()
        self.save_toolbar_settings()
        self.toolbar_layout.invalidate()

    def show_toolbar_item(self, key):
        item = self.toolbar_items_by_key.get(key)
        if not item:
            return
        add_item = self.toolbar_items_by_key.get("add_function")
        if add_item in self.toolbar_items:
            self.toolbar_layout.removeWidget(add_item)
            self.toolbar_items.remove(add_item)
        self.hidden_toolbar_keys.discard(key)
        item.show()
        if item not in self.toolbar_items:
            self.toolbar_items.append(item)
            self.toolbar_layout.addWidget(item)
        if add_item:
            self.toolbar_items.append(add_item)
            self.toolbar_layout.addWidget(add_item)
        self.persist_toolbar_order()
        self.save_toolbar_settings()
        self.toolbar_layout.invalidate()

    def show_add_function_menu(self):
        menu = QMenu(self)
        hidden_items = [
            item for key, item in self.toolbar_items_by_key.items()
            if key in self.hidden_toolbar_keys and item.hideable
        ]
        if not hidden_items:
            action = menu.addAction("No hidden functions")
            action.setEnabled(False)
        for item in hidden_items:
            menu.addAction(item.label.text(), lambda key=item.key: self.show_toolbar_item(key))
        menu.exec(self.add_function_button.mapToGlobal(self.add_function_button.rect().bottomLeft()))

    def save_toolbar_settings(self):
        self.app_settings = load_app_settings()
        self.app_settings["duplicate_toolbar_labels"] = self.toolbar_labels
        self.app_settings["duplicate_toolbar_hidden"] = sorted(self.hidden_toolbar_keys)
        self.app_settings["duplicate_toolbar_order"] = [item.key for item in self.toolbar_items]
        save_app_settings(self.app_settings)

    def restore_toolbar_order(self):
        if not self.toolbar_order:
            return
        ordered_keys = [key for key in self.toolbar_order if key in self.toolbar_items_by_key]
        for key in self.toolbar_items_by_key:
            if key not in ordered_keys:
                ordered_keys.append(key)
        visible_items = [
            self.toolbar_items_by_key[key]
            for key in ordered_keys
            if key in self.toolbar_items_by_key
            and (key not in self.hidden_toolbar_keys or not self.toolbar_items_by_key[key].hideable)
        ]
        for item in self.toolbar_items:
            self.toolbar_layout.removeWidget(item)
        self.toolbar_items = visible_items
        for item in self.toolbar_items:
            self.toolbar_layout.addWidget(item)
        self.toolbar_layout.invalidate()

    def persist_toolbar_order(self):
        self.toolbar_order = [item.key for item in self.toolbar_items]

    def move_toolbar_item(self, source_id, target_id):
        source = next((item for item in self.toolbar_items if id(item) == source_id), None)
        target = next((item for item in self.toolbar_items if id(item) == target_id), None)
        if not source or not target or source is target:
            return
        self.toolbar_items.remove(source)
        target_index = self.toolbar_items.index(target)
        self.toolbar_items.insert(target_index, source)
        for item in self.toolbar_items:
            self.toolbar_layout.removeWidget(item)
        for item in self.toolbar_items:
            self.toolbar_layout.addWidget(item)
        self.persist_toolbar_order()
        self.save_toolbar_settings()
        self.toolbar_layout.invalidate()

    def build_text_scale_widget(self):
        box = QFrame()
        box.setObjectName("TextScaleWidget")
        shadow = QGraphicsDropShadowEffect(box)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        box.setGraphicsEffect(shadow)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        minus = QPushButton("-")
        minus.setObjectName("TextScaleButton")
        minus.clicked.connect(lambda: self.adjust_text_scale(-1))
        self.text_size_value = QLabel("")
        self.text_size_value.setObjectName("TextScaleValue")
        self.text_size_slider = QSlider(Qt.Horizontal)
        self.text_size_slider.setObjectName("TextScaleSlider")
        self.text_size_slider.setRange(-5, 5)
        self.text_size_slider.setValue(0)
        self.text_size_slider.setTickPosition(QSlider.TicksBelow)
        self.text_size_slider.setTickInterval(1)
        self.text_size_slider.valueChanged.connect(self.set_text_scale_offset)
        plus = QPushButton("+")
        plus.setObjectName("TextScaleButton")
        plus.clicked.connect(lambda: self.adjust_text_scale(1))

        layout.addWidget(minus)
        layout.addWidget(self.text_size_slider)
        layout.addWidget(self.text_size_value)
        layout.addWidget(plus)
        self.update_text_scale_label()
        return box

    def adjust_text_scale(self, step):
        value = max(-5, min(5, self.text_scale_offset + step))
        self.text_size_slider.setValue(value)

    def set_text_scale_offset(self, value):
        self.text_scale_offset = int(value)
        self.update_text_scale_label()
        self.apply_text_scale()

    def update_text_scale_label(self):
        if hasattr(self, "text_size_value"):
            self.text_size_value.setText(f"{self.base_text_size + self.text_scale_offset} pt")

    def apply_text_scale(self):
        size = self.base_text_size + self.text_scale_offset
        small = max(8, size - 1)
        title = max(9, size)
        self.cards_host.setStyleSheet(f"""
            QLabel#MatchBadge {{
                font-size: {small}pt;
            }}
            QLabel#GroupTitle,
            QLabel#FileNameReadOnly,
            QLineEdit#FileRenameEditor,
            QLabel#PathText,
            QLabel#MissingPathText {{
                font-size: {title}pt;
            }}
            QLabel#MetaLabel,
            QLabel#ConfidenceLabel,
            QLabel#SavePill,
            QLabel#SizeChip,
            QLabel#HashChip,
            QLabel#AudioChip,
            QLabel#MetaChip,
            QLabel#MissingFlag {{
                font-size: {small}pt;
            }}
        """)

    def build_summary(self):
        bar = QFrame()
        bar.setObjectName("DuplicateSummary")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 9, 16, 9)
        layout.addWidget(self.summary_left, 1)
        layout.addWidget(self.summary_center, 1)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.summary_right)
        layout.addWidget(self.apply_button)
        return bar

    def segment_button(self, text, checked=False):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setObjectName("SegmentButton")
        return button

    def ghost_button(self, text):
        button = QPushButton(text)
        button.setObjectName("GhostButton")
        return button

    def primary_button(self, text):
        button = QPushButton(text)
        button.setObjectName("PrimaryButton")
        return button

    def set_extension(self, value):
        self.extension_value = value
        self.extension_button.setText("All" if value == "ALL" else value.replace(".", "").upper())
        self.refresh()

    def update_match_tooltip(self):
        self.match.setToolTip(MATCH_RULE_DETAILS.get(self.match.currentData(), "Choose duplicate match rule."))

    def confidence_tooltip(self, match_type, score):
        detail = CONFIDENCE_DETAILS.get(
            match_type,
            "Confidence comes from duplicate detector score saved in database.",
        )
        rule = MATCH_RULE_DETAILS.get(match_type, "Rule details unavailable.")
        return f"Confidence: {score}%\n{detail}\nRule: {rule}"

    def set_sort(self, value):
        self.sort_value = value
        label = next((label for label, option_value in GROUP_SORT_OPTIONS if option_value == value), "Biggest first")
        self.sort_button.setText(label)
        self.refresh()

    def show_sort_menu(self):
        menu = QMenu(self)
        for label, value in GROUP_SORT_OPTIONS:
            action = menu.addAction(label, lambda sort=value: self.set_sort(sort))
            action.setCheckable(True)
            action.setChecked(value == self.sort_value)
        menu.exec(self.sort_button.mapToGlobal(self.sort_button.rect().bottomLeft()))

    def toggle_hide_resolved(self, checked):
        self.hide_resolved = bool(checked)
        self.hide_resolved_button.setText("X Hide Resolved" if self.hide_resolved else "Hide Resolved")
        self.refresh()

    def show_extension_menu(self):
        menu = QMenu(self)
        menu.addAction("All", lambda: self.set_extension("ALL"))
        for ext in getattr(self, "all_extensions", []):
            menu.addAction(ext, lambda value=ext: self.set_extension(value))
        menu.exec(self.extension_button.mapToGlobal(self.extension_button.rect().bottomLeft()))

    def show_filter_details(self):
        text = (
            f"Match: {self.match.currentText()}\n"
            f"Extension: {self.extension_value}\n"
            f"Sort: {self.sort_value}\n"
            f"Hide resolved: {'yes' if self.hide_resolved else 'no'}\n"
            f"Search: {self.search.text().strip() or 'none'}\n"
            f"Loaded groups: {len(self.loaded_group_ids)}"
        )
        QMessageBox.information(self, "Filter details", text)

    def set_extension_values(self, extensions):
        self.all_extensions = sorted(set(extensions))
        if self.extension_value not in ["ALL", *self.all_extensions]:
            self.extension_value = "ALL"
        self.extension_button.setText("All" if self.extension_value == "ALL" else self.extension_value.replace(".", "").upper())

    def refresh(self):
        db_path = self.db_path_getter()
        if not os.path.exists(db_path):
            self.render_groups([])
            self.summary_left.setText("Database not found")
            self.loading_finished.emit()
            return
        if self.refresh_worker and self.refresh_worker.isRunning():
            self.status.setText("Duplicate refresh already running.")
            return
        self.summary_left.setText("Loading duplicate groups...")
        self.refresh_button.setEnabled(False)
        self.refresh_worker = DuplicateRefreshWorker(
            db_path,
            self.match.currentData(),
            self.extension_value,
            self.search.text().strip(),
            self.sort_value,
            self.hide_resolved,
        )
        self.refresh_worker.finished_ok.connect(self._refresh_finished)
        self.refresh_worker.failed.connect(self._refresh_failed)
        self.refresh_worker.start()

    def _refresh_finished(self, result):
        self.refresh_button.setEnabled(True)
        self.set_extension_values(result["extensions"])
        self.loaded_group_ids = result["visible_group_ids"]
        self.all_files_mode = result.get("mode") == "all_files"
        self.current_group_id = None
        self.current_rows = []
        self.current_row = None
        self.set_duplicate_actions_enabled(not self.all_files_mode)
        if self.all_files_mode:
            rows = result.get("files", [])
            self.render_all_files(rows)
            loaded_size = sum((row.get("tamano") or 0) for row in rows)
            self.summary_left.setText(f"{len(rows):,} files")
            self.summary_center.setText(f"{format_bytes(loaded_size)} filtered")
            self.summary_right.setText("all files")
        else:
            self.render_groups(result["groups"])
            total_groups = len(result["group_ids"])
            loaded_files = sum(len(group) for group in result["groups"])
            loaded_size = sum((row.get("tamano") or 0) for group in result["groups"] for row in group)
            self.summary_left.setText(f"{total_groups:,} groups - showing 1-{len(result['groups'])}")
            self.summary_center.setText(f"{loaded_files:,} files - {format_bytes(loaded_size)} filtered")
            pages = max(1, (total_groups + 49) // 50)
            self.summary_right.setText(f"page 1 / {pages}")
        self.status.setText("Ready")
        self.loading_finished.emit()

    def _refresh_failed(self, message):
        self.refresh_button.setEnabled(True)
        self.summary_left.setText("Duplicate refresh failed")
        self.loading_finished.emit()
        QMessageBox.critical(self, "Refresh", message)

    def render_groups(self, groups):
        self.clear_cards()
        self.hash_ids = self.build_hash_ids(groups, "md5")
        self.audio_hash_ids = self.build_hash_ids(groups, "audio_md5")
        for rows in groups:
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, self.build_group_card(rows))
        self.schedule_visible_thumbnail_load()

    def render_all_files(self, rows):
        self.clear_cards()
        self.hash_ids = self.build_hash_ids([rows], "md5")
        self.audio_hash_ids = self.build_hash_ids([rows], "audio_md5")
        card = QFrame()
        card.setObjectName("GroupCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("GroupHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 14, 8)
        badge = QLabel("ALL FILES")
        badge.setObjectName("MatchBadge")
        badge.setStyleSheet(f"color:{FG_TEXT}; background:{BG_CARD_HI};")
        title = QLabel("Search files")
        title.setObjectName("GroupTitle")
        header_layout.addWidget(badge)
        header_layout.addWidget(title, 1)
        header_layout.addWidget(QLabel(f"{len(rows)} files"))
        layout.addWidget(header)
        for row in rows:
            layout.addWidget(self.build_file_row(row, [row]))
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self.schedule_visible_thumbnail_load()

    def clear_cards(self):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.row_widgets.clear()
        self.rows_by_id.clear()
        self.preview_labels.clear()
        self.thumbnail_pending.clear()
        self.thumbnail_generation += 1

    def set_duplicate_actions_enabled(self, enabled):
        for widget in (self.apply_button, self.reset_button, self.hide_resolved_button):
            widget.setEnabled(enabled)

    def build_hash_ids(self, groups, key):
        values = []
        seen = set()
        for group in groups:
            for row in group:
                value = row.get(key) or ""
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
        return {
            value: {
                "id": self.short_code(index),
                "color_index": index,
            }
            for index, value in enumerate(values)
        }

    def short_code(self, index):
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        base = len(alphabet)
        code = ""
        current = index
        while True:
            code = alphabet[current % base] + code
            current = current // base - 1
            if current < 0:
                return code

    def build_group_card(self, rows):
        group_id = rows[0].get("grupo_id")
        largest = max((row.get("tamano") or 0) for row in rows)
        recoverable = sum((row.get("tamano") or 0) for row in rows) - largest
        score = int((rows[0].get("score") or 0.8) * 100)
        match_type = rows[0].get("tipo_match") or ""
        badge_text, badge_fg, badge_bg = MATCH_BADGES.get(match_type, (match_type.upper() or "MATCH", FG_TEXT, BG_CARD_HI))
        confidence_tip = self.confidence_tooltip(match_type, score)
        title = self.group_title(group_id, rows)

        card = QFrame()
        card.setObjectName("GroupCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("GroupHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 14, 8)
        header_layout.setSpacing(10)
        badge = QLabel(badge_text)
        badge.setObjectName("MatchBadge")
        badge.setStyleSheet(f"color:{badge_fg}; background:{badge_bg};")
        badge.setToolTip(MATCH_RULE_DETAILS.get(match_type, confidence_tip))
        title_label = QLabel(title)
        title_label.setObjectName("GroupTitle")
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        confidence = QLabel(f"{score}%")
        confidence.setObjectName("ConfidenceLabel")
        confidence.setToolTip(confidence_tip)
        confidence_bar = self.confidence_bar(score)
        confidence_bar.setToolTip(confidence_tip)
        file_count = QLabel(f"{len(rows)} files")
        file_count.setObjectName("MetaLabel")
        save = QLabel(f"save {format_bytes(recoverable)}")
        save.setObjectName("SavePill")
        header_layout.addWidget(badge)
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(confidence_bar)
        header_layout.addWidget(confidence)
        header_layout.addWidget(file_count)
        header_layout.addWidget(save)
        layout.addWidget(header)

        for row in rows:
            layout.addWidget(self.build_file_row(row, rows))
        return card

    def confidence_bar(self, score):
        box = QFrame()
        box.setObjectName("ConfidenceTrack")
        fill = QFrame(box)
        fill.setObjectName("ConfidenceFill")
        fill.setStyleSheet(f"background:{ACCENT_SAGE if score >= 90 else ACCENT_AMBER};")
        fill.setGeometry(0, 2, max(6, int(56 * min(score, 100) / 100)), 3)
        return box

    def group_title(self, group_id, rows):
        first = rows[0]
        name = first.get("nombre") or Path(first.get("ruta") or "").name
        folder = self.short_folder(first.get("carpeta") or "")
        return f"{name} - group {group_id} - {folder}"

    def build_file_row(self, row, group_rows):
        missing = not os.path.exists(row.get("ruta") or "")
        selected = row is self.current_row
        frame = QFrame()
        frame.setObjectName("MissingFileRow" if missing else ("SelectedFileRow" if selected else "FileRow"))
        frame.setProperty("file_id", row.get("id"))
        self.rows_by_id[row.get("id")] = row
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(9)

        master = QPushButton("Master")
        master.setCheckable(True)
        master.setChecked((row.get("decision") or "") == "master")
        master.setObjectName("MasterButton")
        master.setFixedWidth(74)
        master.setVisible(bool(row.get("grupo_id")) and len(group_rows) > 1)
        master.clicked.connect(lambda checked=False, r=row, rows=group_rows: self.set_row_state(r, rows, "master" if checked else ""))
        layout.addWidget(master)
        layout.addSpacing(6)

        info = QVBoxLayout()
        info.setSpacing(4)
        info.setContentsMargins(4, 0, 0, 0)
        title_line = QHBoxLayout()
        title_line.setSpacing(5)
        title = FileNameLabel(self, row, group_rows)
        if missing:
            title.display.setProperty("missing", True)
            title.display.style().unpolish(title.display)
            title.display.style().polish(title.display)
        title.apply_master_highlight()
        title.sync_width()
        title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        path_text = PathLabel(self, row, group_rows)
        path_text.setObjectName("MissingPathText" if missing else "PathText")
        path_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_text.setMinimumWidth(0)
        path_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        title.path_label = path_text
        title_line.addWidget(title, 0)
        title_line.addWidget(path_text, 1)
        meta = QHBoxLayout()
        meta.setSpacing(6)
        meta.addWidget(self.chip(f"{int(row.get('tamano') or 0):,} bytes / {format_bytes(row.get('tamano'))}", "size"))
        meta.addWidget(self.extension_chip(row.get("extension") or ""))
        if row.get("md5"):
            meta.addWidget(self.hash_id_chip(row.get("md5"), "hash"))
        if row.get("audio_md5"):
            meta.addWidget(self.hash_id_chip(row.get("audio_md5"), "audio"))
        if missing:
            missing_label = QLabel("Deleted")
            missing_label.setObjectName("MissingFlag")
            meta.addWidget(missing_label)
        meta.addStretch(1)
        info.addLayout(title_line)
        info.addLayout(meta)
        layout.addLayout(info, 1)
        if self.is_image_row(row) and not missing:
            preview = self.image_row_preview(row)
            if preview:
                layout.addWidget(preview, 0)

        frame.mousePressEvent = lambda _event, r=row, rows=group_rows: self.select_row(r, rows)
        self.row_widgets[row.get("id")] = frame
        return frame

    def is_image_row(self, row):
        return (row.get("extension") or Path(row.get("ruta") or "").suffix).lower() in PREVIEW_IMAGE_EXTS

    def image_row_preview(self, row):
        label = InlineImagePreviewLabel()
        self.preview_labels[row.get("id")] = label
        return label

    def schedule_visible_thumbnail_load(self):
        QTimer.singleShot(0, self.load_visible_thumbnails)

    def load_visible_thumbnails(self):
        if self.thumbnail_worker and self.thumbnail_worker.isRunning():
            return
        viewport_top = self.scroll.verticalScrollBar().value()
        viewport_bottom = viewport_top + self.scroll.viewport().height()
        jobs = []
        for file_id, label in list(self.preview_labels.items()):
            row_widget = self.row_widgets.get(file_id)
            row = self.rows_by_id.get(file_id) or {}
            path = row.get("ruta") or ""
            if not row_widget or not path:
                continue
            top = row_widget.mapTo(self.cards_host, QPoint(0, 0)).y()
            bottom = top + row_widget.height()
            if bottom < viewport_top or top > viewport_bottom:
                continue
            cache_path = self.thumbnail_cache_path(row)
            if not cache_path:
                continue
            cache_key = str(cache_path)
            if cache_key in self.thumbnail_memory_cache:
                label.set_thumbnail(self.thumbnail_memory_cache[cache_key])
            elif cache_path.exists():
                self.thumbnail_memory_cache[cache_key] = str(cache_path)
                label.set_thumbnail(str(cache_path))
            elif file_id not in self.thumbnail_pending:
                self.thumbnail_pending.add(file_id)
                jobs.append((file_id, path, str(cache_path)))
            if len(jobs) >= 12:
                break
        if jobs:
            self.thumbnail_worker = ThumbnailWorker(jobs, self.thumbnail_generation)
            self.thumbnail_worker.thumbnail_ready.connect(self.apply_thumbnail)
            self.thumbnail_worker.finished.connect(self.thumbnail_worker_finished)
            self.thumbnail_worker.start()

    def thumbnail_cache_path(self, row):
        path = row.get("ruta") or ""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        key = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
        digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()
        return THUMB_CACHE_DIR / f"{digest}.png"

    def apply_thumbnail(self, file_id, cache_path, generation):
        if generation != self.thumbnail_generation:
            return
        self.thumbnail_pending.discard(file_id)
        label = self.preview_labels.get(file_id)
        if not label:
            return
        self.thumbnail_memory_cache[cache_path] = cache_path
        label.set_thumbnail(cache_path)

    def thumbnail_worker_finished(self):
        self.thumbnail_worker = None
        self.schedule_visible_thumbnail_load()

    def open_selected_image_preview(self):
        row = self.current_row
        if not row or not self.is_image_row(row):
            return False
        path = row.get("ruta") or ""
        if not os.path.exists(path):
            return False
        if self.image_preview:
            self.image_preview.close()
        self.image_preview = ImagePreviewOverlay(self, path)
        self.image_preview.destroyed.connect(lambda *_args: setattr(self, "image_preview", None))
        self.image_preview.showFullScreen()
        self.image_preview.raise_()
        self.image_preview.activateWindow()
        self.image_preview.setFocus()
        return True

    def highlight_filename_against_master(self, filename, master_row):
        master_name = master_row.get("nombre") or Path(master_row.get("ruta") or "").name
        path = Path(filename)
        master_path = Path(master_name)
        tokens = self.filename_tokens(path.stem)
        master_tokens = self.filename_tokens(master_path.stem)
        words = [token.lower() for token in tokens if self.is_filename_word(token)]
        master_words = [token.lower() for token in master_tokens if self.is_filename_word(token)]
        equal_word_indexes = set()
        matcher = SequenceMatcher(None, words, master_words, autojunk=False)
        for tag, start, end, _master_start, _master_end in matcher.get_opcodes():
            if tag == "equal":
                equal_word_indexes.update(range(start, end))

        word_index = 0
        pieces = []
        for token in tokens:
            escaped = html.escape(token)
            if not self.is_filename_word(token):
                pieces.append(escaped)
                continue
            if word_index in equal_word_indexes:
                pieces.append(escaped)
            else:
                pieces.append(
                    '<span style="background:#3a2412; color:#f0b070; '
                    'border:1px solid #8a4a20; padding:0 2px;">'
                    f"{escaped}</span>"
                )
            word_index += 1

        suffix = path.suffix
        if suffix:
            escaped_suffix = html.escape(suffix)
            if suffix.lower() != master_path.suffix.lower():
                pieces.append(
                    '<span style="background:#32161b; color:#e06060; '
                    'border:1px solid #7a2424; padding:0 2px;">'
                    f"{escaped_suffix}</span>"
                )
            else:
                pieces.append(escaped_suffix)
        return "".join(pieces)

    def filename_tokens(self, text):
        return re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", text)

    def is_filename_word(self, token):
        return bool(re.fullmatch(r"[A-Za-z0-9]+", token or ""))

    def file_title(self, row):
        name = row.get("nombre") or Path(row.get("ruta") or "").name
        path = row.get("ruta") or ""
        return f"{name}  -  {path}"

    def file_path_suffix(self, row):
        path = Path(row.get("ruta") or "")
        folder = str(path.parent) if str(path.parent) != "." else ""
        return f"- {folder}\\{path.name}" if folder else f"- {path.name}"

    def rename_file(self, row, group_rows, new_name, refresh=True):
        stored_path = Path(row.get("ruta") or "")
        current_path = self.resolve_existing_file_path(row)
        if not current_path.exists():
            QMessageBox.warning(self, "Rename file", f"File path needs refresh:\n{stored_path}")
            return False
        if str(current_path) != str(stored_path):
            self.save_row_path(row, current_path)
            self.update_row_path(row, group_rows, current_path)
        if not new_name:
            return False
        if new_name == current_path.name:
            return True
        if any(separator in new_name for separator in ("\\", "/")):
            QMessageBox.warning(self, "Rename file", "Filename cannot contain path separators.")
            return False
        target_path = current_path.with_name(new_name)
        if target_path.exists():
            QMessageBox.warning(self, "Rename file", "Target filename already exists.")
            return False
        try:
            self.release_playback_requested.emit(str(current_path))
            current_path.rename(target_path)
            with open_conn(self.db_path_getter()) as conn:
                conn.execute(
                    """
                    UPDATE archivos
                    SET ruta = ?, carpeta = ?, nombre = ?, extension = ?
                    WHERE id = ?
                    """,
                    (
                        str(target_path),
                        str(target_path.parent),
                        target_path.name,
                        target_path.suffix.lower(),
                        row["id"],
                    ),
                )
                conn.commit()
        except OSError as exc:
            QMessageBox.critical(self, "Rename file", str(exc))
            return False
        self.update_row_path(row, group_rows, target_path)
        if refresh:
            self.refresh()
            self.status.setText(f"Renamed file: {target_path.name}")
        return True

    def resolve_existing_file_path(self, row):
        stored_path = Path(row.get("ruta") or "")
        candidates = [stored_path]
        folder = row.get("carpeta") or str(stored_path.parent)
        name = row.get("nombre") or stored_path.name
        if folder and name:
            candidates.append(Path(folder) / name)
        for candidate in candidates:
            if candidate.exists():
                return candidate

        folder_path = Path(folder) if folder else stored_path.parent
        extension = (row.get("extension") or stored_path.suffix or "").lower()
        expected_size = row.get("tamano")
        if not folder_path.exists():
            return stored_path
        matches = []
        try:
            for child in folder_path.iterdir():
                if not child.is_file():
                    continue
                if extension and child.suffix.lower() != extension:
                    continue
                if expected_size and child.stat().st_size != expected_size:
                    continue
                matches.append(child)
        except OSError:
            return stored_path
        return matches[0] if len(matches) == 1 else stored_path

    def update_row_path(self, row, group_rows, path):
        path = Path(path)
        row["ruta"] = str(path)
        row["carpeta"] = str(path.parent)
        row["nombre"] = path.name
        row["extension"] = path.suffix.lower()
        for group_row in group_rows:
            if group_row.get("id") == row.get("id"):
                group_row.update(row)

    def save_row_path(self, row, path):
        path = Path(path)
        with open_conn(self.db_path_getter()) as conn:
            conn.execute(
                """
                UPDATE archivos
                SET ruta = ?, carpeta = ?, nombre = ?, extension = ?
                WHERE id = ?
                """,
                (
                    str(path),
                    str(path.parent),
                    path.name,
                    path.suffix.lower(),
                    row["id"],
                ),
            )
            conn.commit()

    def chip(self, text, kind):
        label = QLabel(text)
        label.setObjectName({"size": "SizeChip", "hash": "HashChip", "audio": "AudioChip"}.get(kind, "MetaChip"))
        return label

    def extension_chip(self, extension):
        label = self.chip(extension or "file", "ext")
        color = EXTENSION_COLORS.get(extension.lower(), FG_HINT)
        label.setStyleSheet(f"color:{color};")
        return label

    def hash_id_chip(self, value, kind):
        mapping = self.audio_hash_ids if kind == "audio" else self.hash_ids
        colors = AUDIO_HASH_COLORS if kind == "audio" else HASH_COLORS
        meta = mapping.get(value)
        if not meta:
            return self.chip("Audio Hash ID: -" if kind == "audio" else "Hash ID: -", kind)
        chip_id = meta["id"]
        color = colors[meta["color_index"] % len(colors)]
        text = f"Audio Hash ID: {chip_id}" if kind == "audio" else f"Hash ID: {chip_id}"
        label = self.chip(text, kind)
        if kind == "audio":
            label.setToolTip("Based on Exact audio info, total file sizes may differ due to (IDTags) differences.")
        label.setStyleSheet(f"""
            QLabel {{
                background: #111118;
                color: {color};
                border: 1px solid {color};
                padding: 2px 6px;
                font-family: Consolas;
                font-weight: 800;
            }}
        """)
        return label

    def short_folder(self, folder):
        parts = [part for part in folder.replace("/", "\\").split("\\") if part]
        if len(parts) <= 2:
            return folder
        return "...\\" + "\\".join(parts[-2:]) + "\\"

    def select_row(self, row, group_rows):
        self.current_row = row
        self.current_rows = group_rows
        self.current_group_id = row.get("grupo_id")
        for file_id, widget in self.row_widgets.items():
            if file_id == row.get("id"):
                widget.setObjectName("SelectedFileRow")
            elif not os.path.exists((self.rows_by_id.get(file_id) or {}).get("ruta") or ""):
                widget.setObjectName("MissingFileRow")
            else:
                widget.setObjectName("FileRow")
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.status.setText(row.get("ruta") or "")

    def clear_selection(self):
        self.current_row = None
        self.status.setText("Selection cleared")

    def selected_file_rows(self):
        return [self.current_row] if self.current_row else []

    def selected_playback_path(self):
        rows = self.selected_file_rows()
        if not rows:
            return None
        row = rows[0]
        if (row.get("decision") or "") in ("deleted", "missing"):
            return None
        path = row.get("ruta")
        return path if path and os.path.exists(path) else None

    def set_row_state(self, row, group_rows, decision):
        self.current_row = row
        self.current_rows = group_rows
        self.current_group_id = row.get("grupo_id")
        self.set_selected_file_state(decision)

    def set_selected_file_state(self, decision):
        rows = self.selected_file_rows()
        if not rows:
            QMessageBox.information(self, "State", "Select file row first.")
            return
        undo_rows = self.current_rows if decision == "master" and self.current_rows else rows
        self.undo_stack.push("state", undo_rows)
        with open_conn(self.db_path_getter()) as conn:
            if decision == "master" and self.current_rows:
                for group_row in self.current_rows:
                    if group_row.get("id") not in {row.get("id") for row in rows} and (group_row.get("decision") or "") == "master":
                        save_decision(conn, group_row["id"], "")
                        group_row["decision"] = ""
            for row in rows:
                save_decision(conn, row["id"], decision)
                row["decision"] = decision
        self.refresh()
        self.status.setText(f"Updated {len(rows)} file state.")

    def recycle_selected_files_direct(self):
        rows = [
            row for row in self.selected_file_rows()
            if os.path.exists(row.get("ruta") or "") and (row.get("decision") or "") not in ("deleted", "missing")
        ]
        if not rows:
            QMessageBox.information(self, "Recycle", "Select existing file row first.")
            return
        self.undo_stack.push("delete", rows)
        errors = []
        changed = 0
        with open_conn(self.db_path_getter()) as conn:
            for row in rows:
                try:
                    send_to_recycle_bin(row["ruta"])
                    save_decision(conn, row["id"], "deleted")
                    row["decision"] = "deleted"
                    changed += 1
                except FileActionError as exc:
                    errors.append(f"{row['ruta']}: {exc}")
        self.refresh()
        if errors:
            QMessageBox.critical(self, "Recycle errors", "\n".join(errors[:10]))
        self.status.setText(f"Sent {changed} file to Recycle Bin.")

    def undo_last_action(self):
        item = self.undo_stack.pop()
        if not item:
            self.status.setText("Nothing to undo.")
            return
        restored = 0
        blocked = 0
        with open_conn(self.db_path_getter()) as conn:
            for state in item["rows"]:
                if item["action"] == "delete" and not os.path.exists(state.get("path", "")):
                    save_decision(conn, state["id"], "deleted")
                    blocked += 1
                    continue
                save_decision(conn, state["id"], state["decision"])
                restored += 1
        self.refresh()
        self.status.setText(f"Undo restored {restored}; {blocked} still in Recycle Bin.")

    def apply_loaded_page(self):
        if self.all_files_mode:
            QMessageBox.information(self, "Apply", "All mode shows search files. Choose a duplicate match method before applying duplicate actions.")
            return
        if not self.loaded_group_ids:
            QMessageBox.information(self, "Apply", "No loaded groups.")
            return
        self.apply_group_ids(self.loaded_group_ids, "loaded page")

    def apply_group_ids(self, group_ids, scope_label):
        delete_by_id = {}
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                for row in duplicate_group_rows(conn, group_id, "hash"):
                    if (row.get("decision") or "") == "delete":
                        delete_by_id[row["id"]] = row
        deletes = [row for row in delete_by_id.values() if os.path.exists(row.get("ruta") or "")]
        if not deletes:
            QMessageBox.information(self, "Apply", f"No existing files marked Trash in {scope_label}.")
            return
        preview = "\n".join(row["ruta"] for row in deletes[:8])
        if len(deletes) > 8:
            preview += f"\n... and {len(deletes) - 8} more"
        answer = QMessageBox.question(
            self,
            "Delete confirmation",
            f"Apply scope: {scope_label}\nSend {len(deletes)} file(s) to Recycle Bin?\n\n{preview}\n\nNo permanent delete will be used.",
        )
        if answer != QMessageBox.Yes:
            return
        errors = []
        changed = 0
        with open_conn(self.db_path_getter()) as conn:
            for row in deletes:
                try:
                    send_to_recycle_bin(row["ruta"])
                    save_decision(conn, row["id"], "deleted")
                    changed += 1
                except FileActionError as exc:
                    errors.append(f"{row['ruta']}: {exc}")
        self.refresh()
        if errors:
            QMessageBox.critical(self, "Apply errors", "\n".join(errors[:10]))
        self.status.setText(f"Sent {changed} file(s) to Recycle Bin.")

    def reset_loaded_page(self):
        if self.all_files_mode:
            QMessageBox.information(self, "Reset", "All mode shows search files. Choose a duplicate match method before resetting loaded groups.")
            return
        if not self.loaded_group_ids:
            QMessageBox.information(self, "Reset", "No loaded groups.")
            return
        self.reset_group_ids(self.loaded_group_ids, "loaded page")

    def reset_group_ids(self, group_ids, scope_label):
        rows_by_id = {}
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                for row in duplicate_group_rows(conn, group_id, "hash"):
                    if (row.get("decision") or "") in ("master", "delete", "protected", "ignored"):
                        rows_by_id[row["id"]] = row
            if not rows_by_id:
                QMessageBox.information(self, "Reset", f"No review choices to reset in {scope_label}.")
                return
            for file_id in rows_by_id:
                save_decision(conn, file_id, "")
        self.refresh()
        self.status.setText(f"Reset {len(rows_by_id)} review choice(s) in {scope_label}.")

    def apply_rule_scope(self, scope_label):
        if self.all_files_mode:
            QMessageBox.information(self, "Rules", "All mode does not use duplicate groups.")
            return
        group_ids = self.loaded_group_ids[:] if scope_label == "loaded page" else []
        if not group_ids:
            QMessageBox.information(self, "Rules", f"No groups in {scope_label}.")
            return
        rule = self.rule.currentData()
        answer = QMessageBox.question(
            self,
            "Rules",
            f"Apply rule to {len(group_ids)} group(s)?\n\nRule: {rule_label(rule)}\nScope: {scope_label}\n\nFiles are not moved until Apply.",
        )
        if answer != QMessageBox.Yes:
            return
        groups = []
        with open_conn(self.db_path_getter()) as conn:
            for group_id in group_ids:
                rows = duplicate_group_rows(conn, group_id, "hash")
                if len(rows) >= 2:
                    groups.append(rows)
            decision_updates, changed = apply_rule_to_groups(groups, rule)
            save_decisions_bulk(conn, decision_updates)
        self.refresh()
        self.status.setText(f"Rule applied to {len(groups)} group(s): {changed} choice(s) changed.")
