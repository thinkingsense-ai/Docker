"""python3 -m unittest discover -s addons/image-adapter/tests     (needs Pillow; skipped without it)"""
import base64, io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from PIL import Image; HAVE = True
except ImportError: HAVE = False
if HAVE:
    import adapter, images


def png(size=(800, 400), colour=(200, 30, 30), mode="RGB"):
    b = io.BytesIO(); Image.new(mode, size, colour).save(b, "PNG"); return b.getvalue()


def jpeg(gps=True):
    ex = Image.Exif(); ex[0x010F] = "Acme"; ex[0x0110] = "Cam\x07 1"; ex[0x0132] = "2026:05:01 10:00:00"
    if gps: ex.get_ifd(0x8825).update({1: "N", 2: (59.0, 54.0, 0.0), 3: "E", 4: (10.0, 45.0, 0.0)})
    b = io.BytesIO(); Image.new("RGB", (640, 480), (10, 120, 200)).save(b, "JPEG", exif=ex); return b.getvalue()


@unittest.skipUnless(HAVE, "Pillow not installed")
class T(unittest.TestCase):
    def test_png_size_colour_and_thumbnail(self):
        r = adapter.record(png(), "chart.png"); d = r["result"]
        self.assertEqual((d["format"], d["width"], d["height"], d["megapixels"]), ("PNG", 800, 400, 0.32))
        self.assertEqual(d["colours"][0]["hex"], "#c81e1e"); self.assertEqual(d["colours"][0]["share"], 1.0)
        self.assertTrue(d["thumbnail"].startswith("data:image/jpeg;base64,"))
        t = Image.open(io.BytesIO(base64.b64decode(d["thumbnail"].split(",", 1)[1]))); self.assertLessEqual(max(t.size), images.THUMB_PX); self.assertEqual(len(t.getexif()), 0)
        self.assertTrue(any("screenshot" in n for n in r["notes"]))

    def test_a_small_bright_area_is_not_merged_into_its_neighbour(self):
        im = Image.new("RGB", (400, 300), (30, 90, 160)); from PIL import ImageDraw; d = ImageDraw.Draw(im)
        d.ellipse((100, 50, 300, 200), fill=(240, 200, 40)); d.rectangle((0, 230, 400, 300), fill=(40, 140, 60))
        b = io.BytesIO(); im.save(b, "PNG"); hexes = [c["hex"] for c in adapter.record(b.getvalue(), "s.png")["result"]["colours"]]
        near = lambda h, rgb: all(abs(int(h[i:i + 2], 16) - v) < 30 for i, v in zip((1, 3, 5), rgb))
        for rgb in ((30, 90, 160), (240, 200, 40), (40, 140, 60)): self.assertTrue(any(near(h, rgb) for h in hexes), (rgb, hexes))
        self.assertTrue(all(c["share"] >= 0.02 for c in adapter.record(b.getvalue(), "s.png")["result"]["colours"]))

    def test_exif_fields_gps_and_clean_text(self):
        r = adapter.record(jpeg(), "p.jpg"); d = r["result"]
        self.assertEqual(d["exif"]["cameraMake"], "Acme"); self.assertEqual(d["exif"]["cameraModel"], "Cam 1")        # control character dropped
        self.assertEqual(d["exif"]["modifiedAt"], "2026:05:01 10:00:00")
        self.assertEqual(d["gps"], {"lat": 59.9, "lon": 10.75}); self.assertTrue(any("GPS" in n for n in r["notes"]))
        self.assertIsNone(adapter.record(jpeg(gps=False), "p.jpg")["result"]["gps"])

    def test_transparency_and_animation(self):
        self.assertTrue(adapter.record(png(mode="RGBA", colour=(1, 2, 3, 0)), "t.png")["result"]["transparent"])
        b = io.BytesIO(); f = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]; f[0].save(b, "GIF", save_all=True, append_images=f[1:], duration=50)
        r = adapter.record(b.getvalue(), "a.gif"); self.assertEqual(r["result"]["frames"], 3); self.assertTrue(any("Animated" in n for n in r["notes"]))

    def test_svg_tiff_and_junk_refused(self):
        with self.assertRaises(images.ImageError): adapter.record(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.png")
        b = io.BytesIO(); Image.new("RGB", (10, 10)).save(b, "TIFF")
        with self.assertRaises(images.ImageError): adapter.record(b.getvalue(), "x.jpg")
        with self.assertRaises(images.ImageError): adapter.record(b"\x89PNG\r\n\x1a\ngarbage", "x.png")

    def test_oversized_is_refused_before_decoding(self):
        old = images.MAX_PIXELS; images.MAX_PIXELS = 1000
        try:
            with self.assertRaises(images.ImageError): adapter.record(png((100, 100)), "big.png")
        finally: images.MAX_PIXELS = old

    def test_honest_about_not_recognising_content(self):
        r = adapter.record(png(), "a.png"); self.assertEqual(r["askPrompts"], []); self.assertFalse(adapter.MANIFEST["nonCommercial"])
        self.assertTrue(any("Nothing here recognises" in n for n in r["notes"])); self.assertIn("does not recognise", adapter.MANIFEST["notes"])

    def test_accepts(self):
        self.assertTrue(adapter.accepts("A.JPG")); self.assertTrue(adapter.accepts("x", "image/webp")); self.assertFalse(adapter.accepts("a.svg", "image/svg+xml"))


if __name__ == "__main__": unittest.main()
