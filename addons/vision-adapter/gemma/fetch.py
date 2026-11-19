"""Downloads the two Gemma files at a pinned revision and refuses a wrong SHA-256. Standard library only."""
import hashlib, os, sys, urllib.request


def fetch(repo, rev, name, want, out="/models"):
    os.makedirs(out, exist_ok=True); dest = os.path.join(out, name)
    h = hashlib.sha256()
    with urllib.request.urlopen(f"https://huggingface.co/{repo}/resolve/{rev}/{name}", timeout=60) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            h.update(b); f.write(b)
    if h.hexdigest() != want:
        os.remove(dest); raise SystemExit(f"SHA-256 mismatch for {name}: got {h.hexdigest()}, pinned {want}")
    print("ok", name)


if __name__ == "__main__":
    repo, rev, m, ms, p, ps = sys.argv[1:7]
    fetch(repo, rev, m, ms); fetch(repo, rev, p, ps)
