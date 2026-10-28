# photo-tidy

**Straighten photos with camera EXIF or a local vision model. Add captions to JPEG metadata.**

```text
SIDEWAYS PHOTO        CHECK ORIENTATION       UPRIGHT PHOTO
+-----------+         +-------------------+   +-----------+
| \         |         | EXIF rotation?    |   |     O     |
|  +---O    | ------> | yes: use EXIF     | ->|    /|\    |
| /         |         | no: local Ollama  |   |    / \    |
+-----------+         | compare 4 views   |   +-----------+
                      +-------------------+
                      unclear -> keep original

JPEG caption --------> EXIF ImageDescription + XPComment
```

Photo processing runs on your machine. The vision model is served by [Ollama](https://ollama.com)
on `localhost`; images are not sent to a cloud service. The tool comes from the Daisy photo workflow.

## Install

Requires Python 3.10+. Use a virtual environment, including with Homebrew Python on macOS:

```bash
cd /path/to/photo-tidy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ollama pull ministral-3:8b
```

Start the Ollama app or run `ollama serve`. Activate the environment with
`source .venv/bin/activate` in each new terminal. Ollama is needed only when a photo
has no usable camera rotation tag.

## Use

```bash
photo-tidy orient ~/Pictures/album --dry-run --verbose  # inspect decisions
photo-tidy orient ~/Pictures/album                    # apply them
photo-tidy orient photo.jpg --rotate 90 --dry-run      # preview a manual right turn
photo-tidy orient photo.jpg --rotate 90                # apply that turn

photo-tidy caption photo.jpg --set "Summer day at the lake"
photo-tidy caption ~/Pictures/album --map captions.json
photo-tidy caption ~/Pictures/album --show
```

`orient` accepts one photo or a folder, searched recursively. It handles JPEG and PNG.
`--rotate` applies a clockwise angle of `0`, `90`, `180`, or `270` after EXIF correction
and skips Ollama. On a folder, it rotates **every** photo by that angle.

`--verbose` shows EXIF, the model's verdict for each rotation, and any final comparison.
`unchanged` means no rotation was selected; it does not prove that the photo is upright.

| Option | Effect |
| --- | --- |
| `--model NAME` | Choose an installed vision model; default `ministral-3` (8B) |
| `--backup model` | Back up model-chosen and explicit rotations; default |
| `--backup all` | Back up every changed photo, including EXIF corrections |
| `--backup none` | Do not make backups |
| `--no-bake-exif` | Leave photos with camera rotation tags untouched |
| `--ollama-url URL` | Ollama server; default `http://localhost:11434` |

## How it decides

1. A camera EXIF rotation tag takes priority. Photo-tidy applies it to the pixels
   and resets the tag. The model is not called.
2. Otherwise, local Ollama checks the photo in four rotations. If the answers
   conflict, it compares all four views together. An uncertain answer leaves the file alone.
3. Before a model-chosen or explicit rotation, the original goes into `_originals/`.
   Use `--backup all` to save originals for EXIF corrections too.

The default vision model is `ministral-3`. You can try another image-capable model
with `--model`, for example `qwen3.5:4b` after `ollama pull qwen3.5:4b`.
Text-only `qwen3:8b` cannot inspect photos. Model accuracy varies; inspect
`--dry-run --verbose` on photos you care about.

## Captions and limits

Captions are written to JPEG EXIF `ImageDescription` as UTF-8 and to `XPComment`.
A map is either a JSON object such as `{"IMG_0001.jpg": "Kesäpäivä"}` or a two-column
CSV without a header (filename, caption). Caption changes do not re-encode pixels
or create backups.

Rotating a JPEG re-encodes it using the original compression settings, so it is
not lossless. Camera EXIF is trusted even if it is wrong. HEIC and RAW are not
supported. Other non-EXIF metadata may not survive rotation. A later change to
a file can overwrite an existing `_originals/` backup with the same name.

## Development

```bash
python -m unittest discover -s tests
```

MIT licensed.
