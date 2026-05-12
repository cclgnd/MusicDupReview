import hashlib
import os
import re
import unicodedata

try:
    from PIL import Image
    IMAGE_AVAILABLE = True
except Exception:
    Image = None
    IMAGE_AVAILABLE = False

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
CHUNK = 1024 * 1024


def category_for_extension(ext):
    ext = (ext or "").lower()
    if ext in IMAGE_EXTS:
        return "imagen"
    if ext in {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"}:
        return "audio"
    if ext in {".m3u", ".m3u8", ".pls", ".cue"}:
        return "lista"
    if ext in {".txt", ".nfo", ".sfv", ".url", ".ini", ".log"}:
        return "info"
    return "otro"


def md5_file(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def audio_md5_file(path, ext):
    if ext == ".mp3":
        return audio_md5_mp3(path)
    return md5_file(path)


def audio_md5_mp3(path):
    size = os.path.getsize(path)
    if size < 10:
        return None
    start = 0
    end = size
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        head = handle.read(10)
        if head[:3] == b"ID3":
            tag_size = (
                (head[6] << 21) |
                (head[7] << 14) |
                (head[8] << 7) |
                head[9]
            )
            start = tag_size + 10
        if size >= 128:
            handle.seek(size - 128)
            if handle.read(3) == b"TAG":
                end = size - 128
        if end <= start:
            return None
        handle.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def normalize_name(name):
    text = os.path.splitext(name or "")[0].lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\b(19|20)\d{2}\b", "", text)
    text = re.sub(r"\b\d{1,3}\s*kbps\b", "", text)
    text = re.sub(r"[\(\[\{].*?[\)\]\}]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"^\d{1,3}\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def image_fingerprint(path):
    if not IMAGE_AVAILABLE:
        return None, None, None
    try:
        with Image.open(path) as img:
            width, height = img.size
            small = img.convert("L").resize((8, 8))
            values = list(small.getdata())
            avg = sum(values) / len(values)
            bits = "".join("1" if value >= avg else "0" for value in values)
            ahash = f"{int(bits, 2):016x}"
            return width, height, ahash
    except Exception:
        return None, None, None
