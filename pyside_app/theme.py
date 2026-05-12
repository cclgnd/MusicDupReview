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
    """)
