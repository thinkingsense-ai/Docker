#!/usr/bin/env python3
"""Check and bump the app image tag pinned across this repo. See RELEASING.md.

  scripts/version-pins.py check [--verify-ocir] [--verify-tags]
  scripts/version-pins.py bump vX.Y.Z [--group core] [--group gke ...]
  scripts/version-pins.py bump-self eks|aks vX.Y.Z

Pins are grouped by where the image is pulled from. A group must only be bumped once the tag is
published to THAT group's registry (each cloud pulls from a different one). `core` is the
Dockerfiles, compose file and the OKE stack, whose images are built and pushed together by the
release process; it must always agree and `check` fails if it does not. The other groups are
reported but may lag until their registry has the new tag.

Separate from the image pins are the stacks' **self-pins**: the stack release a template names for itself. The EKS template names the release
CodeBuild checks out to build the deployer (`Release.Current.Tag`); the AKS template (and its portal form) names the tarball its deployment
script takes the chart from (`chartSourceUrl`). Both must name the release about to be cut, and a stack release cut without moving them
deploys the PREVIOUS release's code (aks-stack-v1.0.13 shipped naming v1.0.12; eks-stack-v1.0.17 named v1.0.16). `bump-self` moves them;
`check` lists them and fails if the three AKS ones disagree; `check --verify-tags` (run AFTER cutting the releases) fails if a self-pin names
a tag that does not exist on the remote.
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
    ("core", f"{RM}/omnigateeksstack/template.yaml", r"(\n  ImageTag:\n    Type: String\n    Default: )" + TAG, 0),
    ("gke", f"{RM}/omnigategkestack/variables.tf",
     r'(variable "image_tag" \{.*?default\s*=\s*")' + TAG, re.S),
    ("aks", f"{RM}/omnigateaksstack/main.bicep", r"(param imageTag string = ')" + TAG, 0),
    ("aks", f"{RM}/omnigateaksstack/azuredeploy.json",
     r'("imageTag": \{.*?"defaultValue": ")' + TAG, re.S),
    ("aks", f"{RM}/omnigateaksstack/createUiDefinition.json",
     r'("name": "imageTag".*?"defaultValue": ")' + TAG, re.S),
]


# (stack, file, regex with the stack release version (vX.Y.Z) as the LAST capture group, flags)
SELF_PINS = [
    ("eks", f"{RM}/omnigateeksstack/template.yaml", r"(\n  Release:\n    Current:\n      Tag: eks-stack-)" + TAG, 0),
    ("aks", f"{RM}/omnigateaksstack/main.bicep", r"(param chartSourceUrl string = '[^']*?/aks-stack-)" + TAG, 0),
    ("aks", f"{RM}/omnigateaksstack/azuredeploy.json",
     r'("chartSourceUrl": \{.*?"defaultValue": "[^"]*?/aks-stack-)' + TAG, re.S),
    ("aks", f"{RM}/omnigateaksstack/createUiDefinition.json",
     r'("name": "chartSourceUrl".*?"defaultValue": "[^"]*?/aks-stack-)' + TAG, re.S),
]


def read_self_pins():
    out = []
    for stack, rel, rx, flags in SELF_PINS:
        m = re.search(rx, (ROOT / rel).read_text(), flags)
        out.append((stack, rel, m.group(m.lastindex) if m else None))
    return out


def remote_has_tag(tag):
    r = subprocess.run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], capture_output=True, text=True, cwd=ROOT)
    return bool(r.stdout.strip())


def read_pins():
    out = []
    for group, rel, rx, flags in PINS:
        text = (ROOT / rel).read_text()
        m = re.search(rx, text, flags)
        out.append((group, rel, m.group(m.lastindex) if m else None))
    return out


def tenancy_ocid():
    """The tenancy to look in: $OCI_TENANCY_OCID, else the `tenancy` of the default profile in ~/.oci/config."""
    import configparser
    import os
    if os.environ.get("OCI_TENANCY_OCID"):
        return os.environ["OCI_TENANCY_OCID"]
    cfg = configparser.ConfigParser()
    cfg.read(Path.home() / ".oci" / "config")
    try:
        return cfg["DEFAULT"]["tenancy"]
    except KeyError:
        sys.exit("--verify-ocir needs OCI_TENANCY_OCID, or a tenancy in ~/.oci/config")


def ocir_has(repo, tag):
    r = subprocess.run(
        ["oci", "artifacts", "container", "image", "list", "--compartment-id", tenancy_ocid(),
         "--repository-name", repo, "--query", "data.items[].version"],
        capture_output=True, text=True)
    return f'"{tag}"' in r.stdout


def check_self(verify_tags):
    """Lists the self-pins; ok unless one is missing, the AKS ones disagree, or (verify_tags) a named tag is not on the remote."""
    selfs = read_self_pins()
    print("\nself-pins (the stack release each template names for itself):")
    ok = True
    for stack, rel, t in selfs:
        print(f"{stack:5} {t or 'NOT FOUND':10} {rel}")
        ok = ok and t is not None
    for stack in ("eks", "aks"):
        versions = {t for st, _, t in selfs if st == stack}
        if len(versions) > 1:
            print(f"FAIL: the {stack} self-pins disagree: {sorted(map(str, versions))}")
            ok = False
        elif verify_tags and None not in versions:
            tag = f"{stack}-stack-{next(iter(versions))}"
            has = remote_has_tag(tag)
            print(f"tag  {tag} {'present' if has else 'MISSING on origin (cut the release, or this pin is ahead of it)'}")
            ok = ok and has
    return ok


def check(verify_ocir, verify_tags=False):
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
    ok = check_self(verify_tags) and ok
    return 0 if ok else 1


def bump_self(stack, new):
    if not re.fullmatch(TAG, new):
        sys.exit(f"stack release must look like v1.0.19, got {new!r}")
    changed = 0
    for st, rel, rx, flags in SELF_PINS:
        if st != stack:
            continue
        p = ROOT / rel
        text = p.read_text()
        m = re.search(rx, text, flags)
        if not m:
            sys.exit(f"self-pin not found in {rel}")
        if m.group(m.lastindex) == new:
            continue
        s, e = m.span(m.lastindex)
        p.write_text(text[:s] + new + text[e:])
        print(f"bumped {rel}: {m.group(m.lastindex)} -> {new}")
        changed += 1
    extra = (" azuredeploy.json is generated from main.bicep: run `az bicep build --file main.bicep --outfile azuredeploy.json` in "
             "resource-manager/omnigateaksstack and commit the result (it should differ from the edited file only in metadata.templateHash).") if stack == "aks" else ""
    print(f"{changed} file(s) changed. Merge this BEFORE tagging {stack}-stack-{new}, and cut the tag at the merge commit.{extra}")


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
    c.add_argument("--verify-tags", action="store_true", help="after cutting releases: self-pins must name tags that exist on origin")
    bs = sub.add_parser("bump-self")
    bs.add_argument("stack", choices=["eks", "aks"])
    bs.add_argument("tag", help="the stack release about to be cut, e.g. v1.0.19")
    b = sub.add_parser("bump")
    b.add_argument("tag")
    b.add_argument("--group", action="append", default=None)
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(check(a.verify_ocir, a.verify_tags))
    if a.cmd == "bump-self":
        bump_self(a.stack, a.tag)
        sys.exit(0)
    bump(a.tag, set(a.group or ["core"]))
