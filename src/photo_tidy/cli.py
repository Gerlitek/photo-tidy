"""Command line interface: ``photo-tidy orient`` and ``photo-tidy caption``."""
import argparse
import csv
import json
import sys
import urllib.error
from pathlib import Path

from photo_tidy.exif import JPEG_SUFFIXES, read_caption, write_caption
from photo_tidy.orient import OllamaVision, fix_folder


def load_caption_map(path: Path) -> dict[str, str]:
    """JSON {"file.jpg": "caption"} or CSV with two columns (filename, caption)."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with open(path, newline="", encoding="utf-8") as f:
        return {row[0]: row[1] for row in csv.reader(f) if len(row) >= 2}


def cmd_orient(args) -> int:
    vision = OllamaVision(args.model, args.ollama_url)
    if args.verbose:
        print(f"Model: {args.model}; Ollama: {args.ollama_url}", flush=True)
    try:
        results = fix_folder(Path(args.path), vision.is_upright, dry_run=args.dry_run,
                             bake_exif=not args.no_bake_exif, backup=args.backup, rotation=args.rotate,
                             pick_panel=vision.pick_panel)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        print(f"Cannot reach Ollama at {args.ollama_url} ({e}). Start it with: ollama serve", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Cannot determine orientation: {e}", file=sys.stderr)
        return 2
    for r in results:
        if args.verbose:
            if args.rotate is not None:
                detail = f"explicit rotation {args.rotate}° clockwise; model not called"
            elif r.upright is None:
                detail = "camera EXIF trusted; model not called"
            else:
                votes = ", ".join(f"{d}°={'upright' if yes else 'wrong way up'}" for d, yes in r.upright.items())
                good = sum(r.upright.values())
                decision = ("original judged upright" if good == 1 and r.upright[0] else
                            "ambiguous: multiple orientations judged upright" if good > 1 else
                            "uncertain: no orientation judged upright" if good == 0 else
                            f"rotate {r.degrees}° clockwise")
                detail = f"{votes}; {decision}"
                if r.panel_decision is not None:
                    detail += f"; four-panel comparison selected {r.panel_decision}° clockwise"
            print(f"{r.file}: EXIF {r.exif_tag}; {detail}")
        if r.changed:
            what = f"rotate {r.degrees}° ({r.reason})" if r.reason in ("model", "manual") else "apply camera EXIF orientation"
            print(f"{r.file}: {what}" + ("  [dry run]" if args.dry_run else ""))
    n_model = sum(r.reason == "model" for r in results)
    n_exif = sum(r.reason == "exif" for r in results)
    n_manual = sum(r.reason == "manual" for r in results)
    manual = f"{n_manual} rotated by explicit angle, " if args.rotate is not None else ""
    print(f"{len(results)} photos checked: {n_model} rotated by the model, {manual}{n_exif} EXIF orientation baked in, "
          f"{len(results) - n_model - n_exif - n_manual} unchanged" + (" (dry run, nothing written)" if args.dry_run else ""))
    return 0


def _jpegs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.suffix.lower() in JPEG_SUFFIXES)


def cmd_caption(args) -> int:
    path = Path(args.path)
    if args.show:
        for p in _jpegs(path):
            print(f"{p.name}: {read_caption(p) or '(no caption)'}")
        return 0
    if args.set is not None:
        ok = [write_caption(p, args.set) for p in _jpegs(path)]
    else:
        mapping = load_caption_map(Path(args.map))
        ok = [write_caption(p, mapping[p.name]) for p in _jpegs(path) if p.name in mapping]
    print(f"{sum(ok)} captions written" + (f", {len(ok) - sum(ok)} failed" if not all(ok) else ""))
    return 0 if all(ok) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="photo-tidy", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("orient", help="fix photo orientation (EXIF first, local vision model otherwise)")
    o.add_argument("path", help="a photo or a folder (searched recursively)")
    o.add_argument("--dry-run", action="store_true", help="show decisions, change nothing")
    o.add_argument("--verbose", action="store_true", help="show EXIF and the model's verdict for each rotation")
    o.add_argument("--rotate", type=int, choices=(0, 90, 180, 270),
                   help="apply this clockwise angle after EXIF, without asking Ollama; applies to every input photo")
    o.add_argument("--model", default="ministral-3", help="Ollama vision model (default: %(default)s)")
    o.add_argument("--ollama-url", default="http://localhost:11434")
    o.add_argument("--no-bake-exif", action="store_true", help="leave photos that only need their EXIF orientation alone")
    o.add_argument("--backup", choices=["model", "all", "none"], default="model",
                   help="copy originals to _originals/ (default: model-chosen and explicit rotations)")
    o.set_defaults(func=cmd_orient)

    c = sub.add_parser("caption", help="read or write UTF-8 captions in EXIF")
    c.add_argument("path", help="a JPEG or a folder")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true", help="print captions")
    g.add_argument("--set", metavar="TEXT", help="write TEXT as the caption of every JPEG at PATH")
    g.add_argument("--map", metavar="FILE", help="JSON or CSV mapping file name -> caption")
    c.set_defaults(func=cmd_caption)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
