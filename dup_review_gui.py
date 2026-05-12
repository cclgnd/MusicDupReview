#!/usr/bin/env python3
"""
Duplicate Review GUI - Warm Espresso theme.
All groups in one scrollable page.
"""
import os
import sys
import json
import shutil
import sqlite3
import threading
import time
import re
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
from database_maintenance import verify_database_files as verify_database_file_availability
from db_repository import (
    all_duplicate_group_ids,
    create_folder_clone_group,
    duplicate_extensions,
    duplicate_group_ids,
    duplicate_group_rows,
    duplicate_groups_for_ids,
    ensure_schema,
    filtered_duplicate_totals,
    group_has_missing_or_deleted,
    group_ids_for_file_ids,
    rows_marked_for_trash,
)
from duplicate_detection import detect_duplicates
from duplicate_rules import apply_rule_to_groups, overlap_file_count, rule_label
from file_actions import send_to_recycle_bin
from media_utils import (
    IMAGE_EXTS,
    audio_md5_file,
    category_for_extension,
    image_fingerprint,
    md5_file,
)
from playback_service import PlaybackService
from review_state import (
    TRANSIENT_DECISIONS,
    clear_transient_decisions,
    recover_session_snapshot,
    save_decision,
    save_decisions_bulk,
    save_session_snapshot,
)
from undo_service import UndoStack

try:
    from PIL import Image, ImageTk
    IMAGE_OK = True
except Exception:
    IMAGE_OK = False

APP_DIR = Path(__file__).resolve().parent
DB = str(APP_DIR / "music_library.db")
APP_VERSION = "folder-merge-v2"
SETTINGS_FILE = str(APP_DIR / "dup_review_settings.json")
MATCH_FILTERS = [
    ("All", "all"),
    ("Exact file", "md5"),
    ("Same audio", "audio_md5"),
    ("Same image", "image_ahash"),
    ("Same name + size", "nombre_tamano"),
    ("Similar name", "nombre_normalizado"),
    ("Exact filename", "nombre_identico"),
]
MATCH_LABEL_BY_VALUE = {value: label for label, value in MATCH_FILTERS}
MATCH_VALUE_BY_LABEL = {label: value for label, value in MATCH_FILTERS}

# ===== Compact blue-black prototype palette =====
BG_DEEP    = "#0a0a10"
BG_BASE    = "#13131a"
BG_CARD    = "#1a1a24"
BG_CARD_HI = "#22222e"
BG_HEADER  = "#0d0d12"
BG_GROUP   = "#1a1a24"

FG_TEXT    = "#d4d4dc"
FG_MUTED   = "#888894"
FG_HINT    = "#555560"

ACCENT_AMBER    = "#e07b39"
ACCENT_AMBER_BG = "#2a1608"
ACCENT_SAGE     = "#34c478"
ACCENT_SAGE_BG  = "#062218"
ACCENT_TAN      = "#b0b0bc"
ACCENT_TAN_BG   = "#1e1e28"
ACCENT_BORDER   = "#252530"
ACCENT_DIVIDER  = "#1e1e28"
MD5_COLORS       = ["#6ea8fe", "#e07b39", "#34c478", "#e06090", "#c4a7ff", "#e3cf86"]
AUDIO_MD5_COLORS = ["#3b5bdb", "#8fd0c0", "#a9c7f0", "#9fd89f", "#d2b6e8", "#b8d8d8"]
HASH_SAME_DOT    = "#34c478"
HASH_DIFF_DOT    = "#e07b39"
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

# selection + missing
SELECT_BORDER   = "#3b5bdb"
SELECT_BG       = "#0e2040"
MISSING_FG      = "#e06060"
MISSING_BG      = "#2a1116"
MISSING_BORDER  = "#9b3030"

FONT_UI       = ("Segoe UI", 8)
FONT_UI_MED   = ("Segoe UI", 8, "bold")
FONT_UI_STRONG = ("Segoe UI", 9, "bold")
FONT_META     = ("Consolas", 7)
FONT_META_MED = ("Consolas", 8, "bold")
FONT_BASE_SIZES = {
    "ui": 8,
    "ui_strong": 9,
    "meta": 7,
    "meta_med": 8,
}

ROW_PAD_X = 12
ROW_PAD_Y = 7
CHIP_PAD_X = 5

TYPE_FILTERS = ["ALL", ".mp3", ".flp", ".wav", ".pkf"]
GROUP_SORT_SEGMENTS = [
    ("Biggest", "biggest file"),
    ("Name", "name"),
    ("Date", "date"),
]
DECISION_LABELS = {
    "": "Unreviewed",
    "keep": "Keep",
    "master": "Keep",
    "protected": "Protected",
    "delete": "Trash",
    "ignored": "Ignored",
    "deleted": "Deleted",
    "missing": "Missing",
}
DEFAULT_STATE_SHORTCUTS = {
    "keep": "k",
    "trash": "t",
    "protected": "p",
    "ignored": "i",
    "unreviewed": "u",
}
STATE_SHORTCUT_TO_DECISION = {
    "keep": "master",
    "trash": "delete",
    "protected": "protected",
    "ignored": "ignored",
    "unreviewed": "",
}


