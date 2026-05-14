BG_DEEP = "#0a0a10"
BG_BASE = "#13131a"
BG_CARD = "#1a1a24"
BG_CARD_HI = "#22222e"
BG_HEADER = "#0d0d12"
FG_TEXT = "#d4d4dc"
FG_MUTED = "#888894"
FG_HINT = "#555560"
ACCENT_AMBER = "#e07b39"
ACCENT_AMBER_BG = "#2a1608"
ACCENT_SAGE = "#34c478"
ACCENT_BORDER = "#252530"
ACCENT_DIVIDER = "#1e1e28"
ACCENT_BLUE = "#3b5bdb"


def apply_theme(app):
    app.setStyleSheet(f"""
        QMainWindow, QWidget {{
            background: {BG_BASE};
            color: {FG_TEXT};
            font-family: "Segoe UI";
            font-size: 10pt;
        }}
        QMenuBar, QMenu {{
            background: {BG_HEADER};
            color: {FG_TEXT};
            border: 1px solid {ACCENT_BORDER};
        }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background: {BG_CARD_HI};
        }}
        QListWidget, QTableView, QTextEdit {{
            background: {BG_CARD};
            color: {FG_TEXT};
            border: 1px solid {ACCENT_BORDER};
            gridline-color: {ACCENT_DIVIDER};
            selection-background-color: #0e2040;
            selection-color: {FG_TEXT};
        }}
        QHeaderView::section {{
            background: {BG_HEADER};
            color: {FG_MUTED};
            border: 1px solid {ACCENT_BORDER};
            padding: 5px;
        }}
        QPushButton {{
            background: {BG_CARD};
            color: {FG_MUTED};
            border: 1px solid {ACCENT_BORDER};
            padding: 5px 10px;
        }}
        QPushButton:hover {{
            background: {BG_CARD_HI};
            color: {FG_TEXT};
        }}
        QPushButton:pressed {{
            background: {BG_HEADER};
        }}
        QPushButton:disabled {{
            color: {FG_HINT};
            background: {BG_BASE};
        }}
        QLineEdit, QComboBox {{
            background: {BG_CARD};
            color: {FG_TEXT};
            border: 1px solid {ACCENT_BORDER};
            padding: 5px;
            selection-background-color: {BG_CARD_HI};
        }}
        QLabel {{
            color: {FG_TEXT};
        }}
        QCheckBox {{
            color: {FG_TEXT};
        }}
        QSplitter::handle {{
            background: {ACCENT_DIVIDER};
        }}
        QProgressBar {{
            background: {BG_DEEP};
            color: {FG_TEXT};
            border: 1px solid {ACCENT_BORDER};
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: {ACCENT_BLUE};
        }}
        QSlider::groove:horizontal {{
            background: {ACCENT_DIVIDER};
            height: 5px;
        }}
        QSlider::handle:horizontal {{
            background: #6ea8fe;
            border: 1px solid {ACCENT_BLUE};
            width: 12px;
            margin: -5px 0;
        }}
        QStatusBar {{
            background: {BG_DEEP};
            color: {FG_HINT};
        }}
        QFrame#DuplicateToolbar {{
            background: {BG_DEEP};
            border-bottom: 1px solid {ACCENT_DIVIDER};
        }}
        QFrame#ToolbarDraggableItem {{
            background: transparent;
        }}
        QFrame#ToolbarDragHandle {{
            background: transparent;
        }}
        QFrame#ToolbarDragHandle[active="true"] {{
            background: #3b5bdb;
        }}
        QLabel#ToolbarItemTag {{
            background: #0d0d12;
            color: #6f7180;
            border: 1px solid #252530;
            padding: 1px 6px;
            font-size: 8pt;
            font-weight: 700;
        }}
        QLabel#ToolbarItemTag:hover {{
            color: #d4d4dc;
            border-color: #3b5bdb;
        }}
        QScrollArea#ToolbarScroller {{
            background: {BG_DEEP};
            border: none;
        }}
        QFrame#DuplicateSummary {{
            background: {BG_DEEP};
            border-bottom: 1px solid {ACCENT_DIVIDER};
        }}
        QFrame#DuplicateSummary QLabel {{
            color: {FG_HINT};
            font-weight: 600;
        }}
        QPushButton#SegmentButton {{
            background: {BG_CARD};
            color: {FG_HINT};
            border: 1px solid {ACCENT_BORDER};
            padding: 7px 13px;
            font-weight: 700;
        }}
        QPushButton#SegmentButton:checked {{
            background: {ACCENT_BLUE};
            color: #ffffff;
            border-color: {ACCENT_BLUE};
        }}
        QPushButton#GhostButton {{
            background: {BG_CARD};
            color: {FG_MUTED};
            border: 1px solid {ACCENT_BORDER};
            padding: 7px 13px;
            font-weight: 700;
        }}
        QPushButton#PrimaryButton {{
            background: #c2580a;
            color: #ffffff;
            border: 1px solid #c2580a;
            padding: 7px 17px;
            font-weight: 800;
        }}
        QPushButton#PrimaryButton:hover {{
            background: {ACCENT_AMBER};
        }}
        QComboBox#HeaderCombo, QLineEdit#SearchBox {{
            background: {BG_CARD};
            color: {FG_MUTED};
            border: 1px solid {ACCENT_BORDER};
            padding: 7px 12px;
            min-width: 120px;
            font-weight: 700;
        }}
        QLineEdit#SearchBox {{
            min-width: 220px;
        }}
        QFrame#TextScaleWidget {{
            background: #1a1a24;
            border: 1px solid #303040;
        }}
        QLabel#TextScaleValue {{
            color: #b0b0bc;
            font-weight: 800;
            min-width: 38px;
        }}
        QPushButton#TextScaleButton {{
            background: #111118;
            color: #888894;
            border: 1px solid #252530;
            padding: 1px 6px;
            min-width: 22px;
            max-width: 22px;
            min-height: 20px;
            max-height: 20px;
            font-weight: 900;
        }}
        QPushButton#TextScaleButton:hover {{
            background: #22222e;
            color: #d4d4dc;
            border-color: #3b5bdb;
        }}
        QSlider#TextScaleSlider {{
            min-width: 118px;
            max-width: 118px;
        }}
        QSlider#TextScaleSlider::groove:horizontal {{
            background: #1e1e28;
            height: 4px;
        }}
        QSlider#TextScaleSlider::handle:horizontal {{
            background: #6ea8fe;
            border: 1px solid #3b5bdb;
            width: 8px;
            margin: -5px 0;
        }}
        QSlider#TextScaleSlider::add-page:horizontal {{
            background: #1e1e28;
        }}
        QSlider#TextScaleSlider::sub-page:horizontal {{
            background: #3b5bdb;
        }}
        QScrollArea {{
            background: {BG_BASE};
        }}
        QFrame#GroupCard {{
            background: {BG_CARD};
            border: 1px solid {ACCENT_BORDER};
        }}
        QFrame#GroupHeader {{
            background: #14141c;
            border-bottom: 1px solid {ACCENT_DIVIDER};
        }}
        QLabel#MatchBadge {{
            padding: 5px 10px;
            font-weight: 900;
            font-size: 10pt;
        }}
        QLabel#GroupTitle {{
            color: #b0b0bc;
            font-weight: 800;
        }}
        QLabel#MetaLabel, QLabel#ConfidenceLabel {{
            color: {FG_HINT};
            font-weight: 700;
        }}
        QLabel#SavePill {{
            background: #0e2040;
            color: #5a8de0;
            border: 1px solid #1a3870;
            padding: 3px 8px;
            font-weight: 700;
        }}
        QFrame#ConfidenceTrack {{
            background: {BG_CARD_HI};
            min-width: 56px;
            max-width: 56px;
            min-height: 7px;
            max-height: 7px;
        }}
        QFrame#FileRow {{
            background: {BG_CARD};
            border-left: 2px solid {ACCENT_DIVIDER};
            border-bottom: 1px solid #1a1a24;
        }}
        QFrame#SelectedFileRow {{
            background: #101827;
            border: 2px solid {ACCENT_BLUE};
        }}
        QFrame#MissingFileRow {{
            background: #2a1116;
            border: 1px solid #9b3030;
            border-left: 2px solid #e06060;
        }}
        QPushButton#MasterButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #15151d, stop:0.48 #0f0f16, stop:1 #07070b);
            color: #383a46;
            border: 1px solid #1c1c26;
            border-left: 3px solid #252530;
            border-bottom: 2px solid #030305;
            padding: 6px 7px;
            font-family: "Segoe UI Semibold";
            font-weight: 900;
        }}
        QPushButton#MasterButton:hover {{
            color: #747684;
            border-color: #303040;
            border-left-color: #3b5bdb;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1b1b26, stop:0.52 #12121a, stop:1 #09090d);
        }}
        QPushButton#MasterButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #b7c870, stop:0.42 #7d913f, stop:1 #3f4f1f);
            color: #101407;
            border: 1px solid #c7d982;
            border-left: 3px solid #dceaa1;
            border-bottom: 2px solid #253010;
            padding-top: 5px;
            padding-bottom: 7px;
        }}
        QPushButton#MasterButton:checked:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #d3e486, stop:0.45 #91a846, stop:1 #4d6124);
        }}
        QLabel#FileNameReadOnly {{
            background: transparent;
            color: #aeb0c0;
            border: none;
            padding: 0;
            font-weight: 800;
        }}
        QLabel#FileNameReadOnly[missing="true"] {{
            color: #e06060;
        }}
        QLabel#FileTitle {{
            color: #aeb0c0;
            font-weight: 800;
        }}
        QLabel#PathText {{
            background: #171722;
            color: #747684;
            border: 1px solid #222232;
            padding: 2px 6px;
            font-size: 10pt;
            font-weight: 700;
        }}
        QLabel#MissingTitle {{
            color: #e06060;
            font-weight: 800;
        }}
        QLabel#MissingPathText {{
            background: #2a1116;
            color: #d06060;
            border: 1px solid #7a2424;
            padding: 2px 6px;
            font-size: 10pt;
            font-weight: 700;
        }}
        QLineEdit#FileRenameEditor {{
            background: #111118;
            color: #d4d4dc;
            border: 1px solid #3b5bdb;
            padding: 0 4px;
            font-size: 10pt;
            font-weight: 900;
            selection-background-color: #3b5bdb;
        }}
        QLabel#SizeChip {{
            background: #062218;
            color: #34c478;
            border: 1px solid #0f4028;
            padding: 2px 6px;
            font-family: Consolas;
            font-weight: 700;
        }}
        QLabel#HashChip, QLabel#AudioChip, QLabel#MetaChip {{
            background: #111118;
            color: #6ea8fe;
            border: 1px solid #1a1a24;
            padding: 2px 6px;
            font-family: Consolas;
            font-weight: 700;
        }}
        QLabel#MissingFlag {{
            color: #e06060;
            font-weight: 900;
            padding: 0 12px;
        }}
        QLabel#InlineImagePreview {{
            background: transparent;
            border: none;
            padding: 0;
        }}
    """)
