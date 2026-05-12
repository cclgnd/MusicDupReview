import os
import stat

try:
    from send2trash import send2trash
    TRASH_AVAILABLE = True
except Exception:
    send2trash = None
    TRASH_AVAILABLE = False


class FileActionError(RuntimeError):
    pass


def make_file_writable(path):
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except Exception:
        pass


def send_to_recycle_bin(path):
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        return False
    if not TRASH_AVAILABLE:
        raise FileActionError("Recycle Bin support is unavailable. File was not changed.")
    try:
        make_file_writable(normalized)
        send2trash(normalized)
        return True
    except Exception as exc:
        raise FileActionError(f"Recycle Bin failed. File was not changed: {exc}") from exc
