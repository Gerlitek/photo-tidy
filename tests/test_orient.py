import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import piexif
from PIL import Image

from photo_tidy.exif import read_caption, write_caption
from photo_tidy.orient import BACKUP_DIR, choose_rotation, decide, fix_file, fix_folder, rotate


def make(directory, tag=1, name="a.jpg"):
    """40x20 photo with a red marker in the top-left corner and a Make tag."""
    img = Image.new("RGB", (40, 20), "white")
    for x in range(6):
        for y in range(6):
            img.putpixel((x, y), (255, 0, 0))
    exif = {"0th": {piexif.ImageIFD.Make: b"Camera", piexif.ImageIFD.Orientation: tag},
            "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
    p = Path(directory) / name
    img.save(p, "JPEG", exif=piexif.dump(exif))
    return p


def says(*answers):
    """Stub for the vision model: answers for 0°, 90°, 180°, 270° in order, per photo."""
    it = iter(answers)
    return lambda img: next(it)


NEVER = lambda img: (_ for _ in ()).throw(AssertionError("the model must not be asked"))


class Decision(unittest.TestCase):
    def test_conservative(self):
        self.assertEqual(decide({0: True, 90: False, 180: False, 270: False}), 0)
        self.assertEqual(decide({0: True, 180: True}), 0)                       # original judged fine -> untouched
        self.assertEqual(decide({0: False, 90: False, 180: True, 270: False}), 180)
        self.assertEqual(decide({0: False, 90: True, 180: True, 270: False}), 0)   # ambiguous -> untouched
        self.assertEqual(decide({0: False, 90: False, 180: False, 270: False}), 0)

    def test_choose_rotation_asks_four_orientations(self):
        self.assertEqual(choose_rotation(Image.new("RGB", (8, 4)), says(False, False, True, False)), 180)

    def test_rotate_is_clockwise(self):
        img = Image.new("RGB", (4, 2))
        img.putpixel((0, 0), (255, 0, 0))
        out = rotate(img, 90)
        self.assertEqual(out.size, (2, 4))
        self.assertEqual(out.getpixel((1, 0)), (255, 0, 0))        # top-left moves to top-right


class FixFile(unittest.TestCase):
    def test_upright_photo_is_byte_identical(self):
        p = make(tempfile.mkdtemp())
        before = p.read_bytes()
        r = fix_file(p, says(True, False, False, False))
        self.assertFalse(r.changed)
        self.assertEqual(p.read_bytes(), before)

    def test_model_rotation_keeps_exif_and_caption_and_makes_backup(self):
        p = make(tempfile.mkdtemp())
        write_caption(p, "Kesäpäivä ääkköset")
        before = p.read_bytes()
        r = fix_file(p, says(False, True, False, False))           # 90° clockwise
        self.assertEqual((r.changed, r.reason, r.degrees), (True, "model", 90))
        with Image.open(p) as im:
            self.assertEqual(im.size, (20, 40))
            self.assertEqual(im.getexif()[0x0112], 1)
            self.assertGreater(im.convert("RGB").getpixel((17, 2))[0], 200)       # marker top-left -> top-right
        self.assertEqual(piexif.load(str(p))["0th"][piexif.ImageIFD.Make], b"Camera")
        self.assertEqual(read_caption(p), "Kesäpäivä ääkköset")
        self.assertEqual((p.parent / BACKUP_DIR / "a.jpg").read_bytes(), before)

    def test_camera_exif_is_trusted_without_asking_the_model(self):
        p = make(tempfile.mkdtemp(), tag=6)
        r = fix_file(p, NEVER)
        self.assertEqual((r.changed, r.reason), (True, "exif"))
        with Image.open(p) as im:
            self.assertEqual(im.size, (20, 40))
            self.assertEqual(im.getexif()[0x0112], 1)
        self.assertFalse((p.parent / BACKUP_DIR).exists())         # exif bake needs no backup by default

    def test_no_bake_leaves_exif_photos_alone(self):
        p = make(tempfile.mkdtemp(), tag=6)
        before = p.read_bytes()
        self.assertFalse(fix_file(p, NEVER, bake_exif=False).changed)
        self.assertEqual(p.read_bytes(), before)

    def test_backup_policies(self):
        for policy, exif_backup, model_backup in (("model", False, True), ("all", True, True), ("none", False, False)):
            a = make(tempfile.mkdtemp(), tag=6)
            fix_file(a, NEVER, backup=policy)
            b = make(tempfile.mkdtemp())
            fix_file(b, says(False, False, True, False), backup=policy)
            self.assertEqual((a.parent / BACKUP_DIR).exists(), exif_backup, policy)
            self.assertEqual((b.parent / BACKUP_DIR).exists(), model_backup, policy)

    def test_dry_run_changes_nothing(self):
        p = make(tempfile.mkdtemp())
        before = p.read_bytes()
        r = fix_file(p, says(False, False, True, False), dry_run=True)
        self.assertTrue(r.changed)
        self.assertEqual(p.read_bytes(), before)
        self.assertFalse((p.parent / BACKUP_DIR).exists())

    def test_folder_run_skips_the_backup_folder(self):
        d = Path(tempfile.mkdtemp())
        make(d, name="a.jpg")
        (d / BACKUP_DIR).mkdir()
        make(d / BACKUP_DIR, name="old.jpg")
        results = fix_folder(d, lambda img: True)
        self.assertEqual([r.file for r in results], ["a.jpg"])


if __name__ == "__main__":
    unittest.main()