class DupReviewApp:
    def __init__(self, root):
        self.root = root
        self.settings = self._load_settings()
        self.db_path = self.settings.get("db_path", DB)
        self.root.title(f"Duplicate Review - {APP_VERSION} - {os.path.basename(self.db_path)}")
        self.root.geometry(self.settings.get("geometry", "1500x900"))
        self.root.configure(bg=BG_DEEP)
        if self.settings.get("zoomed", True):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_decisions_table()
        self._clear_transient_decisions_on_startup()

        saved_filter = self.settings.get("filter_type", "audio_md5")
        if saved_filter == "image_size":
            saved_filter = "all"
        if saved_filter == "nombre_exacto":
            saved_filter = "nombre_normalizado"
        self.filter_type   = tk.StringVar(value=saved_filter)
        self.match_filter_label = tk.StringVar(
            value=MATCH_LABEL_BY_VALUE.get(saved_filter, "Same audio")
        )
        self.extension_filter = tk.StringVar(value=self.settings.get("extension_filter", "ALL"))
        self.group_sort = tk.StringVar(value=self.settings.get("group_sort", "group_id"))
        self.row_sort = tk.StringVar(value=self.settings.get("row_sort", "hash + biggest"))
        self.hide_incomplete = tk.BooleanVar(value=self.settings.get("hide_incomplete", False))
        self.search_text   = tk.StringVar()
        self.page_size     = 50
        self.playing_row   = None   # currently playing row (or None)
        self.confirm_deletes = tk.BooleanVar(value=self._bool_setting("confirm_deletes", True))
        self.state_shortcuts = dict(DEFAULT_STATE_SHORTCUTS)
        self.state_shortcuts.update(self.settings.get("state_shortcuts", {}))
        self._normalize_state_shortcuts()
        self.page_index    = 0
        self.group_ids     = []
        self.row_widgets   = []   # list of (row_dict, outer_frame)
        self.undo_stack    = UndoStack(maxlen=400)
        self.folder_clone_count_cache = {}
        self.highlight_group_id = None
        self.playback_after = None
        self.playback_duration = 0.0
        self.playback_seek_offset = 0.0
        self.playback_dragging = False
        self.playback_last_seek = 0.0
        self.playback = PlaybackService()
        self.playback_progress = tk.DoubleVar(value=0.0)
        self.playback_time = tk.StringVar(value="00:00")
        self.playback_current_time = tk.StringVar(value="00:00")
        self.playback_total_time = tk.StringVar(value="00:00")
        self.playback_info = tk.StringVar(value="No audio")
        self.playback_file = tk.StringVar(value="")
        self.image_viewer = None
        self.image_viewer_path = None
        self.image_refs = []
        self.text_scale = tk.IntVar(value=int(self.settings.get("text_scale", 0)))
        self._font_refresh_after = None
        self._init_fonts()

        self._setup_styles()
        self._build_ui()
        self._load_groups()

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self):
        try:
            self.settings["db_path"] = self.db_path
            self.settings["geometry"] = self.root.geometry()
            self.settings["zoomed"] = self.root.state() == "zoomed"
            self.settings["filter_type"] = self.filter_type.get()
            self.settings["extension_filter"] = self.extension_filter.get()
            self.settings["group_sort"] = self.group_sort.get()
            self.settings["row_sort"] = self.row_sort.get()
            self.settings["hide_incomplete"] = self.hide_incomplete.get()
            self.settings["confirm_deletes"] = self.confirm_deletes.get()
            self.settings["state_shortcuts"] = self.state_shortcuts
            self.settings["text_scale"] = self.text_scale.get()
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _bool_setting(self, key, default):
        value = self.settings.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("1", "true", "yes", "on"):
                return True
            if normalized in ("0", "false", "no", "off"):
                return False
        return default

    def _normalize_state_shortcuts(self):
        reserved = {"d", "r", " "}
        normalized = {}
        used = set()
        for action, default in DEFAULT_STATE_SHORTCUTS.items():
            value = str(self.state_shortcuts.get(action, default) or default).strip().lower()[:1]
            if not value or value in reserved or value in used:
                value = default
            if value in reserved or value in used:
                value = ""
            normalized[action] = value
            if value:
                used.add(value)
        self.state_shortcuts = normalized

    def _init_fonts(self):
        global FONT_UI, FONT_UI_MED, FONT_UI_STRONG, FONT_META, FONT_META_MED
        step = max(0, min(10, int(self.text_scale.get())))
        FONT_UI = tkfont.Font(family="Segoe UI", size=FONT_BASE_SIZES["ui"] + step)
        FONT_UI_MED = tkfont.Font(family="Segoe UI", size=FONT_BASE_SIZES["ui"] + step, weight="bold")
        FONT_UI_STRONG = tkfont.Font(family="Segoe UI", size=FONT_BASE_SIZES["ui_strong"] + step, weight="bold")
        FONT_META = tkfont.Font(family="Consolas", size=FONT_BASE_SIZES["meta"] + step)
        FONT_META_MED = tkfont.Font(family="Consolas", size=FONT_BASE_SIZES["meta_med"] + step, weight="bold")

    def _apply_text_scale(self, value=None):
        step = max(0, min(10, int(float(value if value is not None else self.text_scale.get()))))
        self.text_scale.set(step)
        FONT_UI.configure(size=FONT_BASE_SIZES["ui"] + step)
        FONT_UI_MED.configure(size=FONT_BASE_SIZES["ui"] + step)
        FONT_UI_STRONG.configure(size=FONT_BASE_SIZES["ui_strong"] + step)
        FONT_META.configure(size=FONT_BASE_SIZES["meta"] + step)
        FONT_META_MED.configure(size=FONT_BASE_SIZES["meta_med"] + step)
        self._setup_styles()
        self._save_settings()
        if self._font_refresh_after:
            try:
                self.root.after_cancel(self._font_refresh_after)
            except Exception:
                pass
        self._font_refresh_after = self.root.after(180, self._refresh_after_font_change)

    def _refresh_after_font_change(self):
        self._font_refresh_after = None
        self._load_groups()

    def _on_close(self):
        self._save_settings()
        try:
            self._save_session_decision_snapshot()
            self.stop_audio()
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()

    def _ensure_decisions_table(self):
        ensure_schema(self.conn)

    def _transient_decisions(self):
        return TRANSIENT_DECISIONS

    def _clear_transient_decisions_on_startup(self):
        clear_transient_decisions(self.conn)

    def _save_session_decision_snapshot(self):
        save_session_snapshot(self.conn)

    def recover_last_session_state(self):
        if not messagebox.askyesno(
            "Recover last session state",
            "Restore staged review choices from the last closed session?\n\n"
            "This does not move files and does not undo Deleted or Missing states."
        ):
            return

        restored = recover_session_snapshot(self.conn)
        self.status.config(text=f"Recovered {restored} review choice(s) from last session")
        self._load_groups()

    def _setup_styles(self):
        s = ttk.Style()
        try:
            s.theme_use('clam')
        except Exception:
            pass

        s.configure('.',
                    background=BG_BASE, foreground=FG_TEXT,
                    fieldbackground=BG_CARD, bordercolor=ACCENT_BORDER,
                    lightcolor=BG_CARD, darkcolor=BG_BASE,
                    troughcolor=BG_DEEP, insertcolor=FG_TEXT,
                    selectbackground=BG_CARD_HI, selectforeground=FG_TEXT,
                    font=FONT_UI)

        s.configure('TFrame', background=BG_BASE)
        s.configure('Top.TFrame', background=BG_HEADER)

        s.configure('TLabel', background=BG_BASE, foreground=FG_TEXT)
        s.configure('Top.TLabel', background=BG_HEADER, foreground=FG_TEXT)
        s.configure('Title.TLabel', background=BG_HEADER, foreground=ACCENT_TAN,
                    font=FONT_UI_STRONG)
        s.configure('Status.TLabel', background=BG_HEADER, foreground=FG_MUTED,
                    relief='flat', padding=(7, 3), font=FONT_UI)
        s.configure('Top.TLabel', background=BG_HEADER, foreground=FG_TEXT,
                    font=FONT_UI)

        s.configure('TButton',
                    background=BG_CARD, foreground=FG_TEXT,
                    bordercolor=ACCENT_BORDER, focuscolor=BG_CARD_HI,
                    relief='flat', padding=(7, 3), font=FONT_UI)
        s.map('TButton',
              background=[('active', BG_CARD_HI), ('pressed', BG_HEADER)],
              foreground=[('active', FG_TEXT)])

        s.configure('Amber.TButton',
                    background=ACCENT_AMBER_BG, foreground=ACCENT_AMBER,
                    bordercolor=ACCENT_AMBER, padding=(9, 3), font=FONT_UI_MED)
        s.map('Amber.TButton',
              background=[('active', ACCENT_AMBER), ('pressed', ACCENT_AMBER_BG)],
              foreground=[('active', BG_DEEP)])

        s.configure('Sage.TButton',
                    background="#3b5bdb", foreground="#ffffff",
                    bordercolor="#3b5bdb", padding=(9, 3), font=FONT_UI_MED)
        s.map('Sage.TButton',
              background=[('active', ACCENT_SAGE), ('pressed', ACCENT_SAGE_BG)],
              foreground=[('active', BG_DEEP)])

        s.configure('Card.TButton',
                    background=BG_CARD, foreground=FG_MUTED, padding=(5, 2), font=FONT_UI)
        s.map('Card.TButton',
              background=[('active', BG_CARD_HI)],
              foreground=[('active', FG_TEXT)])

        s.configure('TCombobox',
                    fieldbackground=BG_CARD, background=BG_CARD,
                    foreground=FG_TEXT, arrowcolor=ACCENT_TAN,
                    bordercolor=ACCENT_BORDER,
                    selectbackground=BG_CARD_HI, selectforeground=FG_TEXT,
                    font=FONT_UI)
        s.configure('TMenubutton',
                    background=BG_CARD, foreground=FG_MUTED,
                    bordercolor=ACCENT_BORDER, padding=(7, 3),
                    font=FONT_UI)
        s.map('TCombobox',
              fieldbackground=[('readonly', BG_CARD)],
              foreground=[('readonly', FG_TEXT)])

        s.configure('TEntry',
                    fieldbackground=BG_CARD, foreground=FG_TEXT,
                    bordercolor=ACCENT_BORDER, insertcolor=FG_TEXT,
                    font=FONT_UI)

        s.configure('TRadiobutton', background=BG_HEADER, foreground=FG_TEXT,
                    indicatorcolor=BG_CARD)
        s.map('TRadiobutton',
              background=[('active', BG_HEADER)],
              foreground=[('active', ACCENT_TAN), ('selected', ACCENT_TAN)])
        s.configure('TCheckbutton', background=BG_HEADER, foreground=FG_TEXT,
                    indicatorcolor=BG_CARD)
        s.map('TCheckbutton',
              background=[('active', BG_HEADER)],
              foreground=[('active', ACCENT_SAGE), ('selected', ACCENT_SAGE)])

        s.configure('Vertical.TScrollbar',
                    background=BG_CARD, troughcolor=BG_DEEP,
                    bordercolor=BG_DEEP, arrowcolor=FG_MUTED, relief='flat')

    def _return_focus_to_root(self):
        self.root.after_idle(self.root.focus_set)

    def _ui_command(self, callback):
        def wrapped():
            try:
                return callback()
            finally:
                self._return_focus_to_root()
        return wrapped

    def _button(self, parent, text, command=None, bg=BG_CARD, fg=FG_MUTED,
                active_bg=BG_CARD_HI, active_fg=FG_TEXT, font=FONT_UI,
                padx=10, pady=4, width=None):
        btn = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=active_bg, activeforeground=active_fg,
            bd=1, relief=tk.SOLID, highlightthickness=0,
            font=font, padx=padx, pady=pady, cursor="hand2",
            takefocus=0
        )
        if width is not None:
            btn.configure(width=width)
        return btn

    def _segmented_button(self, parent, text, is_on, command, rounded=False):
        bg = "#3b5bdb" if is_on and rounded else (BG_CARD_HI if is_on else BG_CARD)
        fg = "#ffffff" if is_on and rounded else (FG_TEXT if is_on else FG_HINT)
        return self._button(parent, text, command=command, bg=bg, fg=fg,
                            active_bg=BG_CARD_HI, active_fg=FG_TEXT,
                            font=FONT_UI, padx=10, pady=3)

    def _build_segmented(self, parent, items, current, setter, rounded=False):
        wrap = tk.Frame(parent, bg=BG_CARD, highlightbackground=ACCENT_BORDER,
                        highlightthickness=1, bd=0)
        buttons = []
        for label, value in items:
            btn = self._segmented_button(
                wrap, label, current == value,
                lambda v=value: setter(v), rounded=rounded
            )
            btn.pack(side=tk.LEFT)
            buttons.append((btn, label, value, rounded))
        return wrap, buttons

    def _refresh_segmented_buttons(self, buttons, current):
        for btn, _label, value, rounded in buttons:
            is_on = current == value
            if rounded and is_on:
                btn.config(bg="#3b5bdb", fg="#ffffff")
            elif is_on:
                btn.config(bg=BG_CARD_HI, fg=FG_TEXT)
            else:
                btn.config(bg=BG_CARD, fg=FG_HINT)

    def _make_chip(self, parent, text, bg=BG_CARD, fg=FG_HINT, border=ACCENT_BORDER,
                   font=FONT_META, padx=CHIP_PAD_X):
        chip = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                        padx=padx, pady=1, bd=1, relief=tk.SOLID,
                        highlightbackground=border, highlightthickness=0)
        return chip

    def _popup_comment(self, widget, text, wrap=320):
        widget._popup_text = text
        widget._popup_wrap = wrap
        widget.bind("<Enter>", lambda e, w=widget: self._show_popup_comment(w, e))
        widget.bind("<Leave>", lambda e, w=widget: self._hide_popup_comment(w))
        widget.bind("<Button-1>", lambda e, w=widget: self._toggle_popup_comment(w, e), add="+")

    def _show_popup_comment(self, widget, event=None):
        self._hide_popup_comment(widget)
        text = getattr(widget, "_popup_text", "")
        if not text:
            return
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.configure(bg=ACCENT_BORDER)
        label = tk.Label(
            popup, text=text, justify=tk.LEFT, bg=BG_HEADER, fg=FG_TEXT,
            font=FONT_UI, padx=9, pady=7,
            wraplength=getattr(widget, "_popup_wrap", 320)
        )
        label.pack(padx=1, pady=1)
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        popup.wm_geometry(f"+{x}+{y}")
        widget._popup_window = popup

    def _hide_popup_comment(self, widget):
        popup = getattr(widget, "_popup_window", None)
        if popup:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            widget._popup_window = None

    def _toggle_popup_comment(self, widget, event=None):
        if getattr(widget, "_popup_window", None):
            self._hide_popup_comment(widget)
        else:
            self._show_popup_comment(widget, event)

    def _build_expandable_box(self, parent, title, details_getter, popup_comment=None):
        box = tk.Frame(parent, bg=BG_CARD, highlightbackground=ACCENT_BORDER,
                       highlightthickness=1, bd=0)
        header = tk.Frame(box, bg=BG_CARD)
        header.pack(fill=tk.X)

        state = {"open": False}
        details = tk.Label(box, text="", bg=BG_HEADER, fg=FG_MUTED,
                           justify=tk.LEFT, anchor="w", font=FONT_UI,
                           padx=9, pady=7, wraplength=360)

        def toggle():
            state["open"] = not state["open"]
            box._expanded = state["open"]
            title_btn.config(text=("- " if state["open"] else "+ ") + title)
            if state["open"]:
                details.config(text=details_getter() if callable(details_getter) else str(details_getter))
                details.pack(fill=tk.X)
            else:
                details.pack_forget()

        title_btn = self._button(header, "+ " + title, command=toggle,
                                 bg=BG_CARD, fg=FG_MUTED, active_bg=BG_CARD_HI,
                                 active_fg=FG_TEXT, font=FONT_UI, padx=8, pady=3)
        title_btn.pack(side=tk.LEFT)
        comment_btn = self._button(header, "?", bg=BG_CARD, fg=FG_HINT,
                                   active_bg=BG_CARD_HI, active_fg=FG_TEXT,
                                   font=FONT_UI_MED, padx=6, pady=3)
        comment_btn.pack(side=tk.LEFT)
        if popup_comment:
            self._popup_comment(comment_btn, popup_comment)
        box._details_label = details
        box._details_getter = details_getter
        box._expanded = False
        return box

    def _refresh_expandable_boxes(self):
        for box in getattr(self, "_expandable_boxes", []):
            if getattr(box, "_expanded", False):
                getter = getattr(box, "_details_getter", None)
                label = getattr(box, "_details_label", None)
                if getter and label:
                    label.config(text=getter() if callable(getter) else str(getter))

    def _short_hash(self, value, label=""):
        if not value:
            return ""
        prefix = f"{label} " if label else ""
        if len(value) <= 16:
            return prefix + value
        return f"{prefix}{value[:8]}...{value[-4:]}"

    def _short_folder(self, folder, max_parts=2):
        if not folder:
            return ""
        parts = [p for p in re.split(r"[\\/]+", folder) if p]
        if len(parts) <= max_parts:
            return folder
        return "..." + "\\" + "\\".join(parts[-max_parts:]) + "\\"

    def _set_group_sort(self, value):
        self.group_sort.set(value)
        if hasattr(self, "group_sort_buttons"):
            self._refresh_segmented_buttons(self.group_sort_buttons, value)
        self._on_filter_change()

    def _set_decision(self, row, decision):
        row['_decision_var'].set(decision)
        self._on_decision_change(row)

    def _filter_details_text(self):
        search = self.search_text.get().strip() or "none"
        ext = self.extension_filter.get() or "ALL"
        match = self.match_filter_label.get()
        sort = next((label for label, value in GROUP_SORT_SEGMENTS
                     if value == self.group_sort.get()), self.group_sort.get())
        hidden = "on" if self.hide_incomplete.get() else "off"
        confirm = "on" if self.confirm_deletes.get() else "off"
        return (
            f"Match: {match}\n"
            f"Extension: {ext}\n"
            f"Search: {search}\n"
            f"Group sort: {sort}\n"
            f"Hide deleted/missing: {hidden}\n"
            f"Visible results: {len(getattr(self, 'group_ids', [])):,} groups"
        )

    def _preferences_text(self):
        confirm = "on" if self.confirm_deletes.get() else "off"
        hidden = "on" if self.hide_incomplete.get() else "off"
        return (
            f"Delete confirmation: {confirm}\n"
            f"Hide missing/deleted groups: {hidden}\n"
            f"Text scale: {self.text_scale.get()}"
        )

    def _toggle_hide_deleted(self):
        self.hide_incomplete.set(not self.hide_incomplete.get())
        self._refresh_toggle_buttons()
        self._on_filter_change()

    def _toggle_confirm_deletes(self):
        self.confirm_deletes.set(not self.confirm_deletes.get())
        self._refresh_toggle_buttons()
        self._save_settings()
        self._refresh_expandable_boxes()

    def _refresh_toggle_buttons(self):
        if hasattr(self, "hide_button"):
            self.hide_button.config(
                text=f"Hide missing/deleted groups: {'On' if self.hide_incomplete.get() else 'Off'}",
                bg=BG_CARD_HI if self.hide_incomplete.get() else BG_CARD,
                fg=FG_TEXT if self.hide_incomplete.get() else FG_MUTED
            )
        if hasattr(self, "confirm_button"):
            self.confirm_button.config(
                text=f"Delete confirmation: {'On' if self.confirm_deletes.get() else 'Off'}",
                bg=BG_CARD_HI if self.confirm_deletes.get() else BG_CARD,
                fg=FG_TEXT if self.confirm_deletes.get() else FG_MUTED
            )

    def _build_preferences_box(self, parent):
        box = tk.Frame(parent, bg=BG_CARD, highlightbackground=ACCENT_BORDER,
                       highlightthickness=1, bd=0)
        header = tk.Frame(box, bg=BG_CARD)
        header.pack(fill=tk.X)
        content = tk.Frame(box, bg=BG_HEADER, padx=9, pady=7)
        state = {"open": False}

        def toggle():
            state["open"] = not state["open"]
            box._expanded = state["open"]
            title_btn.config(text=("- " if state["open"] else "+ ") + "Preferences")
            if state["open"]:
                content.pack(fill=tk.X)
            else:
                content.pack_forget()

        title_btn = self._button(header, "+ Preferences", command=toggle,
                                 bg=BG_CARD, fg=FG_MUTED, active_bg=BG_CARD_HI,
                                 active_fg=FG_TEXT, font=FONT_UI, padx=8, pady=3)
        title_btn.pack(side=tk.LEFT)

        self.confirm_button = self._button(
            content, "Delete confirmation: On", command=self._ui_command(self._toggle_confirm_deletes),
            bg=BG_CARD, fg=FG_MUTED, padx=9, pady=3
        )
        self.confirm_button.pack(fill=tk.X, pady=(0, 5))
        self._popup_comment(
            self.confirm_button,
            "Delete confirmation: asks before trash/apply operations. Permanent delete is never used."
        )

        self.hide_button = self._button(
            content, "Hide missing/deleted groups", command=self._ui_command(self._toggle_hide_deleted),
            bg=BG_CARD, fg=FG_MUTED, padx=9, pady=3
        )
        self.hide_button.pack(fill=tk.X)
        self._popup_comment(
            self.hide_button,
            "Hide missing/deleted groups: removes groups that contain missing files or rows already marked as deleted."
        )

        return box

    # ---------- UI ----------
    def _build_ui(self):
        self._build_menu()

        toolbar = tk.Frame(self.root, bg=BG_HEADER, padx=14, pady=9)
        toolbar.pack(fill=tk.X)

        left = tk.Frame(toolbar, bg=BG_HEADER)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        right = tk.Frame(toolbar, bg=BG_HEADER)
        right.pack(side=tk.RIGHT)

        type_items = [("All" if label == "ALL" else label, label) for label in TYPE_FILTERS]
        type_wrap, self.extension_buttons = self._build_segmented(
            left, type_items, self.extension_filter.get(), self._set_extension_filter, rounded=True
        )
        self.extension_segment = type_wrap
        self.extension_values = TYPE_FILTERS[:]
        type_wrap.pack(side=tk.LEFT, padx=(0, 8))
        self._popup_comment(
            type_wrap,
            "Extension filter: limits duplicate groups to groups that still have at least two files with the selected extension. Extra extensions live under More."
        )

        current_sort = self.group_sort.get()
        if current_sort not in {value for _, value in GROUP_SORT_SEGMENTS}:
            current_sort = "biggest file"
            self.group_sort.set(current_sort)
        sort_wrap, self.group_sort_buttons = self._build_segmented(
            left, GROUP_SORT_SEGMENTS, current_sort, self._set_group_sort
        )
        sort_wrap.pack(side=tk.LEFT, padx=(0, 8))
        self._popup_comment(
            sort_wrap,
            "Group sort: Biggest orders by the largest file in each group; Name orders by the first filename; Date orders by newest modified file."
        )

        self.match_button = tk.Menubutton(
            left, text=self.match_filter_label.get(), bg=BG_CARD, fg=FG_MUTED,
            activebackground=BG_CARD_HI, activeforeground=FG_TEXT,
            bd=1, relief=tk.SOLID, font=FONT_UI, padx=10, pady=3,
            cursor="hand2", takefocus=0
        )
        match_menu = tk.Menu(self.match_button, tearoff=0, bg=BG_HEADER, fg=FG_MUTED,
                             activebackground=BG_CARD, activeforeground=FG_TEXT,
                             font=FONT_UI)
        for label, _value in MATCH_FILTERS:
            match_menu.add_command(label=label, command=lambda l=label: self._set_match_filter(l))
        self.match_button["menu"] = match_menu
        self.match_button.pack(side=tk.LEFT, padx=(0, 8))
        self._popup_comment(
            self.match_button,
            "Match filter: chooses the duplicate-detection layer, such as exact file hash, same audio hash, same image, or similar filename."
        )

        search_wrap = tk.Frame(left, bg=BG_CARD, padx=8, pady=3,
                               highlightbackground=ACCENT_BORDER, highlightthickness=1)
        search_wrap.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(search_wrap, text="Search", bg=BG_CARD, fg=FG_HINT,
                 font=FONT_UI).pack(side=tk.LEFT, padx=(0, 6))
        e = tk.Entry(search_wrap, textvariable=self.search_text, width=22,
                     bg=BG_CARD, fg=FG_TEXT, insertbackground=FG_TEXT,
                     relief=tk.FLAT, bd=0, font=FONT_UI)
        e.pack(side=tk.LEFT)
        e.bind('<KeyRelease>', lambda ev: self._on_filter_change())
        self._popup_comment(
            search_wrap,
            "Search filter: matches text inside the full file path and keeps groups where at least one file path matches."
        )

        filter_box = self._build_expandable_box(
            left,
            "Filter details",
            self._filter_details_text,
            "Click the box to expand a live summary of the active filters. Hover the other controls for focused comments."
        )
        filter_box.pack(side=tk.LEFT, padx=(0, 8))
        self._expandable_boxes = [filter_box]

        preferences_box = self._build_preferences_box(left)
        preferences_box.pack(side=tk.LEFT, padx=(0, 8))

        text_scale_box = tk.Frame(right, bg="#d7d7dc", padx=8, pady=3,
                                  highlightbackground="#f0f0f3", highlightthickness=1)
        text_scale_box.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(text_scale_box, text="Text", bg="#d7d7dc", fg="#202027",
                 font=FONT_UI_MED).pack(side=tk.LEFT, padx=(0, 7))
        self.text_scale_slider = tk.Scale(
            text_scale_box, from_=0, to=10, orient=tk.HORIZONTAL,
            variable=self.text_scale, command=self._apply_text_scale,
            length=120, showvalue=False, resolution=1,
            bg="#d7d7dc", fg="#202027", troughcolor="#8c8c96",
            activebackground="#f3f3f5", highlightthickness=0,
            sliderrelief=tk.FLAT, bd=0, width=12, takefocus=0
        )
        self.text_scale_slider.pack(side=tk.LEFT)
        self._popup_comment(
            text_scale_box,
            "Text size: base size at the far left. Move right to enlarge the whole interface up to 10 steps."
        )

        self._build_global_rules_menu(right).pack(side=tk.LEFT, padx=4)
        self._button(right, "Reset...",
                     command=self._ui_command(self.reset_review_choices),
                     bg=BG_HEADER, fg=FG_MUTED, padx=10, pady=3).pack(side=tk.LEFT, padx=4)
        self._button(right, "Apply...",
                     command=self._ui_command(self.apply_decisions),
                     bg="#c2580a", fg="#ffffff", active_bg=ACCENT_AMBER,
                     active_fg="#ffffff", font=FONT_UI_MED, padx=12, pady=3).pack(side=tk.LEFT, padx=4)
        self._refresh_toggle_buttons()

        summary = tk.Frame(self.root, bg=BG_HEADER, padx=14, pady=5,
                           highlightbackground=ACCENT_DIVIDER, highlightthickness=1)
        summary.pack(fill=tk.X)
        self.summary_label = tk.Label(summary, text="", bg=BG_HEADER, fg=FG_HINT,
                                      anchor="w", font=FONT_UI)
        self.summary_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.filtered_size_label = tk.Label(summary, text="", bg=BG_HEADER, fg=FG_HINT,
                                            anchor="center", font=FONT_UI)
        self.filtered_size_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.page_label = tk.Label(summary, text="", bg=BG_HEADER, fg=FG_HINT,
                                   anchor="e", font=FONT_UI)
        self.page_label.pack(side=tk.RIGHT, padx=(8, 0))
        self._button(summary, "Next", command=self._ui_command(self.next_page),
                     bg=BG_HEADER, fg=FG_MUTED, padx=8, pady=2).pack(side=tk.RIGHT, padx=2)
        self._button(summary, "Prev", command=self._ui_command(self.prev_page),
                     bg=BG_HEADER, fg=FG_MUTED, padx=8, pady=2).pack(side=tk.RIGHT, padx=2)
        # main scrollable area
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(outer, bg=BG_BASE, highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(outer, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.list_inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.list_inner,
                                  anchor="nw", tags="inner")
        self.list_inner.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig("inner", width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta/120), "units"))

        # Keyboard shortcuts
        self.root.bind_all("<KeyPress>", self._on_key)

        status_bar = tk.Frame(self.root, bg=BG_DEEP, highlightbackground=ACCENT_DIVIDER,
                              highlightthickness=1, padx=14, pady=8)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.playback_panel = tk.Frame(status_bar, bg=BG_DEEP)
        self.playback_panel.pack(side=tk.LEFT, fill=tk.X, expand=True)

        player_left = tk.Frame(self.playback_panel, bg=BG_DEEP, width=170)
        player_left.pack(side=tk.LEFT, fill=tk.Y)
        player_left.pack_propagate(False)

        self.playback_file_label = tk.Label(
            player_left, textvariable=self.playback_file,
            bg=BG_DEEP, fg=FG_TEXT, anchor="w",
            font=FONT_UI_STRONG)
        self.playback_file_label.pack(fill=tk.X)

        self.playback_info_label = tk.Label(
            player_left, textvariable=self.playback_info,
            bg=BG_DEEP, fg=FG_HINT, anchor="w",
            font=FONT_META)
        self.playback_info_label.pack(fill=tk.X)

        self.play_toggle_button = self._button(
            self.playback_panel, "Play", command=self._ui_command(self.toggle_selected_playback),
            bg=BG_CARD, fg=FG_MUTED, active_bg=BG_CARD_HI,
            active_fg=FG_TEXT, font=FONT_UI_MED, padx=12, pady=5, width=6
        )
        self.play_toggle_button.pack(side=tk.LEFT, padx=(10, 0))

        player_center = tk.Frame(self.playback_panel, bg=BG_DEEP)
        player_center.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 12))
        times = tk.Frame(player_center, bg=BG_DEEP)
        times.pack(fill=tk.X)
        tk.Label(times, textvariable=self.playback_current_time,
                 bg=BG_DEEP, fg=FG_HINT, font=FONT_META).pack(side=tk.LEFT)
        tk.Label(times, textvariable=self.playback_total_time,
                 bg=BG_DEEP, fg=FG_HINT, font=FONT_META).pack(side=tk.RIGHT)

        self.playback_canvas = tk.Canvas(player_center, height=14, bg=BG_DEEP,
                                         highlightthickness=0, bd=0)
        self.playback_canvas.pack(fill=tk.X)
        self.playback_canvas.bind("<Configure>", lambda e: self._draw_playback_bar())
        self.playback_canvas.bind("<ButtonPress-1>", self._on_seek_canvas_press)
        self.playback_canvas.bind("<B1-Motion>", self._on_seek_canvas_drag)
        self.playback_canvas.bind("<ButtonRelease-1>", self._on_seek_canvas_release)

        self.shortcut_panel = tk.Frame(status_bar, bg=BG_DEEP)
        self.shortcut_panel.pack(side=tk.RIGHT)
        self.hotkey_frame = tk.Frame(self.shortcut_panel, bg=BG_DEEP)
        self.hotkey_frame.pack(side=tk.LEFT)
        self._build_hotkey_pills()
        self.shortcut_config_button = tk.Button(
            self.shortcut_panel, text="?", command=self._show_shortcut_config,
            bg=BG_CARD, fg=FG_HINT, activebackground=BG_CARD_HI,
            activeforeground=FG_TEXT, bd=1, relief=tk.SOLID,
            font=('Segoe UI', 10), width=3)
        self.shortcut_config_button.pack(side=tk.LEFT, padx=(6, 0))
        self.status = tk.Label(self.shortcut_panel, text="", bg=BG_DEEP, fg=FG_HINT,
                               font=FONT_UI)
        status_bar.bind("<Configure>", self._resize_playback_slider)

    def _build_hotkey_pills(self):
        items = [
            (self.state_shortcuts.get("keep", "k").upper(), "Keep"),
            (self.state_shortcuts.get("trash", "t").upper(), "Trash"),
            (self.state_shortcuts.get("protected", "p").upper(), "Protect"),
            (self.state_shortcuts.get("ignored", "i").upper(), "Ignore"),
            ("D", "Recycle"),
            ("Space", "Play"),
            ("Esc", "Clear"),
        ]
        for key, text in items:
            pill = tk.Frame(self.hotkey_frame, bg=BG_CARD, highlightbackground=ACCENT_BORDER,
                            highlightthickness=1, padx=6, pady=3)
            pill.pack(side=tk.LEFT, padx=3)
            tk.Label(pill, text=key, bg="#111118", fg="#7a7a8c",
                     font=FONT_META, padx=4).pack(side=tk.LEFT)
            tk.Label(pill, text=text, bg=BG_CARD, fg=FG_HINT,
                     font=FONT_UI).pack(side=tk.LEFT, padx=(4, 0))

    def _refresh_hotkey_pills(self):
        for child in self.hotkey_frame.winfo_children():
            child.destroy()
        self._build_hotkey_pills()

    def _show_shortcut_config(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Keyboard shortcuts")
        dialog.configure(bg=BG_BASE)
        dialog.geometry("360x260")
        self._center_window(dialog, 360, 260)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="File state shortcuts",
                 bg=BG_BASE, fg=FG_TEXT, font=FONT_UI_STRONG,
                 padx=12, pady=10).pack(fill=tk.X)
        body = tk.Frame(dialog, bg=BG_BASE, padx=12, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        fields = {}
        labels = [
            ("keep", "Keep"),
            ("trash", "Trash"),
            ("protected", "Protected"),
            ("ignored", "Ignored"),
            ("unreviewed", "Unreviewed"),
        ]
        for idx, (key, label) in enumerate(labels):
            tk.Label(body, text=label, bg=BG_BASE, fg=FG_TEXT,
                     font=FONT_UI).grid(row=idx, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.state_shortcuts.get(key, DEFAULT_STATE_SHORTCUTS[key]).upper())
            entry = tk.Entry(body, textvariable=var, width=4,
                             bg=BG_CARD, fg=FG_TEXT, insertbackground=FG_TEXT,
                             relief=tk.FLAT, font=FONT_UI_MED)
            entry.grid(row=idx, column=1, sticky="w", padx=(10, 0), pady=4)
            fields[key] = var

        buttons = tk.Frame(dialog, bg=BG_BASE, padx=12, pady=10)
        buttons.pack(fill=tk.X)

        def save():
            next_map = {}
            used = set()
            for key, var in fields.items():
                value = (var.get() or "").strip().lower()
                if len(value) != 1 or value in used or value in {"d", "r", " "}:
                    messagebox.showerror(
                        "Keyboard shortcuts",
                        "Use one unique letter per state. D, R, and Space are reserved."
                    )
                    return
                used.add(value)
                next_map[key] = value
            self.state_shortcuts = next_map
            self._save_settings()
            self._refresh_hotkey_pills()
            dialog.destroy()

        self._button(buttons, "Save", command=save, bg=ACCENT_SAGE_BG,
                     fg=ACCENT_SAGE, padx=10, pady=4).pack(side=tk.RIGHT, padx=(6, 0))
        self._button(buttons, "Cancel", command=dialog.destroy,
                     bg=BG_CARD, fg=FG_MUTED, padx=10, pady=4).pack(side=tk.RIGHT)

    def _show_playback_panel(self):
        self.playback_panel.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _hide_playback_panel(self):
        self._draw_playback_bar()

    def _resize_playback_slider(self, event=None):
        self._draw_playback_bar()

    def _build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=0)
        new_menu = tk.Menu(file_menu, tearoff=0)
        new_menu.add_command(
            label="Exact duplicate search...",
            command=lambda: self.new_search_database(compute_audio_md5=False)
        )
        new_menu.add_command(
            label="Audio-only MD5 search...",
            command=lambda: self.new_search_database(compute_audio_md5=True)
        )
        file_menu.add_cascade(label="New search", menu=new_menu)
        file_menu.add_command(label="Open search...", command=self.open_database)
        file_menu.add_separator()
        file_menu.add_command(label="Check file availability", command=self.verify_database_files)
        file_menu.add_command(label="Recover last session state", command=self.recover_last_session_state)
        file_menu.add_command(label="Backup this search", command=self.backup_database)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu, tearoff=0)
        view_menu.add_command(label="Maximize now", command=lambda: self.root.state("zoomed"))
        menu.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menu)

    def backup_database(self):
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            src = Path(self.db_path)
            dest = src.with_name(f"{src.stem}_backup_{stamp}{src.suffix}")
            shutil.copy2(src, dest)
            messagebox.showinfo("Backup this search", f"Backup created:\n{dest}")
        except Exception as e:
            messagebox.showerror("Backup error", str(e))

    def verify_database_files(self):
        progress = tk.Toplevel(self.root)
        progress.title("Checking files")
        progress.configure(bg=BG_BASE)
        progress.geometry("520x120")
        label = ttk.Label(progress, text="Checking database against disk...", style='Status.TLabel')
        label.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        progress.transient(self.root)
        progress.grab_set()

        def worker():
            try:
                stats = verify_database_file_availability(self.db_path)
                self.root.after(0, lambda s=stats: finish(s, None))
            except Exception as e:
                self.root.after(0, lambda err=e: finish(None, err))

        def finish(stats, error):
            try:
                progress.destroy()
            except Exception:
                pass
            if error:
                messagebox.showerror("Check files error", str(error))
                return
            lines = [
                f"Marked missing: {stats['missing']}",
                f"Still present: {stats['existing']}",
                f"Added new: {stats['new']}",
                f"Duplicate rows added: {stats['duplicates']}",
            ]
            messagebox.showinfo("Check files now", "\n".join(lines))
            self._load_groups()

        threading.Thread(target=worker, daemon=True).start()

    def open_database(self):
        path = filedialog.askopenfilename(
            title="Open duplicate database",
            filetypes=[("SQLite database", "*.db *.sqlite"), ("All files", "*.*")]
        )
        if path:
            self._switch_database(path)

    def _switch_database(self, path):
        self.stop_audio()
        try:
            self._save_session_decision_snapshot()
            self.conn.close()
        except Exception:
            pass
        self.db_path = path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_decisions_table()
        self._clear_transient_decisions_on_startup()
        self.root.title(f"Duplicate Review - {APP_VERSION} - {os.path.basename(self.db_path)}")
        self.extension_filter.set("ALL")
        self.page_index = 0
        self._save_settings()
        self._load_groups()

    def new_search_database(self, compute_audio_md5=False):
        root_folder = filedialog.askdirectory(title="Folder to search for duplicates")
        if not root_folder:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path = str(APP_DIR / f"_pending_search_{stamp}.db")
        progress = tk.Toplevel(self.root)
        progress.title("Scanning")
        progress.configure(bg=BG_BASE)
        progress.geometry("620x180")
        self._center_window(progress, 620, 180)
        mode = "Audio-only MD5" if compute_audio_md5 else "Exact MD5"
        label = ttk.Label(progress, text=f"Preparing {mode} scan...", style='Status.TLabel')
        label.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        button_row = ttk.Frame(progress)
        button_row.pack(fill=tk.X, padx=12, pady=(0, 12))
        save_button = ttk.Button(button_row, text="Save search", state=tk.DISABLED)
        close_button = ttk.Button(button_row, text="Close", state=tk.DISABLED)
        close_button.pack(side=tk.RIGHT, padx=4)
        save_button.pack(side=tk.RIGHT, padx=4)
        progress.transient(self.root)
        progress.grab_set()

        def update_progress(done, total, duplicates, stage):
            percent = (done / total * 100) if total else 0
            label.config(
                text=(
                    f"{stage}\n"
                    f"{percent:.1f}%  |  files checked {done:,} / {total:,}\n"
                    f"duplicates found: {duplicates:,}"
                )
            )

        def worker():
            try:
                stats = self._create_scan_database(
                    root_folder, db_path, compute_audio_md5,
                    progress_callback=lambda d, t, dup, stage:
                        self.root.after(0, lambda: update_progress(d, t, dup, stage))
                )
                self.root.after(0, lambda s=stats: finish(s, None))
            except Exception as e:
                self.root.after(0, lambda err=e: finish(None, err))

        def finish(stats, error):
            if error:
                try:
                    if os.path.exists(db_path):
                        os.remove(db_path)
                except Exception:
                    pass
                try:
                    progress.destroy()
                except Exception:
                    pass
                messagebox.showerror("Scan error", str(error))
                return
            label.config(
                text=(
                    "Scan complete\n"
                    f"Files checked: {stats['files']:,}\n"
                    f"Duplicate groups: {stats['groups']:,}  |  duplicate files: {stats['duplicates']:,}\n"
                    "Save this search now?"
                )
            )
            save_button.config(
                state=tk.NORMAL,
                command=lambda: self._save_finished_search(db_path, root_folder, progress)
            )
            close_button.config(
                state=tk.NORMAL,
                command=lambda: self._discard_finished_search(db_path, progress)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _center_window(self, window, width, height):
        window.update_idletasks()
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _save_finished_search(self, temp_db_path, root_folder, window):
        default_name = f"duplicates_{Path(root_folder).name or 'scan'}.db"
        final_path = filedialog.asksaveasfilename(
            title="Save finished search",
            defaultextension=".db",
            initialfile=default_name,
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")]
        )
        if not final_path:
            return
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
            shutil.move(temp_db_path, final_path)
            window.destroy()
            self._switch_database(final_path)
        except Exception as e:
            messagebox.showerror("Save search", str(e))

    def _discard_finished_search(self, temp_db_path, window):
        try:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
        except Exception:
            pass
        window.destroy()

    def _create_scan_database(self, root_folder, db_path, compute_audio_md5=False, progress_callback=None):
        if os.path.exists(db_path):
            os.remove(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
        c = conn.cursor()
        files = 0
        all_files = []
        for dirpath, _, filenames in os.walk(root_folder):
            for fn in filenames:
                all_files.append((dirpath, fn))
        total_files = len(all_files)
        if progress_callback:
            progress_callback(0, total_files, 0, "Scanning files")
        for dirpath, fn in all_files:
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
                ext = os.path.splitext(fn)[1].lower()
                cat = category_for_extension(ext)
                md5 = md5_file(full)
                audio_md5 = None
                if compute_audio_md5 and cat == "audio":
                    audio_md5 = audio_md5_file(full, ext)
                c.execute("""
                    INSERT INTO archivos
                    (ruta, carpeta, nombre, extension, tamano, fecha_mod, md5, audio_md5, escaneado, categoria)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (full, dirpath, fn, ext, st.st_size, st.st_mtime, md5, audio_md5, 1, cat))
                aid = c.lastrowid
                if cat == "imagen":
                    width, height, ahash = image_fingerprint(full)
                    c.execute("""
                        INSERT OR REPLACE INTO image_metadata (archivo_id, width, height, ahash)
                        VALUES (?,?,?,?)
                    """, (aid, width, height, ahash))
                files += 1
                if files % 250 == 0:
                    conn.commit()
                    if progress_callback:
                        progress_callback(files, total_files, 0, "Scanning files")
            except Exception as e:
                c.execute("""
                    INSERT OR IGNORE INTO archivos
                    (ruta, carpeta, nombre, extension, escaneado, error, categoria)
                    VALUES (?,?,?,?,?,?,?)
                """, (full, dirpath, fn, os.path.splitext(fn)[1].lower(), 1, str(e), "otro"))
        conn.commit()
        if progress_callback:
            progress_callback(files, total_files, 0, "Finding duplicates")
        groups, dupes = detect_duplicates(conn)
        if progress_callback:
            progress_callback(files, total_files, dupes, "Finding duplicates")
        notes = f"root={root_folder};audio_md5={1 if compute_audio_md5 else 0}"
        c.execute("""
            INSERT INTO escaneos (inicio, fin, total_archivos, total_duplicados, notas)
            VALUES (?,?,?,?,?)
        """, (time.time(), time.time(), files, dupes, notes))
        conn.commit()
        conn.close()
        return {"files": files, "groups": groups, "duplicates": dupes}

    def _trash_or_remove(self, path):
        send_to_recycle_bin(path)

    # ---------- Data ----------
    def _set_match_filter(self, label):
        self.match_filter_label.set(label)
        self.filter_type.set(MATCH_VALUE_BY_LABEL.get(label, "all"))
        if hasattr(self, "match_button"):
            self.match_button.config(text=label)
        self._on_filter_change()

    def _on_filter_change(self):
        self._save_settings()
        self.page_index = 0
        self._load_groups()
        self._refresh_expandable_boxes()

    def _set_extension_filter(self, ext):
        self.extension_filter.set(ext)
        self._save_settings()
        if hasattr(self, "extension_buttons"):
            self._refresh_segmented_buttons(self.extension_buttons, ext)
        self._on_filter_change()

    def _refresh_extension_menu(self):
        if not hasattr(self, "extension_buttons"):
            return
        current = self.extension_filter.get() or "ALL"
        exts = ["ALL"] + duplicate_extensions(self.conn)
        if current not in exts:
            current = "ALL"
            self.extension_filter.set(current)
        extra_exts = [ext for ext in exts if ext not in TYPE_FILTERS]
        visible = TYPE_FILTERS[:]
        if current not in visible:
            visible.append(current)
        if (getattr(self, "extension_values", None) != visible or
                getattr(self, "extension_extra_values", None) != extra_exts):
            for child in self.extension_segment.winfo_children():
                child.destroy()
            self.extension_buttons = []
            for ext in visible:
                label = "All" if ext == "ALL" else ext
                btn = self._segmented_button(
                    self.extension_segment, label, current == ext,
                    lambda e=ext: self._set_extension_filter(e),
                    rounded=True
                )
                btn.pack(side=tk.LEFT)
                self.extension_buttons.append((btn, label, ext, True))
            if extra_exts:
                more_btn = tk.Menubutton(
                    self.extension_segment, text="More", bg=BG_CARD, fg=FG_HINT,
                    activebackground=BG_CARD_HI, activeforeground=FG_TEXT,
                    bd=1, relief=tk.SOLID, font=FONT_UI, padx=10, pady=3,
                    cursor="hand2", takefocus=0
                )
                menu = tk.Menu(more_btn, tearoff=0, bg=BG_HEADER, fg=FG_MUTED,
                               activebackground=BG_CARD, activeforeground=FG_TEXT,
                               font=FONT_UI)
                for ext in extra_exts:
                    menu.add_command(label=ext, command=lambda e=ext: self._set_extension_filter(e))
                more_btn['menu'] = menu
                more_btn.pack(side=tk.LEFT)
            self.extension_values = visible
            self.extension_extra_values = extra_exts
        self._refresh_segmented_buttons(self.extension_buttons, current)

    def _load_groups(self, focus_group_id=None):
        self._refresh_extension_menu()
        self.group_ids = duplicate_group_ids(
            self.conn,
            match_filter=self.filter_type.get(),
            extension_filter=self.extension_filter.get(),
            search_text=self.search_text.get().strip(),
            group_sort=self.group_sort.get(),
        )
        if self.hide_incomplete.get():
            self.group_ids = [
                gid for gid in self.group_ids
                if not self._group_has_missing_or_deleted(gid)
            ]
        self.filtered_file_count, self.filtered_total_size = self._filtered_totals()
        if focus_group_id in self.group_ids:
            self.group_ids.remove(focus_group_id)
            self.group_ids.insert(0, focus_group_id)
            self.page_index = 0
        self._render_page()

    def _group_has_missing_or_deleted(self, gid):
        return group_has_missing_or_deleted(self.conn, gid)

    def _filtered_totals(self):
        return filtered_duplicate_totals(self.conn, self.group_ids)

    def _format_bytes(self, size):
        size = int(size or 0)
        units = ["bytes", "KB", "MB", "GB", "TB"]
        value = float(size)
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        if unit == "bytes":
            return f"{size:,} bytes"
        return f"{value:.2f} {unit}"

    def _render_page(self):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.row_widgets = []
        self.image_refs = []
        self.folder_clone_count_cache = {}
        self.hash_colors = {'md5': {}, 'audio_md5': {}}
        self.next_hash_color = {'md5': 0, 'audio_md5': 0}

        total = len(self.group_ids)
        if total == 0:
            self.summary_label.config(text="No groups match filter")
            self.filtered_size_label.config(text="0 files - 0 bytes filtered")
            self.page_label.config(text="0 / 0")
            return

        start = self.page_index * self.page_size
        end = min(start + self.page_size, total)
        page_groups = self.group_ids[start:end]

        self.summary_label.config(
            text=f"{total} groups - showing {start+1}-{end}")
        self.filtered_size_label.config(
            text=f"{self.filtered_file_count:,} files - {self._format_bytes(self.filtered_total_size)} filtered")
        self.page_label.config(
            text=f"page {self.page_index+1} / {(total + self.page_size - 1) // self.page_size}")

        for gid in page_groups:
            rows = duplicate_group_rows(self.conn, gid, self.row_sort.get())
            if len(rows) < 2:
                continue
            self._build_group_block(gid, rows)

        # quick scroll to top
        self.canvas.yview_moveto(0)

    def _build_group_block(self, gid, rows):
        sep = tk.Frame(self.list_inner, bg=BG_BASE, height=2)
        sep.pack(fill=tk.X, pady=(6, 0))

        block = tk.Frame(self.list_inner, bg=BG_GROUP, bd=0,
                         highlightbackground=ACCENT_BORDER,
                         highlightthickness=1)
        block.pack(fill=tk.X, padx=14, pady=(0, 8))

        header_bg = "#14141c"
        if gid == self.highlight_group_id:
            block.config(highlightthickness=3, highlightbackground=SELECT_BORDER)
            header_bg = SELECT_BG

        header = tk.Frame(block, bg=header_bg, padx=12, pady=8)
        header.pack(fill=tk.X)

        tipo = rows[0]['tipo_match']
        score = max((r.get('score') or 0) for r in rows)
        pct = int(round(score * 100)) if 0 < score <= 1 else (int(score) if score else 0)
        pct = max(0, min(100, pct))
        total_size = sum(r['tamano'] for r in rows)
        recoverable = total_size - max(r['tamano'] for r in rows)

        tag = tk.Label(header, text=self._match_label(tipo).upper(), bg=self._match_bg(tipo),
                       fg=self._match_fg(tipo), padx=7, pady=2, font=FONT_UI_MED)
        tag.pack(side=tk.LEFT, padx=(0, 8))

        title = self._group_title(gid, rows)
        tk.Label(header, text=title, bg=header_bg, fg=ACCENT_TAN,
                 anchor='w', font=FONT_UI_MED).pack(side=tk.LEFT, fill=tk.X, expand=True)

        if pct:
            conf = tk.Frame(header, bg=header_bg)
            conf.pack(side=tk.LEFT, padx=(8, 8))
            track = tk.Canvas(conf, width=52, height=5, bg=header_bg,
                              highlightthickness=0, bd=0)
            track.pack(side=tk.LEFT, padx=(0, 5))
            track.create_rectangle(0, 1, 52, 4, fill=BG_CARD_HI, outline="")
            track.create_rectangle(0, 1, int(52 * pct / 100), 4,
                                   fill=ACCENT_SAGE if pct >= 85 else ACCENT_AMBER,
                                   outline="")
            tk.Label(conf, text=f"{pct}%", bg=header_bg, fg=FG_HINT,
                     font=FONT_META).pack(side=tk.LEFT)

        tk.Label(header, text=f"{len(rows)} files", bg=header_bg, fg=FG_HINT,
                 font=FONT_UI).pack(side=tk.LEFT, padx=(0, 8))
        self._make_chip(header, f"save {self._format_bytes(recoverable)}",
                        bg="#0e2040", fg="#5a8de0", border="#1a3870",
                        font=FONT_UI).pack(side=tk.LEFT, padx=(0, 8))
        self._assign_hash_colors(rows)
        for row in rows:
            self._build_file_row(block, row)

    def _group_title(self, gid, rows):
        first = rows[0]
        base = first.get('nombre') or f"Group {gid}"
        folder = self._short_folder(first.get('carpeta') or "", max_parts=1)
        if folder:
            return f"{base} - group {gid} - {folder}"
        return f"{base} - group {gid}"

    def _match_label(self, match_type):
        labels = {
            'md5': 'exact file',
            'audio_md5': 'same audio',
            'image_ahash': 'same image',
            'nombre_tamano': 'name + size',
            'nombre_normalizado': 'similar name',
            'nombre_exacto': 'similar name',
            'nombre_identico': 'exact filename',
            'folder_audio_md5': 'folder audio',
        }
        return labels.get(match_type, match_type.replace('_', ' '))

    def _match_bg(self, match_type):
        if match_type in ('md5', 'nombre_identico'):
            return "#0e2040"
        if match_type in ('audio_md5', 'image_ahash', 'nombre_tamano'):
            return ACCENT_SAGE_BG
        return ACCENT_AMBER_BG

    def _match_fg(self, match_type):
        if match_type in ('md5', 'nombre_identico'):
            return "#6ea8fe"
        if match_type in ('audio_md5', 'image_ahash', 'nombre_tamano'):
            return ACCENT_SAGE
        return ACCENT_AMBER

    def _assign_hash_colors(self, rows):
        previous_md5 = None
        previous_audio_md5 = None
        for row in rows:
            md5 = row.get('md5') or ''
            audio_md5 = row.get('audio_md5') or ''
            row['_md5_color'] = self._hash_color('md5', md5) if md5 else ACCENT_TAN
            row['_audio_md5_color'] = (
                self._hash_color('audio_md5', audio_md5) if audio_md5 else None
            )
            row['_md5_same_as_previous'] = bool(md5 and previous_md5 == md5)
            row['_audio_same_as_previous'] = bool(audio_md5 and previous_audio_md5 == audio_md5)
            previous_md5 = md5
            previous_audio_md5 = audio_md5

    def _hash_color(self, hash_type, value):
        palette = MD5_COLORS if hash_type == 'md5' else AUDIO_MD5_COLORS
        colors = self.hash_colors[hash_type]
        if value not in colors:
            index = self.next_hash_color[hash_type]
            colors[value] = palette[index % len(palette)]
            self.next_hash_color[hash_type] = index + 1
        return colors[value]

    def _build_global_rules_menu(self, parent):
        menu_btn = tk.Menubutton(parent, text="Rules...", bg="#3b5bdb", fg="#ffffff",
                                 activebackground="#4c6ef5", activeforeground="#ffffff",
                                 bd=1, relief=tk.SOLID, font=FONT_UI_MED,
                                 padx=12, pady=3, cursor="hand2", takefocus=0)
        menu = tk.Menu(menu_btn, tearoff=0, bg=BG_HEADER, fg=FG_MUTED,
                       activebackground=BG_CARD, activeforeground=FG_TEXT,
                       font=FONT_UI)
        menu.add_command(label="Keep only longest path",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("longest_path")))
        menu.add_command(label="Keep only shortest path",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("shortest_path")))
        menu.add_command(label="Keep only largest file",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("largest")))
        menu.add_command(label="Keep only smallest file",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("smallest")))
        menu.add_command(label="Keep only newest modified",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("newest")))
        menu.add_command(label="Keep only oldest modified",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("oldest")))
        menu.add_separator()
        menu.add_command(label="Trash exact hash duplicates only",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("exact_hash")))
        menu.add_command(label="Clear group choices",
                         command=self._ui_command(lambda: self.apply_rule_with_scope("clear")))
        menu_btn['menu'] = menu
        return menu_btn

    def _build_action_menu(self, parent, row):
        menu_btn = tk.Menubutton(parent, text="...", bg=BG_CARD, fg=FG_HINT,
                                 activebackground=BG_CARD_HI, activeforeground=FG_TEXT,
                                 bd=1, relief=tk.SOLID, font=FONT_UI_MED,
                                 padx=6, pady=2, cursor="hand2", takefocus=0)
        menu = tk.Menu(menu_btn, tearoff=0, bg=BG_HEADER, fg=FG_MUTED,
                       activebackground=BG_CARD, activeforeground=FG_TEXT,
                       font=FONT_UI)
        menu.add_command(label="Folder", command=self._ui_command(lambda r=row: self.open_folder(r)))
        menu.add_command(label="Merge", command=self._ui_command(lambda r=row: self.preview_folder_merge(r)))
        menu.add_command(label="Build group", command=self._ui_command(lambda r=row: self.build_folder_clone_group(r)))
        menu_btn['menu'] = menu
        return menu_btn

    def _build_decision_menu(self, parent, row, decision_var):
        label = DECISION_LABELS.get(decision_var.get(), "Unreviewed")
        btn = tk.Menubutton(parent, text=label, bg=BG_CARD, fg=FG_HINT,
                            activebackground=BG_CARD_HI, activeforeground=FG_TEXT,
                            bd=1, relief=tk.SOLID, font=FONT_UI_MED,
                            padx=8, pady=2, cursor="hand2", takefocus=0)
        menu = tk.Menu(btn, tearoff=0, bg=BG_HEADER, fg=FG_MUTED,
                       activebackground=BG_CARD, activeforeground=FG_TEXT,
                       font=FONT_UI)
        for decision, text in (
            ("master", "Keep"),
            ("protected", "Protected"),
            ("delete", "Trash"),
            ("ignored", "Ignored"),
            ("", "Clear"),
        ):
            menu.add_command(label=text, command=lambda d=decision, r=row: self._set_decision(r, d))
        btn['menu'] = menu
        return btn

    def _build_file_row(self, parent, row):
        outer = tk.Frame(parent, bg=BG_CARD, highlightbackground=ACCENT_BORDER,
                         highlightthickness=0, bd=0)
        outer.pack(fill=tk.X, padx=0, pady=0)

        rail = tk.Frame(outer, bg=ACCENT_SAGE, width=2)
        rail.pack(side=tk.LEFT, fill=tk.Y)

        line = tk.Frame(outer, bg=BG_CARD, padx=ROW_PAD_X, pady=ROW_PAD_Y)
        line.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        decision_var = tk.StringVar(value=row['decision'] or '')
        row['_decision_var'] = decision_var
        row['_outer'] = outer
        row['_line'] = line
        row['_rail'] = rail
        row['_selected'] = False
        row['_missing'] = not os.path.exists(row['ruta'])

        decision_btn = self._build_decision_menu(line, row, decision_var)
        decision_btn.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 8))
        row['_decision_button'] = decision_btn

        info = tk.Frame(line, bg=BG_CARD)
        info.grid(row=0, column=1, rowspan=2, sticky="ew")
        line.grid_columnconfigure(1, weight=1)
        title_line = tk.Frame(info, bg=BG_CARD)
        title_line.pack(fill=tk.X)
        name_lbl = tk.Label(title_line, text=row.get('nombre') or os.path.basename(row['ruta']),
                            bg=BG_CARD, fg=ACCENT_TAN, anchor='w', font=FONT_UI_MED)
        name_lbl.pack(side=tk.LEFT)
        path_lbl = tk.Label(title_line, text=f" - {row.get('ruta') or ''}",
                            bg=BG_CARD, fg=FG_HINT, anchor='w',
                            justify=tk.LEFT, font=FONT_UI)
        path_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        meta = tk.Frame(info, bg=BG_CARD)
        meta.pack(fill=tk.X, pady=(2, 0))
        size_text = f"{int(row['tamano'] or 0):,} bytes / {(row['tamano'] or 0)/1024/1024:.2f} MB"
        size_chip = self._make_chip(meta, size_text, bg=ACCENT_SAGE_BG, fg=ACCENT_SAGE,
                                    border="#0f4028", font=FONT_META)
        size_chip.pack(side=tk.LEFT, padx=(0, 4))

        ext = (row.get('extension') or '').lower()
        ext_wrap = tk.Frame(meta, bg=BG_CARD)
        ext_wrap.pack(side=tk.LEFT, padx=(0, 4))
        type_dot = tk.Label(ext_wrap, text="o", bg=BG_CARD,
                            fg=EXTENSION_COLORS.get(ext, FG_HINT), font=FONT_META_MED)
        type_dot.pack(side=tk.LEFT, padx=(0, 2))
        type_lbl = self._make_chip(ext_wrap, ext or "no ext", bg=BG_CARD,
                                   fg=FG_HINT, border=ACCENT_BORDER, font=FONT_META)
        type_lbl.pack(side=tk.LEFT)

        md5_value_lbl = None
        audio_value_lbl = None
        hash_label_lbs = []
        if row.get('md5'):
            md5_value_lbl = self._make_chip(meta, self._short_hash(row.get('md5')),
                                            bg="#111118", fg=row.get('_md5_color', FG_HINT),
                                            border=ACCENT_DIVIDER, font=FONT_META)
            md5_value_lbl.pack(side=tk.LEFT, padx=(0, 4))
        if row.get('audio_md5'):
            audio_value_lbl = self._make_chip(meta, self._short_hash(row.get('audio_md5'), "audio"),
                                              bg="#111118", fg="#3b5bdb",
                                              border=ACCENT_DIVIDER, font=FONT_META)
            audio_value_lbl.pack(side=tk.LEFT, padx=(0, 4))
        if row.get('bitrate'):
            self._make_chip(meta, self._format_bitrate(row.get('bitrate')),
                            bg=BG_CARD, fg=FG_HINT, border=ACCENT_BORDER,
                            font=FONT_META).pack(side=tk.LEFT, padx=(0, 4))
        folder_clone_count, external_clone_count = self._folder_clone_counts(row['carpeta'])
        if folder_clone_count:
            self._make_chip(meta, f"clones {folder_clone_count}/{external_clone_count}",
                            bg=BG_CARD, fg=FG_HINT, border=ACCENT_BORDER,
                            font=FONT_META).pack(side=tk.LEFT, padx=(0, 4))

        warn_lbl = tk.Label(meta, text="", bg=BG_CARD, fg=MISSING_FG,
                            font=FONT_UI_MED)
        warn_lbl.pack(side=tk.RIGHT, padx=8)

        action_btn = self._build_action_menu(line, row)
        action_btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

        row['_warn_lbl'] = warn_lbl
        row['_path_lbl'] = path_lbl
        row['_name_lbl'] = name_lbl
        row['_size_lbl'] = size_chip
        row['_info_lbl'] = None
        row['_hash_rail'] = rail
        row['_md5_rail'] = rail
        row['_audio_rail'] = None
        row['_md5_value_lbl'] = md5_value_lbl
        row['_audio_value_lbl'] = audio_value_lbl
        row['_hash_label_lbs'] = hash_label_lbs
        row['_type_dot_lbl'] = type_dot
        row['_type_lbl'] = type_lbl
        row['_sub'] = meta
        row['_bg_widgets'] = [outer, line, info, title_line, meta, ext_wrap, name_lbl, path_lbl, warn_lbl, type_dot]

        for w in row['_bg_widgets'] + [size_chip, type_lbl]:
            w.bind("<Button-1>", lambda e, r=row: self._on_row_click(r, e))
        if md5_value_lbl:
            md5_value_lbl.bind("<Button-1>", lambda e, r=row: self._on_row_click(r, e))
        if audio_value_lbl:
            audio_value_lbl.bind("<Button-1>", lambda e, r=row: self._on_row_click(r, e))

        self.row_widgets.append(row)
        self._apply_row_color(row)

        line.bind("<Configure>",
                  lambda e, r=row, lbl=path_lbl: self._fit_path_label(r, lbl, e.width))
    def _is_image_row(self, row):
        return (row.get('categoria') == 'imagen' or
                (row.get('extension') or '').lower() in IMAGE_EXTS)

    def _make_image_preview(self, path):
        if not IMAGE_OK or not os.path.exists(path):
            return None
        try:
            with Image.open(path) as img:
                img.thumbnail((96, 72))
                thumb = Image.new("RGB", (96, 72), BG_CARD)
                x = (96 - img.width) // 2
                y = (72 - img.height) // 2
                thumb.paste(img.convert("RGB"), (x, y))
            return ImageTk.PhotoImage(thumb)
        except Exception:
            return None

    def _fit_path_label(self, row, label, line_width):
        available = max(80, line_width - 24)
        wrapped = self._wrap_path_to_width(row['ruta'], label, available)
        label.configure(text=f" - {wrapped}",
                        wraplength=0)

    def _wrap_path_to_width(self, text, label, width):
        try:
            measure_font = tkfont.Font(font=label.cget('font'))
        except Exception:
            measure_font = tkfont.nametofont('TkDefaultFont')

        lines = []
        remaining = text
        break_chars = set("\\/ _-.")
        while remaining:
            if measure_font.measure(remaining) <= width:
                lines.append(remaining)
                break

            cut = 0
            last_break = -1
            for i, ch in enumerate(remaining, start=1):
                if measure_font.measure(remaining[:i]) > width:
                    cut = max(1, i - 1)
                    break
                if ch in break_chars:
                    last_break = i

            if last_break > 0 and last_break >= max(1, cut // 2):
                cut = last_break
            elif cut <= 0:
                cut = 1

            lines.append(remaining[:cut])
            remaining = remaining[cut:]

        return "\n".join(lines)

    def _apply_row_color(self, row):
        outer = row['_outer']
        d = row['_decision_var'].get()
        missing = row.get('_missing', False)
        selected = row.get('_selected', False)

        if d in ('deleted', 'missing') or missing:
            bg = MISSING_BG
            border = MISSING_BORDER
            rail_color = MISSING_BORDER
        else:
            bg = BG_CARD
            border = ACCENT_BORDER
            rail_color = FG_HINT
        if selected:
            border = SELECT_BORDER

        outer.config(bg=bg, highlightbackground=border,
                     highlightthickness=1 if (selected or missing or d in ('deleted', 'missing')) else 0)

        for widget in row.get('_bg_widgets', []):
            try:
                widget.config(bg=bg)
            except tk.TclError:
                pass

        rail = row.get('_rail') or row.get('_hash_rail')
        if rail:
            rail.config(bg=rail_color)

        decision_btn = row.get('_decision_button')
        if decision_btn:
            label = DECISION_LABELS.get(d, 'Unreviewed')
            btn_bg, btn_fg = self._state_button_colors(d, missing)
            decision_btn.config(text=label, bg=btn_bg, fg=btn_fg,
                                activebackground=btn_bg, activeforeground=btn_fg)

        warn = row.get('_warn_lbl')
        if warn:
            if d == 'deleted':
                warn_text = "DELETED"
            elif d == 'missing' or missing:
                warn_text = "MISSING"
            else:
                warn_text = ""
            warn.config(text=warn_text, bg=bg, fg=MISSING_FG)
        name_lbl = row.get('_name_lbl')
        if name_lbl:
            name_lbl.config(fg=MISSING_FG if (d in ('deleted', 'missing') or missing) else ACCENT_TAN, bg=bg)
        path_lbl = row.get('_path_lbl')
        if path_lbl:
            path_lbl.config(fg=MISSING_FG if (d in ('deleted', 'missing') or missing) else FG_HINT, bg=bg)

        md5_color = row.get('_md5_color', ACCENT_TAN)
        audio_color = row.get('_audio_md5_color') or "#3b5bdb"
        md5_value_lbl = row.get('_md5_value_lbl')
        if md5_value_lbl:
            md5_value_lbl.config(fg=md5_color, bg="#111118")
        audio_value_lbl = row.get('_audio_value_lbl')
        if audio_value_lbl:
            audio_value_lbl.config(fg=audio_color, bg="#111118")

        type_dot = row.get('_type_dot_lbl')
        if type_dot:
            ext = (row.get('extension') or '').lower()
            type_dot.config(fg=EXTENSION_COLORS.get(ext, FG_HINT), bg=bg)
        type_lbl = row.get('_type_lbl')
        if type_lbl:
            type_lbl.config(fg=FG_HINT, bg=bg)

    def _state_button_colors(self, decision, missing=False):
        if decision in ('deleted', 'missing') or missing:
            return MISSING_BG, MISSING_FG
        if decision == 'delete':
            return ACCENT_AMBER_BG, ACCENT_AMBER
        if decision == 'master':
            return ACCENT_SAGE_BG, ACCENT_SAGE
        if decision == 'protected':
            return "#0e2040", "#6ea8fe"
        if decision == 'ignored':
            return "#181820", "#777784"
        return BG_CARD, FG_HINT

    # ---------- Selection + keyboard ----------
    def _on_row_click(self, row, event):
        self._return_focus_to_root()
        if self._ctrl_is_held(event):
            row['_selected'] = not row.get('_selected', False)
            self._apply_row_color(row)
        else:
            self._clear_selection()
            row['_selected'] = True
            self._apply_row_color(row)
        self._update_mode_indicator()

    def _ctrl_is_held(self, event):
        return bool(getattr(event, "state", 0) & 0x4)

    def _selected_rows(self):
        return [r for r in self.row_widgets if r.get('_selected')]

    def _clear_selection(self):
        for r in self.row_widgets:
            if r.get('_selected'):
                r['_selected'] = False
                self._apply_row_color(r)

    def _on_key(self, event):
        # ignore if focus is on entry widget (search box)
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        sel = self._selected_rows()
        k = event.keysym.lower()
        if (event.state & 0x4) and k == 'z':
            self.undo_last_action()
            return "break"
        if k == 'd':
            self._direct_recycle_selected(sel)
            return "break"
        state_action = self._state_action_for_key(k)
        if state_action:
            self._set_selected_state(sel, STATE_SHORTCUT_TO_DECISION[state_action], DECISION_LABELS[STATE_SHORTCUT_TO_DECISION[state_action]])
            return "break"
        elif k == 'r':
            self.reset_review_choices()
            return "break"
        elif k == 'space':
            self._space_pressed(sel)
            return "break"
        elif k == 'escape':
            self._clear_selection()
            self._update_mode_indicator()
            return "break"

    def _update_mode_indicator(self):
        n = len(self._selected_rows())
        self.status.config(
            text=f"{n} selected  ·  Ctrl+click multi-select  ·  D trash  ·  Space play  ·  K keep  ·  Ctrl+Z undo  ·  Esc clear")

    def _state_action_for_key(self, key):
        for action, shortcut in self.state_shortcuts.items():
            if key == (shortcut or "").lower():
                return action
        return None

    def _set_selected_state(self, rows, decision, label):
        if not rows:
            return
        self._push_undo("state", rows)
        for r in rows:
            self._set_row_decision(r, decision)
        self.status.config(text=f"{len(rows)} marked as {label.lower()}")

    def _direct_recycle_selected(self, rows):
        rows = [r for r in rows if not r.get('_missing') and os.path.exists(r.get('ruta', ''))]
        if not rows:
            return

        if self.confirm_deletes.get():
            preview = "\n".join(r['ruta'] for r in rows[:8])
            if len(rows) > 8:
                preview += f"\n... and {len(rows) - 8} more"
            msg = (
                f"Send {len(rows)} selected file(s) to Recycle Bin now?\n\n"
                f"{preview}\n\n"
                "No permanent delete will be used. Deleted rows stay visible."
            )
            if not messagebox.askyesno("Delete confirmation", msg):
                return

        self._release_if_rows_affect_playback(rows)
        self._push_undo("delete", rows)
        ok = 0
        errors = []
        for r in rows:
            try:
                self._trash_or_remove(r['ruta'])
                self._set_row_decision(r, 'deleted')
                r['_missing'] = True
                r['_selected'] = False
                self._apply_row_color(r)
                ok += 1
            except Exception as e:
                errors.append(f"{r['ruta']}: {e}")

        self.status.config(text=f"Sent {ok} file(s) to Recycle Bin")
        if errors:
            messagebox.showerror("Recycle Bin errors", "\n".join(errors[:10]))

    def _push_undo(self, action, rows):
        self.undo_stack.push(action, rows)

    def undo_last_action(self):
        if not self.undo_stack:
            self.status.config(text="Nothing to undo")
            return
        item = self.undo_stack.pop()
        restored = 0
        blocked = 0
        for state in item["rows"]:
            row = self._visible_row_by_id(state["id"])
            if item["action"] == "delete" and not os.path.exists(state.get("path", "")):
                if row:
                    row['_missing'] = True
                    self._set_row_decision(row, 'deleted')
                else:
                    self._save_decision(state["id"], 'deleted')
                blocked += 1
                continue
            if row:
                row['_missing'] = state["missing"]
                self._set_row_decision(row, state["decision"])
            else:
                self._save_decision(state["id"], state["decision"])
            restored += 1
        if item["action"] == "delete":
            self.status.config(
                text=f"Undo restored {restored} row state(s); {blocked} file(s) still in Recycle Bin")
        else:
            self.status.config(text=f"Undo restored {restored} row state(s)")

    def _visible_row_by_id(self, file_id):
        for r in self.row_widgets:
            if r.get("id") == file_id:
                return r
        return None

    def _space_pressed(self, sel):
        """Spacebar logic:
        - No selection: stop whatever is playing.
        - One selected, NOT currently playing -> play that one (stop current first).
        - One selected, AND it IS the currently playing one -> stop.
        - Multiple selected: play first; if same first as playing, stop."""
        if not sel:
            self.stop_audio()
            return
        target = sel[0]
        if self._row_is_playing(target):
            self.stop_audio()
        else:
            self.play_file(target)

    def toggle_selected_playback(self):
        self._space_pressed(self._selected_rows())

    def _format_time(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _format_bitrate(self, bitrate):
        try:
            bitrate = int(bitrate)
        except (TypeError, ValueError):
            return "bitrate N/A"
        if bitrate > 10000:
            bitrate = round(bitrate / 1000)
        return f"{bitrate} kbps"

    def _row_is_playing(self, row):
        return bool(
            self.playing_row and row and
            (row.get('id') == self.playing_row.get('id') or
             row.get('ruta') == self.playing_row.get('ruta'))
        )

    def _rows_include_playing(self, rows):
        return any(self._row_is_playing(r) for r in rows)

    def _release_if_rows_affect_playback(self, rows):
        if self._rows_include_playing(rows):
            self.stop_audio()
            return True
        return False

    def _update_play_toggle_button(self):
        if not hasattr(self, "play_toggle_button"):
            return
        if self.playing_row:
            self.play_toggle_button.config(text="Stop", bg=ACCENT_AMBER_BG, fg=ACCENT_AMBER,
                                           activebackground=ACCENT_AMBER_BG,
                                           activeforeground=ACCENT_AMBER)
        else:
            self.play_toggle_button.config(text="Play", bg=BG_CARD, fg=FG_MUTED,
                                           activebackground=BG_CARD_HI,
                                           activeforeground=FG_TEXT)

    def _cancel_playback_timer(self):
        if self.playback_after is not None:
            try:
                self.root.after_cancel(self.playback_after)
            except Exception:
                pass
            self.playback_after = None

    def _reset_playback_bar(self):
        self._cancel_playback_timer()
        self.playback_seek_offset = 0.0
        self.playback_dragging = False
        self.playback_last_seek = 0.0
        self.playback_progress.set(0.0)
        self.playback_time.set("00:00")
        self.playback_current_time.set("00:00")
        self.playback_total_time.set("00:00")
        self.playback_info.set("No audio")
        self.playback_file.set("")
        self._draw_playback_bar()
        self._update_play_toggle_button()

    def _get_audio_duration(self, path):
        return self.playback.duration(path)

    def _event_to_seek_seconds(self, event):
        if self.playback_duration <= 0 or not hasattr(self, 'playback_canvas'):
            return 0.0
        width = max(1, self.playback_canvas.winfo_width())
        fraction = min(1.0, max(0.0, event.x / width))
        return fraction * self.playback_duration

    def _draw_playback_bar(self):
        if not hasattr(self, 'playback_canvas'):
            return
        canvas = self.playback_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        y = 7
        track_h = 4
        duration = self.playback_duration if self.playback_duration > 0 else 1.0
        value = min(max(self.playback_progress.get(), 0.0), duration)
        frac = value / duration if duration else 0.0
        fill_w = int(width * frac)
        canvas.create_rectangle(0, y - track_h // 2, width, y + track_h // 2,
                                fill=ACCENT_DIVIDER, outline="")
        canvas.create_rectangle(0, y - track_h // 2, fill_w, y + track_h // 2,
                                fill="#3b5bdb", outline="")
        thumb_x = max(5, min(width - 5, fill_w))
        canvas.create_oval(thumb_x - 5, y - 5, thumb_x + 5, y + 5,
                           fill="#6ea8fe", outline="#3b5bdb", width=2)

    def _on_seek_canvas_press(self, event):
        self._on_seek_press(event)
        self._draw_playback_bar()

    def _on_seek_canvas_drag(self, event):
        self._on_seek_drag(event)
        self._draw_playback_bar()

    def _on_seek_canvas_release(self, event):
        self._on_seek_release(event)
        self._draw_playback_bar()

    def _on_seek_press(self, event):
        if not self.playing_row or self.playback_duration <= 0:
            return
        self.playback_dragging = True
        seconds = self._event_to_seek_seconds(event)
        self.playback_progress.set(seconds)
        self.playback_time.set(
            f"{self._format_time(seconds)} / {self._format_time(self.playback_duration)}")
        self.playback_current_time.set(self._format_time(seconds))
        self.playback_total_time.set(self._format_time(self.playback_duration))

    def _on_seek_drag(self, event):
        if not self.playback_dragging or self.playback_duration <= 0:
            return
        seconds = self._event_to_seek_seconds(event)
        self.playback_progress.set(seconds)
        self.playback_time.set(
            f"{self._format_time(seconds)} / {self._format_time(self.playback_duration)}")
        self.playback_current_time.set(self._format_time(seconds))
        self.playback_total_time.set(self._format_time(self.playback_duration))
        now = time.monotonic()
        if now - self.playback_last_seek >= 0.25:
            self.playback_last_seek = now
            self._seek_playback(seconds)

    def _on_seek_release(self, event):
        if not self.playback_dragging or not self.playing_row or self.playback_duration <= 0:
            self.playback_dragging = False
            return
        self.playback_dragging = False
        self.playback_last_seek = 0.0
        self._seek_playback(self._event_to_seek_seconds(event))

    def _seek_playback(self, seconds):
        if not self.playback.available or not self.playing_row:
            return
        seconds = min(max(0.0, seconds), max(0.0, self.playback_duration - 0.1))
        try:
            self._cancel_playback_timer()
            self.playback.seek(seconds)
            self.playback_seek_offset = seconds
            self.playback_progress.set(seconds)
            self._update_playback_timer()
        except Exception as e:
            messagebox.showerror("Seek error", str(e))

    def _start_playback_timer(self):
        self._cancel_playback_timer()
        self.playback_progress.set(0.0)
        self.playback_total_time.set(self._format_time(self.playback_duration))
        self._draw_playback_bar()
        self._update_play_toggle_button()
        self._update_playback_timer()

    def _update_playback_timer(self):
        if not self.playing_row:
            return

        pos_seconds = self.playback.position_seconds()
        elapsed = self.playback_seek_offset + max(0.0, pos_seconds)
        if pos_seconds < 0 and self.playback.available and not self.playback.is_busy():
            elapsed = self.playback_duration if self.playback_duration > 0 else 0.0
        if self.playback_duration > 0:
            elapsed = min(elapsed, self.playback_duration)
            if not self.playback_dragging:
                self.playback_progress.set(elapsed)
            self.playback_time.set(
                f"{self._format_time(elapsed)} / {self._format_time(self.playback_duration)}")
            self.playback_current_time.set(self._format_time(elapsed))
            self.playback_total_time.set(self._format_time(self.playback_duration))
        else:
            self.playback_time.set(self._format_time(elapsed))
            self.playback_current_time.set(self._format_time(elapsed))
            self.playback_total_time.set("00:00")
        self._draw_playback_bar()

        if self.playback.is_busy():
            self.playback_after = self.root.after(250, self._update_playback_timer)
        else:
            self.playing_row = None
            self.playback_after = None
            self.playback_seek_offset = 0.0
            self._reset_playback_bar()
            self._update_mode_indicator()

    # ---------- Actions ----------
    def play_file(self, row):
        decision = row.get('_decision_var').get() if '_decision_var' in row else row.get('decision', '')
        if decision in ('deleted', 'missing') or not os.path.exists(row.get('ruta', '')):
            self.status.config(text="Playback blocked: file is deleted or missing")
            return
        if self._is_image_row(row):
            self.open_image_viewer(row)
            return
        if not self.playback.available:
            messagebox.showerror("Audio", "pygame not available")
            return
        try:
            self._release_audio()
            self.playback_seek_offset = 0.0
            self.playback_duration = float(row.get('duracion') or 0.0) or self._get_audio_duration(row['ruta'])
            self.playback.play(row['ruta'])
            self.playing_row = row
            bitrate = self._format_bitrate(row.get('bitrate')) if row.get('bitrate') else "bitrate N/A"
            self.playback_info.set(bitrate)
            self.playback_file.set(row['nombre'])
            self._show_playback_panel()
            self._start_playback_timer()
            self._update_play_toggle_button()
            self._update_mode_indicator()
        except Exception as e:
            self.playing_row = None
            self._reset_playback_bar()
            self._update_play_toggle_button()
            messagebox.showerror("Play error", str(e))

    def stop_audio(self):
        self._release_audio()
        self.playing_row = None
        self.playback_duration = 0.0
        self._reset_playback_bar()
        self._update_play_toggle_button()
        self._update_mode_indicator()

    def _release_audio(self):
        """Stop and FULLY release the file handle pygame is holding.

        pygame.mixer.music.stop() does NOT close the underlying file. On
        Windows, send2trash then fails with OLE error 0x80270027 because the
        file is still open. Calling .unload() (pygame >=2.0) releases it.
        Falls back to loading a tiny silent buffer if unload is missing.
        """
        self._cancel_playback_timer()
        self.playback_progress.set(0.0)
        self.playback_time.set("00:00")
        self.playback_current_time.set("00:00")
        self.playback_total_time.set("00:00")
        self.playback_info.set("No audio")
        self.playback_file.set("")
        self.playback_seek_offset = 0.0
        self.playback_dragging = False
        self.playback_last_seek = 0.0
        self._draw_playback_bar()
        self.playback.release()

    def open_image_viewer(self, row):
        path = row['ruta']
        if (self.image_viewer and self.image_viewer.winfo_exists() and
                self.image_viewer_path == path):
            try:
                self.image_viewer.destroy()
            except Exception:
                pass
            self.image_viewer = None
            self.image_viewer_path = None
            return
        if not IMAGE_OK:
            try:
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Open image", str(e))
            return
        try:
            with Image.open(path) as img:
                image = img.convert("RGB").copy()
            viewer = tk.Toplevel(self.root)
            viewer.title(row['nombre'])
            viewer.configure(bg="#050505")
            try:
                viewer.attributes("-alpha", 0.97)
            except tk.TclError:
                pass

            screen_w = viewer.winfo_screenwidth()
            screen_h = viewer.winfo_screenheight()
            viewer.geometry(f"{screen_w}x{screen_h}+0+0")

            canvas = tk.Canvas(viewer, bg="#050505", highlightthickness=0)
            canvas.grid(row=0, column=0, sticky="nsew")
            viewer.grid_rowconfigure(0, weight=1)
            viewer.grid_columnconfigure(0, weight=1)
            close_btn = tk.Button(
                viewer, text="?", command=lambda v=viewer: self._close_image_viewer(v),
                bg="#181512", fg=FG_TEXT, activebackground=ACCENT_AMBER_BG,
                activeforeground=ACCENT_AMBER, bd=2, relief=tk.SOLID,
                font=('Segoe UI', 16, 'bold'), width=2
            )
            close_btn.place(relx=1.0, x=-26, y=22, anchor="ne")
            viewer.original_image = image
            viewer.zoom = 1.0
            viewer.canvas = canvas
            self._render_image_viewer(viewer)
            viewer.bind("<Escape>", lambda e, v=viewer: self._close_image_viewer(v))
            viewer.bind("<space>", lambda e, v=viewer: self._close_image_viewer(v))
            viewer.bind("<Key-space>", lambda e, v=viewer: self._close_image_viewer(v))
            viewer.bind("<MouseWheel>", lambda e, v=viewer: self._zoom_image_viewer(v, e.delta))
            viewer.protocol("WM_DELETE_WINDOW", lambda: self._close_image_viewer(viewer))
            viewer.focus_set()
            self.image_viewer = viewer
            self.image_viewer_path = path
        except Exception as e:
            try:
                os.startfile(path)
            except Exception:
                messagebox.showerror("Open image", str(e))

    def _render_image_viewer(self, viewer):
        image = viewer.original_image
        zoom = viewer.zoom
        if zoom != 1.0:
            size = (max(1, int(image.width * zoom)), max(1, int(image.height * zoom)))
            image = image.resize(size, Image.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        viewer.image_ref = photo
        canvas = viewer.canvas
        canvas.delete("all")
        canvas.update_idletasks()
        canvas.create_image(
            max(1, canvas.winfo_width()) // 2,
            max(1, canvas.winfo_height()) // 2,
            image=photo, anchor="center"
        )

    def _zoom_image_viewer(self, viewer, delta):
        step = 1.1 if delta > 0 else 1 / 1.1
        viewer.zoom = max(0.1, min(8.0, viewer.zoom * step))
        self._render_image_viewer(viewer)

    def _close_image_viewer(self, viewer):
        try:
            viewer.destroy()
        except Exception:
            pass
        if viewer is self.image_viewer:
            self.image_viewer = None
            self.image_viewer_path = None

    def open_folder(self, row):
        try:
            os.startfile(row['carpeta'])
        except Exception as e:
            messagebox.showerror("Open folder", str(e))

    def _folder_clone_counts(self, folder):
        if folder in self.folder_clone_count_cache:
            return self.folder_clone_count_cache[folder]

        c = self.conn.cursor()
        c.execute("""
        SELECT audio_md5, COUNT(*) as n
        FROM archivos
        WHERE carpeta = ? AND audio_md5 IS NOT NULL AND audio_md5 != ''
        GROUP BY audio_md5
        """, (folder,))
        hashes = [r[0] for r in c.fetchall()]
        if not hashes:
            return 0, 0

        placeholders = ",".join("?" * len(hashes))
        c.execute(f"""
        SELECT audio_md5, SUM(CASE WHEN carpeta = ? THEN 1 ELSE 0 END) as in_folder,
               SUM(CASE WHEN carpeta != ? THEN 1 ELSE 0 END) as outside_folder
        FROM archivos
        WHERE audio_md5 IN ({placeholders})
        GROUP BY audio_md5
        """, [folder, folder] + hashes)

        folder_clone_count = 0
        external_clone_count = 0
        for _hash, in_folder, outside_folder in c.fetchall():
            if outside_folder:
                folder_clone_count += in_folder or 0
                external_clone_count += outside_folder or 0
        result = (folder_clone_count, external_clone_count)
        self.folder_clone_count_cache[folder] = result
        return result

    def _folder_clone_rows(self, folder):
        c = self.conn.cursor()
        c.execute("""
        SELECT audio_md5
        FROM archivos
        WHERE carpeta = ? AND audio_md5 IS NOT NULL AND audio_md5 != ''
        GROUP BY audio_md5
        """, (folder,))
        hashes = [r[0] for r in c.fetchall()]
        if not hashes:
            return [], [], []

        placeholders = ",".join("?" * len(hashes))
        c.execute(f"""
        SELECT audio_md5
        FROM archivos
        WHERE audio_md5 IN ({placeholders})
        GROUP BY audio_md5
        HAVING SUM(CASE WHEN carpeta = ? THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN carpeta != ? THEN 1 ELSE 0 END) > 0
        """, hashes + [folder, folder])
        clone_hashes = [r[0] for r in c.fetchall()]
        if not clone_hashes:
            return [], [], []

        placeholders = ",".join("?" * len(clone_hashes))
        c.execute(f"""
        SELECT id, ruta, nombre, carpeta, tamano, md5, audio_md5
        FROM archivos
        WHERE audio_md5 IN ({placeholders})
        ORDER BY carpeta = ? DESC, audio_md5, carpeta, ruta
        """, clone_hashes + [folder])
        rows = [dict(r) for r in c.fetchall()]
        anchor_rows = [r for r in rows if r['carpeta'] == folder]
        external_rows = [r for r in rows if r['carpeta'] != folder]
        return rows, anchor_rows, external_rows

    def build_folder_clone_group(self, row):
        folder = row['carpeta']
        rows, anchor_rows, external_rows = self._folder_clone_rows(folder)
        if not rows:
            messagebox.showinfo(
                "Build group",
                "No files in this folder have audio_md5 clones elsewhere in the database."
            )
            return

        hashes = {r['audio_md5'] for r in rows}
        donor_folders = sorted({r['carpeta'] for r in external_rows})
        msg = "\n".join([
            "Build a new merged clone group from this folder?",
            "",
            folder,
            "",
            f"Folder files with clones: {len(anchor_rows)}",
            f"External clone files to include: {len(external_rows)}",
            f"Audio fingerprints: {len(hashes)}",
            f"Other folders involved: {len(donor_folders)}",
            "",
            "This updates the duplicate grouping database only.",
            "It does not move or delete any music files."
        ])
        if not messagebox.askyesno("Build merged group", msg):
            return

        ids = [r['id'] for r in rows]
        new_gid, _affected_groups = create_folder_clone_group(self.conn, ids)
        self.highlight_group_id = new_gid
        self.filter_type.set("audio_md5")
        self.match_filter_label.set(MATCH_LABEL_BY_VALUE["audio_md5"])
        self.hide_incomplete.set(False)
        self.search_text.set("")
        self.status.config(
            text=f"Built merged group {new_gid}: {len(rows)} files from {len(hashes)} audio hashes")
        self._load_groups(focus_group_id=new_gid)

    def _folder_audio_rows(self, folder):
        c = self.conn.cursor()
        c.execute("""
        SELECT id, ruta, nombre, carpeta, audio_md5
        FROM archivos
        WHERE carpeta = ? AND audio_md5 IS NOT NULL AND audio_md5 != ''
        ORDER BY ruta
        """, (folder,))
        return [dict(r) for r in c.fetchall()]

    def _find_merge_candidate_folders(self, target_folder):
        target_rows = self._folder_audio_rows(target_folder)
        target_md5s = {r['audio_md5'] for r in target_rows}
        if not target_md5s:
            return [], target_rows

        c = self.conn.cursor()
        c.execute("""
        SELECT carpeta
        FROM archivos
        WHERE audio_md5 IS NOT NULL AND audio_md5 != ''
          AND carpeta != ?
        GROUP BY carpeta
        """, (target_folder,))

        candidates = []
        target_norm = os.path.normcase(os.path.abspath(target_folder))
        for (folder,) in c.fetchall():
            if os.path.normcase(os.path.abspath(folder)) == target_norm:
                continue
            rows = self._folder_audio_rows(folder)
            duplicate_rows = [r for r in rows if r['audio_md5'] in target_md5s]
            donor_md5s = {r['audio_md5'] for r in rows}
            duplicate_md5s = {r['audio_md5'] for r in duplicate_rows}
            if duplicate_rows:
                candidates.append({
                    'folder': folder,
                    'rows': duplicate_rows,
                    'audio_count': len(duplicate_rows),
                    'fingerprint_count': len(duplicate_md5s),
                    'total_audio_count': len(rows),
                    'extra_audio_count': len(donor_md5s - target_md5s),
                })
        return candidates, target_rows

    def _folder_leftovers_after_removing(self, folder, rows):
        try:
            removing = {os.path.normcase(os.path.abspath(r['ruta'])) for r in rows}
            leftovers = []
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.normcase(os.path.abspath(path)) not in removing:
                    leftovers.append(path)
            return leftovers
        except Exception:
            return []

    def preview_folder_merge(self, target_row):
        target_folder = target_row['carpeta']
        if not os.path.isdir(target_folder):
            messagebox.showerror("Merge folders", f"Target folder not found:\n{target_folder}")
            return

        donors, target_rows = self._find_merge_candidate_folders(target_folder)
        if not donors:
            messagebox.showinfo(
                "Merge folders",
                "No donor folders found with audio_md5 files already present in the target folder."
            )
            return

        lines = [
            "Target folder:",
            target_folder,
            "",
            f"Target audio fingerprints: {len({r['audio_md5'] for r in target_rows})}",
            "",
            "Donor folders with duplicate audio to clean:",
        ]
        total_files = 0
        removable_dirs = 0
        for donor in donors[:8]:
            leftovers = self._folder_leftovers_after_removing(donor['folder'], donor['rows'])
            total_files += donor['audio_count']
            if not leftovers:
                removable_dirs += 1
            lines.extend([
                "",
                donor['folder'],
                f"  duplicate audio files to Recycle Bin: {donor['audio_count']}",
                f"  different audio files kept in donor: {donor['extra_audio_count']}",
                f"  leftover items after cleanup: {len(leftovers)}",
                "  donor folder: kept",
            ])
        if len(donors) > 8:
            lines.append(f"\n... and {len(donors) - 8} more donor folders")

        lines.extend([
            "",
            f"Total duplicate files to trash: {total_files}",
            "Donor folders: kept",
            "",
            "Apply this folder merge cleanup?"
        ])
        if not messagebox.askyesno("Preview folder merge", "\n".join(lines)):
            return

        self._apply_folder_merge(target_folder, donors)

    def _apply_folder_merge(self, target_folder, donors):
        self._release_if_rows_affect_playback(
            [r for donor in donors for r in donor['rows']]
        )
        trashed = 0
        removed_dirs = 0
        errors = []
        for donor in donors:
            for r in donor['rows']:
                if not os.path.exists(r['ruta']):
                    errors.append(f"MISSING {r['ruta']}")
                    continue
                try:
                    self._trash_or_remove(r['ruta'])
                    self._save_decision(r['id'], 'deleted')
                    trashed += 1
                except Exception as e:
                    errors.append(f"TRASH {r['ruta']}: {e}")

        self.status.config(
            text=f"Merged into folder: trashed {trashed} duplicate file(s)")
        if errors:
            messagebox.showerror("Folder merge errors", "\n".join(errors[:10]))
        self._load_groups()

    def apply_rule_with_scope(self, rule):
        scope = self._choose_rule_scope()
        if not scope:
            return
        groups = self._groups_for_scope(scope)
        if not groups:
            messagebox.showinfo("Rules", "No groups available for that scope.")
            return

        overlap_files = overlap_file_count(groups)
        if rule != "clear" and overlap_files:
            msg = (
                f"{overlap_files} file(s) appear in more than one group in this scope.\n\n"
                "This can happen when different duplicate methods overlap. A broad rule may overwrite choices from another group.\n\n"
                "Continue applying this rule?"
            )
            if not messagebox.askyesno("Overlapping groups", msg):
                return

        if self.confirm_deletes.get() and rule not in ("clear",):
            msg = (
                f"Apply rule to {len(groups)} group(s)?\n\n"
                f"Rule: {rule_label(rule)}\n"
                f"Scope: {self._scope_label(scope)}\n\n"
                "This only queues Keep/Trash choices. Files are changed later with Apply."
            )
            if not messagebox.askyesno("Delete confirmation", msg):
                return

        undo_rows = []
        for rows in groups:
            undo_rows.extend(rows)
        self._push_undo("state", undo_rows)
        decision_updates, changed = apply_rule_to_groups(groups, rule)
        self._save_decisions_bulk(decision_updates)

        self.status.config(
            text=f"Rule applied to {len(groups)} group(s): {changed} file choice(s) changed")
        self._load_groups()

    def _choose_rule_scope(self):
        return self._choose_scope("Apply rule to:", include_database=True)

    def _groups_for_scope(self, scope):
        if scope == "page":
            return self._group_rows_for_ids(self.group_ids[
                self.page_index * self.page_size:
                min((self.page_index + 1) * self.page_size, len(self.group_ids))
            ])
        if scope == "selected_groups":
            return self._group_rows_for_ids(self._group_ids_for_rows(self._selected_rows()))
        return self._group_rows_for_ids(self._all_duplicate_group_ids())

    def _all_duplicate_group_ids(self):
        return all_duplicate_group_ids(self.conn)

    def _group_rows_for_ids(self, group_ids):
        return duplicate_groups_for_ids(self.conn, group_ids)

    def _set_row_decision(self, row, decision, decision_updates=None):
        if '_decision_var' in row:
            row['_decision_var'].set(decision)
        if decision_updates is not None:
            decision_updates.append((row['id'], decision))
        else:
            self._save_decision(row['id'], decision)
        if '_outer' in row:
            self._apply_row_color(row)

    def _on_decision_change(self, row):
        d = row['_decision_var'].get()
        self._save_decision(row['id'], d)
        self._apply_row_color(row)

    def _save_decision(self, file_id, decision):
        save_decision(self.conn, file_id, decision)

    def _save_decisions_bulk(self, updates):
        save_decisions_bulk(self.conn, updates)

    def reset_review_choices(self):
        scope = self._choose_reset_scope()
        if not scope:
            return
        rows = self._rows_for_reset_scope(scope)
        transient = set(self._transient_decisions())
        updates = []
        changed = 0
        undo_rows = []
        for r in rows:
            current = r.get('_decision_var').get() if '_decision_var' in r else r.get('decision', '')
            if current in transient:
                undo_rows.append(r)
        self._push_undo("state", undo_rows)
        for r in undo_rows:
            self._set_row_decision(r, '', decision_updates=updates)
            changed += 1
        self._save_decisions_bulk(updates)
        self.status.config(text=f"Reset {changed} review choice(s)")
        if scope != "selected_files":
            self._load_groups()

    def _choose_reset_scope(self):
        return self._choose_scope(
            "Reset review choices:",
            options=[
                ("Reset selected files", "selected_files"),
                ("Reset whole page", "page"),
                ("Reset all pages", "database"),
            ]
        )

    def _rows_for_reset_scope(self, scope):
        if scope == "selected_files":
            return self._selected_rows()
        if scope == "page":
            return self.row_widgets
        c = self.conn.cursor()
        transient = self._transient_decisions()
        placeholders = ",".join("?" * len(transient))
        c.execute(f"""
            SELECT a.id, a.ruta, a.nombre, a.carpeta, de.decision
            FROM archivos a
            JOIN decisiones de ON de.archivo_id = a.id
            WHERE de.decision IN ({placeholders})
        """, transient)
        return [dict(r) for r in c.fetchall()]

    def apply_decisions(self):
        scope = self._choose_apply_scope()
        if not scope:
            return
        deletes = self._rows_marked_for_trash(scope)
        if not deletes:
            messagebox.showinfo("Apply", "No files are marked for Recycle Bin in that scope.")
            return

        missing = [r for r in deletes if not os.path.exists(r['ruta'])]
        deletes = [r for r in deletes if os.path.exists(r['ruta'])]
        if not deletes:
            messagebox.showinfo("Apply", "All marked files are already missing. No files were changed.")
            return

        if self.confirm_deletes.get():
            preview = "\n".join(r['ruta'] for r in deletes[:8])
            if len(deletes) > 8:
                preview += f"\n... and {len(deletes) - 8} more"
            msg = (
                f"Apply scope: {self._scope_label(scope)}\n"
                f"Send to Recycle Bin: {len(deletes)} file(s)\n"
                f"Already missing: {len(missing)} file(s)\n\n"
                f"{preview}\n\n"
                "No permanent delete will be used."
            )
            if not messagebox.askyesno("Delete confirmation", msg):
                return

        self._release_if_rows_affect_playback(deletes)
        errors = []
        for r in deletes:
            try:
                self._trash_or_remove(r['ruta'])
                self._save_decision(r['id'], 'deleted')
            except Exception as e:
                errors.append(f"TRASH {r['ruta']}: {e}")

        if errors:
            messagebox.showerror("Errors", "\n".join(errors[:10]))
        else:
            messagebox.showinfo("Done", f"Sent {len(deletes)} file(s) to Recycle Bin")
        self._load_groups()

    def _choose_apply_scope(self):
        return self._choose_scope("Apply queued Recycle Bin actions to:", include_database=True)

    def _choose_scope(self, title_text, include_database=True, options=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Scope")
        dialog.configure(bg=BG_BASE)
        dialog.geometry("360x180")
        self._center_window(dialog, 360, 180)
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"scope": None}

        tk.Label(dialog, text=title_text,
                 bg=BG_BASE, fg=FG_TEXT, font=FONT_UI_STRONG,
                 padx=12, pady=12).pack(fill=tk.X)
        buttons = tk.Frame(dialog, bg=BG_BASE, padx=12, pady=8)
        buttons.pack(fill=tk.BOTH, expand=True)

        def choose(scope):
            result["scope"] = scope
            dialog.destroy()

        if options is None:
            options = [
                ("Selected groups", "selected_groups"),
                ("Current page", "page"),
            ]
            if include_database:
                options.append(("Whole database", "database"))

        for label, scope in options:
            self._button(buttons, label, command=lambda s=scope: choose(s),
                         bg=BG_CARD, fg=FG_TEXT, padx=10, pady=5).pack(fill=tk.X, pady=3)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return result["scope"]

    def _scope_label(self, scope):
        return {
            "selected_groups": "selected groups",
            "page": "current page",
            "database": "whole database",
        }.get(scope, scope)

    def _group_ids_for_rows(self, rows):
        if not rows:
            return []
        return group_ids_for_file_ids(self.conn, [r['id'] for r in rows])

    def _rows_marked_for_trash(self, scope):
        if scope == "page":
            return [r for r in self.row_widgets if r['_decision_var'].get() == 'delete']

        if scope == "selected_groups":
            gids = self._group_ids_for_rows(self._selected_rows())
            return rows_marked_for_trash(self.conn, scope, gids)
        return rows_marked_for_trash(self.conn, scope)

    def prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self._render_page()

    def next_page(self):
        max_page = (len(self.group_ids) - 1) // self.page_size if self.group_ids else 0
        if self.page_index < max_page:
            self.page_index += 1
            self._render_page()


def main():
    if not os.path.exists(DB):
        print(f"DB not found: {DB}")
        sys.exit(1)
    root = tk.Tk()
    app = DupReviewApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()




