import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import piexif
from PIL import Image

from photo_tidy.exif import read_caption, slugify, write_caption


def make_jpeg(directory, name="a.jpg", tags=None):
    p = Path(directory) / name
    exif = {"0th": tags or {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
    Image.new("RGB", (16, 8), "white").save(p, "JPEG", exif=piexif.dump(exif))
    return p


class Captions(unittest.TestCase):
    def test_utf8_caption_roundtrip_and_other_tags_kept(self):
        p = make_jpeg(tempfile.mkdtemp(), tags={piexif.ImageIFD.Make: b"Camera"})
        self.assertTrue(write_caption(p, "Kesäpäivä ääkköset"))
        self.assertEqual(read_caption(p), "Kesäpäivä ääkköset")
        self.assertEqual(piexif.load(str(p))["0th"][piexif.ImageIFD.Make], b"Camera")

    def test_windows_xpcomment_is_written_too(self):
        p = make_jpeg(tempfile.mkdtemp())
        write_caption(p, "Öljy")
        self.assertEqual(bytes(piexif.load(str(p))["0th"][piexif.ImageIFD.XPComment]).decode("utf-16le"), "Öljy")

    def test_oversized_embedded_thumbnail_is_dropped_not_fatal(self):
        p = make_jpeg(tempfile.mkdtemp(), tags={piexif.ImageIFD.Make: b"Camera"})
        real_dump, real_load = piexif.dump, piexif.load

        def picky_dump(d):                      # piexif refuses thumbnails above 64 kB
            if d.get("thumbnail"):
                raise ValueError("Given thumbnail is too large. max 64kB")
            return real_dump(d)

        with mock.patch.object(piexif, "dump", picky_dump), \
                mock.patch.object(piexif, "load", lambda f: {**real_load(f), "thumbnail": b"x" * 10}):
            self.assertTrue(write_caption(p, "Ääkköset säilyvät"))
        self.assertEqual(read_caption(p), "Ääkköset säilyvät")
        self.assertEqual(piexif.load(str(p))["0th"][piexif.ImageIFD.Make], b"Camera")

    def test_non_jpeg_or_empty_caption_is_refused(self):
        d = Path(tempfile.mkdtemp())
        Image.new("RGB", (4, 4)).save(d / "a.png")
        self.assertFalse(write_caption(d / "a.png", "x"))
        self.assertFalse(write_caption(make_jpeg(d), ""))
        self.assertIsNone(read_caption(d / "missing.jpg"))

    def test_slugify_has_no_umlauts_or_symbols(self):
        self.assertEqual(slugify("Hiekkalaatikko & Äänekäs päivä!"), "hiekkalaatikko-aanekas-paiva")
        self.assertEqual(slugify("  --  "), "")
        self.assertLessEqual(len(slugify("a" * 100)), 40)


if __name__ == "__main__":
    unittest.main()
