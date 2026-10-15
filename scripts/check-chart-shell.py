#!/usr/bin/env python3
"""Syntax-checks every shell command the OKE chart renders.

`helm lint` and `helm template` pass on a command that YAML has quietly mangled: in a folded scalar (`>-`)
a more-indented line keeps its newline, so a multi-line loop can render with a line starting `||` (found
live: the TPC-H loader's init container failed 8 times and the whole deploy timed out after 40 minutes).
This renders the chart in several configurations, decodes each `sh -c <script>` / `bash -c <script>` command
the way Kubernetes would see it, and runs `sh -n` on it.

  pip install pyyaml
  scripts/check-chart-shell.py            # exit 1 if any rendered script fails to parse
"""
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("needs PyYAML: pip install pyyaml")

CHART = Path(__file__).resolve().parent.parent / "resource-manager" / "omnigateokestack" / "helm" / "omnigate"
BASE = ["--set", "omnigate.appUsers=x", "--set", "omnigate.llmApiKey=x"]
CLUSTER = ["--set", "omnigate.clusterEnabled=true", "--set", "omnigate.replicaCount=2",
           "--set", "omnigate.configDb.external=true", "--set", "omnigate.configDb.configDbUrl=jdbc:x",
           "--set", "omnigate.configDb.configDbUser=u", "--set", "omnigate.configDb.configDbPassword=p"]
CONFIGS = {
    "default": [],
    "tpch (postgres fact table)": ["--set", "tpch.enabled=true"],
    "tpch (s3 fact table)": ["--set", "tpch.enabled=true", "--set", "tpch.lineitemStore=s3"],
    "cluster + tpch + sso": CLUSTER + ["--set", "tpch.enabled=true", "--set", "omnigate.oidc.issuer=https://x",
                                       "--set", "omnigate.oidc.clientId=c", "--set", "omnigate.oidc.clientSecret=s"],
}


def containers(doc):
    spec = ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
    for key in ("initContainers", "containers"):
        for c in spec.get(key) or []:
            yield c


def main():
    bad = checked = 0
    for name, extra in CONFIGS.items():
        out = subprocess.run(["helm", "template", "t", str(CHART)] + BASE + extra, capture_output=True, text=True)
        if out.returncode != 0:
            print(f"[{name}] helm template failed: {out.stderr.strip()[:200]}")
            bad += 1
            continue
        for doc in yaml.safe_load_all(out.stdout):
            if not doc:
                continue
            for c in containers(doc):
                cmd = c.get("command") or []
                if len(cmd) >= 3 and cmd[0] in ("sh", "bash") and cmd[1] == "-c":
                    checked += 1
                    r = subprocess.run(["sh", "-n", "-c", cmd[2]], capture_output=True, text=True)
                    if r.returncode != 0:
                        bad += 1
                        print(f"[{name}] {doc['kind']}/{doc['metadata']['name']} container {c['name']}: {r.stderr.strip()}")
                        print("    script:", repr(cmd[2])[:300])
    print(f"checked {checked} shell command(s) across {len(CONFIGS)} configurations: {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
