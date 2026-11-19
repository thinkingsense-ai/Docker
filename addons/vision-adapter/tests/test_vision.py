import io, json, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "image-adapter")); sys.path.insert(0, os.path.join(HERE, ".."))   # vision-adapter first: both have an adapter.py
from PIL import Image
import adapter


def jpeg(size=(2000, 1000), exif=False):
    im = Image.new("RGB", size, (200, 30, 30)); out = io.BytesIO()
    if exif:
        e = Image.Exif(); e[0x010F] = "TestCam"; im.save(out, "JPEG", exif=e)
    else: im.save(out, "JPEG")
    return out.getvalue()


def reply(text): return lambda url, body, to: {"choices": [{"message": {"content": text}}]}


class T(unittest.TestCase):
    def test_split_text(self):
        d, v = adapter.split_text("A red square.\nText: STOP")
        self.assertEqual((d, v), ("A red square.", "STOP"))
        self.assertEqual(adapter.split_text("A cat.\nText: none")[1], None)
        self.assertEqual(adapter.split_text("Just a cat.")[1], None)

    def test_prepare_resizes_and_strips_metadata(self):
        out = adapter.prepare(jpeg((3000, 1500), exif=True)); im = Image.open(io.BytesIO(out))
        self.assertEqual(max(im.size), adapter.SEND_PX); self.assertFalse(im.getexif())

    def test_prepare_flattens_transparency(self):
        im = Image.new("RGBA", (10, 10), (0, 0, 0, 0)); b = io.BytesIO(); im.save(b, "PNG")
        self.assertEqual(Image.open(io.BytesIO(adapter.prepare(b.getvalue()))).getpixel((0, 0)), (255, 255, 255))

    def test_record_success_keeps_file_details_and_adds_description(self):
        r = adapter.record(jpeg(exif=True), "a.jpg", reply("A red rectangle.\nText: none"))
        m = r["result"]["model"]
        self.assertEqual(m["description"], "A red rectangle."); self.assertIsNone(m["visibleText"]); self.assertTrue(m["experimental"])
        self.assertEqual(r["result"]["format"], "JPEG"); self.assertIn("not been benchmarked", r["notes"][0])

    def test_request_carries_an_image_and_no_exif(self):
        seen = {}
        def post(url, body, to): seen.update(url=url, body=json.loads(body)); return {"choices": [{"message": {"content": "x"}}]}
        adapter.record(jpeg(exif=True), "a.jpg", post)
        self.assertTrue(seen["url"].endswith("/v1/chat/completions"))
        part = seen["body"]["messages"][0]["content"][1]["image_url"]["url"]; self.assertTrue(part.startswith("data:image/jpeg;base64,"))
        import base64; raw = base64.b64decode(part.split(",", 1)[1]); self.assertFalse(Image.open(io.BytesIO(raw)).getexif())
        self.assertNotIn("TestCam", json.dumps(seen["body"]))

    def test_model_failure_still_returns_file_details(self):
        def boom(url, body, to): raise OSError("down")
        r = adapter.record(jpeg(), "a.jpg", boom)
        self.assertIsNone(r["result"]["model"]); self.assertEqual(r["result"]["format"], "JPEG"); self.assertTrue(any("could not describe" in n for n in r["notes"]))

    def test_empty_reply_is_a_failure_not_a_blank_description(self):
        self.assertIsNone(adapter.record(jpeg(), "a.jpg", reply("   "))["result"]["model"])

    def test_gps_is_noted_and_not_sent(self):
        im = Image.new("RGB", (50, 50)); e = Image.Exif(); g = e.get_ifd(0x8825)
        g[1] = "N"; g[2] = (37.0, 46.0, 30.0); g[3] = "W"; g[4] = (122.0, 25.0, 0.0); b = io.BytesIO(); im.save(b, "JPEG", exif=e)
        seen = {}
        def post(url, body, to): seen["b"] = body.decode(); return {"choices": [{"message": {"content": "A picture."}}]}
        r = adapter.record(b.getvalue(), "g.jpg", post)
        if r["result"]["gps"]: self.assertTrue(any("NOT sent" in n for n in r["notes"]))

    def test_manifest_says_experimental_and_accepts_pictures_only(self):
        self.assertIn("EXPERIMENTAL", adapter.MANIFEST["notes"]); self.assertTrue(adapter.accepts("x.PNG")); self.assertFalse(adapter.accepts("x.svg"))


if __name__ == "__main__": unittest.main()
