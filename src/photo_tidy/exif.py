"""EXIF caption helpers that keep non-ASCII text intact (Pillow would turn it into '?')."""
import re
import unicodedata
from pathlib import Path

JPEG_SUFFIXES = {".jpg", ".jpeg"}


def read_caption(path: Path | str) -> str | None:
    """Return the EXIF ImageDescription (UTF-8) of a JPEG, or None."""
    try:
        import piexif
        raw = piexif.load(str(path))["0th"].get(piexif.ImageIFD.ImageDescription)
        return raw.decode("utf-8") if raw else None
    except Exception:
        return None


def write_caption(path: Path | str, caption: str) -> bool:
    """Write a caption into a JPEG's EXIF (ImageDescription as UTF-8, and XPComment for Windows).

    The image data is not re-encoded and other EXIF tags are kept. Some cameras embed a preview larger than
    64 kB, which piexif refuses to rewrite; in that case only the embedded preview is dropped.
    Returns False if the file is not a JPEG or the write failed.
    """
    path = Path(path)
    if not caption or path.suffix.lower() not in JPEG_SUFFIXES:
        return False
    try:
        import piexif
        try:
            exif = piexif.load(str(path))
        except Exception:
            exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif["0th"][piexif.ImageIFD.ImageDescription] = caption.encode("utf-8")
        exif["0th"][piexif.ImageIFD.XPComment] = caption.encode("utf-16le")
        try:
            blob = piexif.dump(exif)
        except ValueError:
            exif["thumbnail"], exif["1st"] = None, {}
            blob = piexif.dump(exif)
        piexif.insert(blob, str(path))
        return True
    except Exception:
        return False


def slugify(text: str, maxlen: int = 40) -> str:
    """ASCII filename fragment from a caption: 'Hiekkalaatikko & Äänekäs päivä!' -> 'hiekkalaatikko-aanekas-paiva'."""
    t = (text or "").lower().replace("ä", "a").replace("ö", "o").replace("å", "a")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:maxlen].strip("-")
