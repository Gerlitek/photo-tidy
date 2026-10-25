"""Fix photo orientation conservatively.

1. If the photo carries an EXIF orientation from the camera, trust it (optionally bake it into the pixels).
2. Otherwise a local vision model (Ollama) judges the picture in four rotations, one at a time.
   The photo is rotated only if the original is judged wrong *and* exactly one rotation is judged right.
   Anything uncertain is left untouched. Wrongly rotating a correct photo is worse than missing a sideways one.

Photos never leave the machine; the only network call is to the local Ollama server.
"""
import base64
import io
import json
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, JpegImagePlugin

from photo_tidy.exif import read_caption, write_caption

SUFFIXES = {".jpg", ".jpeg", ".png"}
ORIENTATION = 0x0112
BACKUP_DIR = "_originals"
ROTATIONS = (0, 90, 180, 270)               # degrees clockwise
_TRANSPOSE = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}

SCHEMA = {"type": "object", "properties": {"upright": {"type": "boolean"}}, "required": ["upright"]}
PROMPT = ("Is this photo shown upright, the way a person would normally view it? Upright means people and animals "
          "have their heads at the top and their feet or the floor at the bottom, the sky is at the top, and any text "
          "reads left to right. Answer true only if the photo is clearly upright, false if it is sideways or "
          "upside down.")


@dataclass
class Result:
    file: str
    exif_tag: int
    degrees: int
    changed: bool
    reason: str | None        # "model" | "exif" | None


def rotate(img: Image.Image, degrees_cw: int) -> Image.Image:
    return img if degrees_cw == 0 else img.transpose(_TRANSPOSE[degrees_cw])


def decide(upright: dict[int, bool]) -> int:
    """Pick the clockwise rotation to apply, or 0 when unsure."""
    if upright.get(0):
        return 0
    good = [d for d in (90, 180, 270) if upright.get(d)]
    return good[0] if len(good) == 1 else 0


def choose_rotation(img: Image.Image, is_upright: Callable[[Image.Image], bool]) -> int:
    return decide({d: is_upright(rotate(img, d)) for d in ROTATIONS})


class OllamaVision:
    """Ask a local Ollama vision model whether a picture is upright."""

    def __init__(self, model: str = "ministral-3", url: str = "http://localhost:11434", size: int = 512,
                 timeout: int = 300):
        self.model, self.url, self.size, self.timeout = model, url.rstrip("/"), size, timeout

    def is_upright(self, img: Image.Image) -> bool:
        small = img.convert("RGB")
        small.thumbnail((self.size, self.size))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=85)
        body = json.dumps({
            "model": self.model, "stream": False, "think": False, "format": SCHEMA,
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(buf.getvalue()).decode()]}],
            "options": {"temperature": 0},
        }).encode()
        req = urllib.request.Request(self.url + "/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return bool(json.loads(json.loads(r.read())["message"]["content"])["upright"])


def fix_file(path: Path, is_upright: Callable[[Image.Image], bool], *, dry_run: bool = False,
             bake_exif: bool = True, backup: str = "model") -> Result:
    """Fix one photo. backup: "model" (copy the original only for model-chosen rotations), "all" or "none".

    The caption (EXIF ImageDescription) survives rotation. The original is copied to ``_originals/`` next to the file.
    """
    path = Path(path)
    caption = read_caption(path)
    with Image.open(path) as src:
        fmt, exif = src.format, src.getexif()
        tag = exif.get(ORIENTATION, 1)
        qtables = getattr(src, "quantization", None)
        subsampling = JpegImagePlugin.get_sampling(src) if fmt == "JPEG" else None
        base = ImageOps.exif_transpose(src)          # what a photo viewer would show
        base.load()
        deg = 0 if tag != 1 else choose_rotation(base, is_upright)     # camera EXIF is trusted, no model call
        if deg == 0 and (tag == 1 or not bake_exif):
            return Result(path.name, tag, 0, False, None)
        result = Result(path.name, tag, deg, True, "model" if deg else "exif")
        if dry_run:
            return result
        final = rotate(base, deg)
        exif[ORIENTATION] = 1                        # pixels are upright now; other EXIF tags are kept
        kwargs: dict = {}
        if fmt in ("JPEG", "PNG"):
            kwargs["exif"] = exif.tobytes()
        if fmt == "JPEG":                            # same compression as the original: no quality loss
            kwargs.update(qtables=qtables, subsampling=subsampling)
        if backup == "all" or (backup == "model" and deg != 0):
            folder = path.parent / BACKUP_DIR
            folder.mkdir(exist_ok=True)
            shutil.copy2(path, folder / path.name)
        final.save(path, fmt, **kwargs)
    if caption:                                      # Pillow cannot round-trip UTF-8 EXIF text
        write_caption(path, caption)
    return result


def fix_folder(folder: Path, is_upright: Callable[[Image.Image], bool], **kwargs) -> list[Result]:
    folder = Path(folder)
    if folder.is_file():
        return [fix_file(folder, is_upright, **kwargs)]
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in SUFFIXES and BACKUP_DIR not in p.parts)
    return [fix_file(p, is_upright, **kwargs) for p in files]
