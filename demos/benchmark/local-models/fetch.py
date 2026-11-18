"""Downloads model files named in models.json into a directory, and refuses anything that is not exactly what the manifest pins.

  python3 fetch.py <model-id> [<model-id> ...] [--dir DIR] [--vision]
  python3 fetch.py --list

Rules (each one is a test):
  * an entry with no licence, no pinned revision, or a file with no 64-hex SHA-256 is refused before anything is downloaded;
  * a file already on disk with the right hash is left alone; a wrong one is deleted, never reused;
  * a download resumes from a .part file; the hash is checked over the finished file; a mismatch deletes it and exits 2;
  * HF_TOKEN (if set, for a gated repository) is sent only to huggingface.co, never to the CDN a redirect leads to.
Standard library only. HF_ENDPOINT overrides the host (the tests point it at a local server).
"""
import hashlib, json, os, re, sys, urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINT = lambda: os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FetchError(Exception):
    pass


def load_models(path=None):
    with open(path or os.path.join(HERE, "models.json")) as f: return json.load(f)["models"]


def check_entry(mid, entry):
    """Raises FetchError for an entry that is not safe to download."""
    for k in ("repo", "revision", "licence", "base"):
        if not entry.get(k): raise FetchError(f"{mid}: manifest has no '{k}'")
    if not re.match(r"^[0-9a-f]{40}$", entry["revision"]): raise FetchError(f"{mid}: revision must be a full 40-hex commit, not a branch name")
    if "main" not in entry.get("files", {}): raise FetchError(f"{mid}: manifest has no main file")
    for role, f in entry["files"].items():
        if not f.get("name") or "/" in f["name"] or f["name"].startswith("."): raise FetchError(f"{mid}/{role}: bad file name")
        if not HEX64.match(f.get("sha256") or ""): raise FetchError(f"{mid}/{role}: no pinned SHA-256")


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""): h.update(b)
    return h.hexdigest()


class _KeepTokenOnlyOnHF(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            new.remove_header("Authorization")
        return new


def download(url, dest, expected_sha, token=None, progress=None):
    """Streams url to dest (resuming dest + '.part'), verifies the hash, and moves it into place."""
    part = dest + ".part"; have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"User-Agent": "omnigate-bench-fetch"}
    if token: headers["Authorization"] = "Bearer " + token
    if have: headers["Range"] = f"bytes={have}-"
    op = urllib.request.build_opener(_KeepTokenOnlyOnHF)
    try:
        r = op.open(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:        # the .part is already complete
            r = None
        else: raise FetchError(f"{url}: HTTP {e.code}")
    if r is not None:
        mode = "ab" if (have and r.status == 206) else "wb"
        with open(part, mode) as f:
            n = have if mode == "ab" else 0
            for chunk in iter(lambda: r.read(1 << 20), b""):
                f.write(chunk); n += len(chunk)
                if progress: progress(n)
    got = sha256_of(part)
    if got != expected_sha:
        os.remove(part)
        raise FetchError(f"{os.path.basename(dest)}: SHA-256 {got} does not match the pinned {expected_sha}; the download was deleted")
    os.replace(part, dest)


def fetch(mid, entry, directory, want_mmproj=False, log=print):
    check_entry(mid, entry)
    os.makedirs(directory, exist_ok=True); out = {}
    for role, f in entry["files"].items():
        if role == "mmproj" and not want_mmproj: continue
        dest = os.path.join(directory, f["name"]); out[role] = dest
        if os.path.exists(dest):
            if sha256_of(dest) == f["sha256"]: log(f"  {f['name']}: already present, hash ok"); continue
            os.remove(dest); log(f"  {f['name']}: on disk with the wrong hash, deleted")
        url = f"{ENDPOINT()}/{entry['repo']}/resolve/{entry['revision']}/{urllib.parse.quote(f['name'])}"
        log(f"  {f['name']}: downloading (~{f.get('approx_gb', '?')} GB)")
        download(url, dest, f["sha256"], token=os.environ.get("HF_TOKEN"))
        log(f"  {f['name']}: hash ok")
    return out


def main(argv):
    models = load_models(); args = [a for a in argv if not a.startswith("--")]
    if "--list" in argv:
        for k, v in models.items(): print(f"{k:28} {v['licence']:12} {v['files']['main']['name']}  ({v['source']})")
        return 0
    d = os.environ.get("MODELS_DIR", os.path.expanduser("~/omnigate-models"))
    if "--dir" in argv: d = argv[argv.index("--dir") + 1]; args = [a for a in args if a != d]
    if not args: print(__doc__); return 1
    try:
        for mid in args:
            if mid not in models: raise FetchError(f"unknown model '{mid}' (try --list)")
            print(mid); fetch(mid, models[mid], d, want_mmproj="--vision" in argv)
    except FetchError as e:
        print("REFUSED:", e, file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
