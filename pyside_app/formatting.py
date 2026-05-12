from PySide6.QtGui import QColor


def format_bytes(size):
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


def decision_label(decision):
    return {
        "master": "Keep",
        "delete": "Trash",
        "deleted": "Deleted",
        "missing": "Missing",
        "protected": "Protected",
        "ignored": "Ignored",
        "": "Unreviewed",
    }.get(decision or "", decision or "Unreviewed")


def decision_color(decision):
    return QColor({
        "master": "#14532d",
        "delete": "#7f1d1d",
        "deleted": "#991b1b",
        "missing": "#991b1b",
        "protected": "#1e3a8a",
        "ignored": "#3f3f46",
        "": "#27272a",
    }.get(decision or "", "#27272a"))
