#!/usr/bin/env python3
"""Check and bump the app image tag pinned across this repo. See RELEASING.md.

  scripts/version-pins.py check [--verify-ocir]
  scripts/version-pins.py bump vX.Y.Z [--group core] [--group gke ...]

Pins are grouped by where the image is pulled from. A group must only be bumped once the tag is
published to THAT group's registry (each cloud pulls from a different one). `core` is the
Dockerfiles, compose file and the OKE stack, whose images are built and pushed together by the
release process; it must always agree and `check` fails if it does not. The other groups are
reported but may lag until their registry has the new tag.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RM = "resource-manager"
TAG = r"(v\d+\.\d+\.\d+)"

# (group, file, regex with the tag as the LAST capture group, flags)
PINS = [
    ("core", "Dockerfile", r"(ARG OMNIGATE_RELEASE_TAG=)" + TAG, 0),
    ("core", "free-edition/Dockerfile", r"(ARG OMNIGATE_RELEASE_TAG=)" + TAG, 0),
    ("core", "docker-compose.yml", r"(OMNIGATE_RELEASE_TAG:-)" + TAG, 0),
    ("core", f"{RM}/omnigateokestack/variables.tf",
     r'(variable "image_tag" \{.*?default\s*=\s*")' + TAG, re.S),
    ("core", f"{RM}/omnigateokestack/schema.yaml",
     r'(\n  image_tag:\n.*?default: ")' + TAG, re.S),
    ("gke", f"{RM}/omnigategkestack/variables.tf",
     r'(variable "image_tag" \{.*?default\s*=\s*")' + TAG, re.S),
    ("aks", f"{RM}/omnigateaksstack/azuredeploy.json",
     r'("imageTag": \{.*?"defaultValue": ")' + TAG, re.S),
    ("aks", f"{RM}/omnigateaksstack/createUiDefinition.json",
     r'("name": "imageTag".*?"defaultValue": ")' + TAG, re.S),
]


def read_pins():
    out = []
    for group, rel, rx, flags in PINS:
        text = (ROOT / rel).read_text()
        m = re.search(rx, text, flags)
        out.append((group, rel, m.group(m.lastindex) if m else None))
    return out


def ocir_has(repo, tag):
    ns = "ocid1.tenancy.oc1..aaaaaaaa7knayo46uzyz6nx7szpwrqvevwr5npvqmjz7kexgqplfxnfta5bq"
    r = subprocess.run(
        ["oci", "artifacts", "container", "image", "list", "--compartment-id", ns,
         "--repository-name", repo, "--query", "data.items[].version"],
        capture_output=True, text=True)
    return f'"{tag}"' in r.stdout


def check(verify_ocir):
    pins = read_pins()
    core = {t for g, _, t in pins if g == "core"}
    for g, rel, t in pins:
        print(f"{g:5} {t or 'NOT FOUND':10} {rel}")
    ok = len(core) == 1 and None not in core
    if not ok:
        print(f"\nFAIL: core pins disagree or are missing: {sorted(map(str, core))}")
    if verify_ocir and ok:
        tag = core.pop()
        for repo in ("omnigate", "omnigate-commercial"):
            has = ocir_has(repo, tag)
            print(f"OCIR {repo}:{tag} {'present' if has else 'MISSING'}")
            ok = ok and has
    lag = sorted({g for g, _, t in pins if g != "core" and t not in core and t})
    if lag:
        print(f"\nnote: groups behind core (fine until their registry has the tag): {lag}")
    return 0 if ok else 1


def bump(new, groups):
    if not re.fullmatch(TAG, new):
        sys.exit(f"tag must look like v0.10.4, got {new!r}")
    changed = 0
    for group, rel, rx, flags in PINS:
        if group not in groups:
            continue
        p = ROOT / rel
        text = p.read_text()
        m = re.search(rx, text, flags)
        if not m:
            sys.exit(f"pin not found in {rel}")
        if m.group(m.lastindex) == new:
            continue
        s, e = m.span(m.lastindex)
        p.write_text(text[:s] + new + text[e:])
        print(f"bumped {rel}: {m.group(m.lastindex)} -> {new}")
        changed += 1
    print(f"{changed} file(s) changed. Before merging: confirm {new} exists in each bumped "
          "group's registry (check --verify-ocir for core), and update prose mentions in READMEs.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--verify-ocir", action="store_true")
    b = sub.add_parser("bump")
    b.add_argument("tag")
    b.add_argument("--group", action="append", default=None)
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(check(a.verify_ocir))
    bump(a.tag, set(a.group or ["core"]))
