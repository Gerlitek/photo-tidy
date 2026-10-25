# photo-tidy

Two small chores for a photo archive, done **locally**: fix photos that are sideways or upside down, and keep
captions inside the files (including `ä`, `ö`, `å` and other non-ASCII text).

- No cloud, no accounts. The only network call is to your own [Ollama](https://ollama.com) server on `localhost`.
- Conservative by design: a photo is only rotated when the evidence is clear. Uncertain photos are left alone.

## Install

```bash
pip install .            # Python 3.10+, installs Pillow and piexif
ollama pull ministral-3  # any Ollama vision model works; only needed for photos without camera orientation
```

## Usage

```bash
photo-tidy orient ~/Pictures/album --dry-run   # show what would change, write nothing
photo-tidy orient ~/Pictures/album             # do it

photo-tidy caption photo.jpg --set "Summer day at the lake"
photo-tidy caption ~/Pictures/album --map captions.json   # {"IMG_0001.jpg": "Caption", ...} or a CSV
photo-tidy caption ~/Pictures/album --show
```

`orient` options: `--model`, `--ollama-url`, `--no-bake-exif`, `--backup {model,all,none}`.

## How orientation is decided

1. **Camera EXIF first.** If a photo has an EXIF orientation, it is trusted (no model call). The rotation is baked into
   the pixels and the tag is reset, so the photo is upright in viewers that ignore EXIF too.
   Use `--no-bake-exif` to leave such photos untouched, since most viewers already show them correctly.
2. **Otherwise a vision model judges the photo in four rotations**, one at a time ("is this upright?").
   The photo is rotated only if the original is judged wrong **and exactly one** rotation is judged right.
   Contradictory or uncertain answers mean no change.
3. Everything else is preserved: other EXIF tags stay, JPEGs are re-saved with the original quantization tables and
   subsampling (no extra quality loss), and the caption survives the rotation.
4. By default the original is copied to `_originals/` only when the *model* chose the rotation, because that is the
   only change that could be wrong. Camera-EXIF baking is deterministic and needs no backup (`--backup all` to keep one).

Why so careful? In real use a single "rotate" verdict on a correct photo is much worse than missing a sideways one,
and small vision models are not reliable enough to act on a single answer.

## Captions

EXIF `ImageDescription` is written as **UTF-8** (Pillow would silently turn non-ASCII characters into `?`), plus the
Windows `XPComment` field. The image data is not re-encoded. Cameras sometimes embed a preview larger than 64 kB,
which `piexif` refuses to rewrite; in that case only the embedded preview is dropped and all other tags are kept.

## Limits

- Captions are written to JPEG only. PNG and others are rotated but not captioned.
- A vision model can still be wrong about unusual scenes (macro, abstract, overhead shots). Run `--dry-run` first on
  an archive you care about, and keep backups.

## Development

```bash
pip install -e .
python -m unittest discover -s tests     # no Ollama needed: the model is stubbed
```

MIT licensed.
