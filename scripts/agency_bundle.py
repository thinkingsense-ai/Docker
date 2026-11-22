#!/usr/bin/env python3
"""Build and check the Agency UI bundle that the cloud add-on ships (agency/chart/web.tgz: the built UI plus INPUT_SHA, a hash of the sources it was built from).
  scripts/agency_bundle.py build   npm ci + npm run build in agency/web, then write agency/chart/web.tgz (needs node)
  scripts/agency_bundle.py check   exit 1 when the committed bundle was built from different sources than agency/web now holds (no build, no node needed)
The bundle is generated, so a source change without a rebuild must fail a pre-release check rather than ship an old screen."""
import hashlib, io, os, subprocess, sys, tarfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "agency/web")
OUT = os.path.join(ROOT, "agency/chart/web.tgz")
INPUTS = ["src", "public", "index.html", "package.json", "package-lock.json", "tsconfig.json", "vite.config.ts"]
def input_sha():
    h = hashlib.sha256()
    for item in INPUTS:
        p = os.path.join(WEB, item)
        files = [p] if os.path.isfile(p) else sorted(os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs)
        for f in files:
            h.update(os.path.relpath(f, WEB).encode() + b"\0"); h.update(open(f, "rb").read()); h.update(b"\0")
    return h.hexdigest()
def stored_sha():
    if not os.path.exists(OUT): return None
    with tarfile.open(OUT) as t:
        m = [x for x in t.getmembers() if x.name == "INPUT_SHA"]
        return t.extractfile(m[0]).read().decode().strip() if m else None
def build():
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=WEB, check=True)
    subprocess.run(["npm", "run", "build"], cwd=WEB, check=True)
    dist = os.path.join(WEB, "dist")
    def clean(ti):                                   # reproducible: no owner, no timestamps
        ti.uid = ti.gid = 0; ti.uname = ti.gname = ""; ti.mtime = 0; return ti
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as t:
        sha = input_sha().encode() + b"\n"
        ti = tarfile.TarInfo("INPUT_SHA"); ti.size = len(sha); t.addfile(clean(ti), io.BytesIO(sha))
        for d, _, fs in sorted(os.walk(dist)):
            for f in sorted(fs):
                full = os.path.join(d, f); ti = t.gettarinfo(full, os.path.relpath(full, dist)); t.addfile(clean(ti), open(full, "rb"))
    import gzip
    with open(OUT, "wb") as o, gzip.GzipFile(fileobj=o, mode="wb", mtime=0) as g: g.write(raw.getvalue())
    print("wrote", os.path.relpath(OUT, ROOT), os.path.getsize(OUT), "bytes")
def main(cmd):
    if cmd == "build": build(); return 0
    if cmd == "check":
        want, have = input_sha(), stored_sha()
        print("the UI bundle matches the sources" if want == have else "the UI bundle is stale or missing: run scripts/agency_bundle.py build")
        return 0 if want == have else 1
    print(__doc__); return 2
if __name__ == "__main__": sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
