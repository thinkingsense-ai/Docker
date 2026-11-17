"""An image (JPEG, PNG, GIF, WebP) seen as a thinking-layer adapter (docs/agency-spec.md section 4). Describes the file; keeps nothing; no model sees the picture."""
import images

EXTS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
MIMES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_BYTES = 15_000_000
MANIFEST = {
    "id": "image-describe", "title": "Pictures (JPEG, PNG, GIF, WebP)", "kind": "image", "version": "1",
    "accepts": {"extensions": EXTS, "mime": MIMES}, "maxBytes": MAX_BYTES, "nonCommercial": False,
    "licence": "Decoded with Pillow (MIT-CMU licence); no model and no third-party data; nothing is sent anywhere.",
    "notes": "Describes the file only (size, camera and date metadata, colours, a small thumbnail). It does not recognise or classify what is in the picture, and the picture is not loaded into any data source or index, so the Server cannot answer questions about it.",
}


def accepts(name, mime=None):
    n = (name or "").lower()
    return any(n.endswith(e) for e in EXTS) or (mime or "").split(";")[0].strip().lower() in MIMES


def record(data, name):
    d = images.describe(data); d["name"] = name
    notes = ["The picture was described only. Nothing here recognises what is in it, and it is not in any Server data source, so questions about it cannot be answered yet."]
    if d["gps"]: notes.append("The file carries a GPS location (%s, %s). It is shown to you only and is not kept after the record expires; check before sharing the original." % (d["gps"]["lat"], d["gps"]["lon"]))
    if d["frames"] > 1: notes.append("Animated: %d frames; the thumbnail shows the first." % d["frames"])
    if d["format"] == "PNG" and not d["exif"] and d["width"] > 600 and d["height"] > 300: notes.append("No camera metadata: this may be a screenshot, a chart or an export rather than a photograph.")
    notes.append("The thumbnail is re-encoded by the adapter; the original bytes are not kept.")
    return {"result": d, "notes": notes, "licence": MANIFEST["licence"], "askPrompts": []}
