"""Describes a JPEG, PNG, GIF or WebP: size, format, selected camera/date/location metadata, dominant colours and a small thumbnail re-encoded by us.
No model looks at the picture: nothing here says what is IN it. Pillow (MIT-CMU) decodes; SVG, TIFF and BMP are not accepted."""
import base64, io
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATS = ["JPEG", "PNG", "GIF", "WEBP"]
MAX_PIXELS, THUMB_PX, MAX_TEXT = 50_000_000, 192, 80
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
TAGS = {0x010F: "cameraMake", 0x0110: "cameraModel", 0x0131: "software", 0x9003: "takenAt", 0x0132: "modifiedAt"}


class ImageError(ValueError):
    pass


def clean(v): return "".join(ch for ch in str(v) if ch.isprintable()).strip()[:MAX_TEXT]


def deg(vals, ref):
    try:
        d = float(vals[0]) + float(vals[1]) / 60 + float(vals[2]) / 3600
        return round(-d if ref in ("S", "W") else d, 5)
    except (TypeError, ValueError, IndexError, ZeroDivisionError): return None


def exif_of(im):
    out, gps = {}, None
    try: ex = im.getexif()
    except Exception: return out, gps
    for tag, name in TAGS.items():
        v = ex.get(tag)
        if v is None and tag == 0x9003:
            v = ex.get_ifd(0x8769).get(0x9003) if hasattr(ex, "get_ifd") else None
        if v is not None and clean(v): out[name] = clean(v)
    try:
        g = ex.get_ifd(0x8825)
        if g and g.get(2) and g.get(4):
            lat, lon = deg(g[2], g.get(1)), deg(g[4], g.get(3))
            if lat is not None and lon is not None: gps = {"lat": lat, "lon": lon}
    except Exception: pass
    return out, gps


def colours(im):
    small = ImageOps.exif_transpose(im).convert("RGB")
    small.thumbnail((64, 64))
    q = small.quantize(colors=5, method=Image.Quantize.MAXCOVERAGE)       # median cut merged a small bright area into a big neighbour in a test picture
    pal, counts = q.getpalette(), sorted(q.getcolors(), reverse=True)
    total = sum(n for n, _ in counts)
    return [{"hex": "#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]), "share": round(n / total, 2)} for n, i in counts if n / total >= 0.02]


def thumbnail(im):
    t = ImageOps.exif_transpose(im).convert("RGB")      # re-encoded: no metadata and none of the uploaded bytes are passed on
    t.thumbnail((THUMB_PX, THUMB_PX))
    b = io.BytesIO(); t.save(b, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def has_transparency(im):
    """True only when some pixel is actually see-through: an RGBA file that is fully opaque (a canvas export, say) has an alpha channel but no transparent area."""
    if im.mode in ("RGBA", "LA"): return im.getchannel("A").getextrema()[0] < 255
    return "transparency" in im.info


def describe(data):
    try:
        im = Image.open(io.BytesIO(data), formats=FORMATS)
        w, h = im.size
        if w * h > MAX_PIXELS: raise ImageError("The picture is too large to read safely (over %d million pixels)." % (MAX_PIXELS // 1_000_000))
        fmt, frames = im.format, getattr(im, "n_frames", 1)
        ex, gps = exif_of(im)
        im.load()
    except ImageError: raise
    except Image.DecompressionBombError: raise ImageError("The picture is too large to read safely.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError): raise ImageError("That is not a JPEG, PNG, GIF or WebP picture this adapter can read.")
    r = {"format": fmt, "width": w, "height": h, "megapixels": round(w * h / 1e6, 2), "frames": frames,
         "transparent": has_transparency(im), "exif": ex, "gps": gps,
         "colours": colours(im), "thumbnail": thumbnail(im)}
    return r
