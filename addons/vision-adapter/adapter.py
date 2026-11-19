"""Optional picture adapter that asks a LOCAL Gemma 4 E4B (llama-server sidecar, mmproj) what a picture shows. EXPERIMENTAL and OFF by default.
Everything image-adapter reports (size, EXIF, colours, thumbnail) is kept; a model-written description is added. Nothing leaves the host: the only
call is to GEMMA_URL, which must be a service on the same compose network."""
import base64, io, json, os, time, urllib.request
import images   # copied from addons/image-adapter at build time

EXTS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
MIMES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_BYTES = 15_000_000
SEND_PX = 1024            # longest side sent to the model; keeps tokens and time bounded
GEMMA_URL = os.environ.get("GEMMA_URL", "http://gemma-model:8090")
MODEL_NAME = "gemma-4-E4B-it (Q4_0, Apache-2.0 per its card)"
PROMPT = ("Describe this picture in two or three plain sentences. Then, on a new line starting with 'Text:', copy any text you can read in it exactly, "
          "or write 'Text: none'. Do not guess who anyone is. If you are unsure, say so.")
MANIFEST = {
    "id": "image-vision", "title": "Pictures (JPEG, PNG, GIF, WebP) with a local model description", "kind": "image", "version": "1",
    "accepts": {"extensions": EXTS, "mime": MIMES}, "maxBytes": MAX_BYTES, "nonCommercial": False,
    "licence": "Decoded with Pillow (MIT-CMU). Description by Gemma 4 E4B running in a local container (Apache-2.0 per its model card; the separate licence page has not been read by counsel). Nothing is sent to a hosted service.",
    "notes": "EXPERIMENTAL. The description is written by a small model and has not been benchmarked: it can be wrong, miss text, or invent detail. Treat it as a hint, not a fact. Use the plain image adapter if you do not want a model to look at the picture."}


def accepts(name, mime=None):
    n = (name or "").lower()
    return any(n.endswith(e) for e in EXTS) or (mime or "").split(";")[0].strip().lower() in MIMES


def prepare(data):
    """JPEG bytes, longest side at most SEND_PX, metadata stripped: what the model is shown."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)); im.seek(0)
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255)); im = im.convert("RGBA"); bg.paste(im, mask=im.split()[3]); im = bg
    else: im = im.convert("RGB")
    im.thumbnail((SEND_PX, SEND_PX)); out = io.BytesIO(); im.save(out, "JPEG", quality=85); return out.getvalue()


def ask_model(jpeg, post=None, timeout=600):
    """(text, seconds). `post` is injectable for tests: post(url, body_bytes, timeout) -> parsed JSON."""
    body = json.dumps({"messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}]}],
        "temperature": 0.2, "top_p": 0.95, "top_k": 64, "max_tokens": 400}).encode()
    t0 = time.time()
    if post is None:
        def post(url, b, to):
            req = urllib.request.Request(url, b, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=to) as r: return json.load(r)
    reply = post(GEMMA_URL.rstrip("/") + "/v1/chat/completions", body, timeout)
    text = (((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return text, round(time.time() - t0, 1)


def split_text(raw):
    """(description, visible_text or None) from the model's reply."""
    desc, vis = [], None
    for line in raw.splitlines():
        if line.strip().lower().startswith("text:"): vis = line.split(":", 1)[1].strip()
        else: desc.append(line)
    d = " ".join(x.strip() for x in desc if x.strip())
    return d, (None if (vis or "").lower() in ("", "none", "none.") else vis)


def record(data, name, post=None):
    d = images.describe(data); d["name"] = name
    notes = ["The description below was written by a small local model and has not been benchmarked. It can be wrong or miss text."]
    try:
        raw, secs = ask_model(prepare(data), post)
        desc, vis = split_text(raw)
        if not desc: raise ValueError("empty reply")
        d["model"] = {"name": MODEL_NAME, "description": desc, "visibleText": vis, "seconds": secs, "experimental": True}
    except Exception as e:
        d["model"] = None
        notes.append("The model could not describe this picture (%s), so only the file details are shown." % type(e).__name__)
    if d["gps"]: notes.append("The file carries a GPS location (%s, %s). It is shown to you only and was NOT sent to the model; check before sharing the original." % (d["gps"]["lat"], d["gps"]["lon"]))
    if d["frames"] > 1: notes.append("Animated: %d frames; only the first was shown to the model." % d["frames"])
    notes.append("The picture sent to the model was re-encoded without metadata and not kept; the original bytes are not kept either.")
    return {"result": d, "notes": notes, "licence": MANIFEST["licence"], "askPrompts": []}
