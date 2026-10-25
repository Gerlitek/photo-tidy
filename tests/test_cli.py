import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from photo_tidy import cli
from photo_tidy.exif import read_caption
from test_exif import make_jpeg


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class Caption(unittest.TestCase):
    def test_set_show_and_map(self):
        d = Path(tempfile.mkdtemp())
        a, b = make_jpeg(d, "a.jpg"), make_jpeg(d, "b.jpg")
        self.assertEqual(run("caption", str(d), "--set", "Yhteinen teksti")[0], 0)
        self.assertEqual((read_caption(a), read_caption(b)), ("Yhteinen teksti",) * 2)
        (d / "map.json").write_text(json.dumps({"a.jpg": "Ääkköset A"}), encoding="utf-8")
        (d / "map.csv").write_text("b.jpg,Teksti B\n", encoding="utf-8")
        run("caption", str(d), "--map", str(d / "map.json"))
        run("caption", str(d), "--map", str(d / "map.csv"))
        self.assertEqual((read_caption(a), read_caption(b)), ("Ääkköset A", "Teksti B"))
        code, out = run("caption", str(a), "--show")
        self.assertIn("a.jpg: Ääkköset A", out)


class Orient(unittest.TestCase):
    def test_dry_run_summary_with_stubbed_model(self):
        d = Path(tempfile.mkdtemp())
        make_jpeg(d, "a.jpg")
        with mock.patch.object(cli, "OllamaVision") as vision:
            vision.return_value.is_upright = lambda img: True
            code, out = run("orient", str(d), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("1 photos checked", out)
        self.assertIn("dry run", out)


if __name__ == "__main__":
    unittest.main()
