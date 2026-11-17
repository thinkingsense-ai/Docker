#!/usr/bin/env python3
"""Keep the payment-workflow cloud add-on identical in the four stack charts. The single source is demos/payment-workflow (the Python files and inbox page that run the
workflow, and chart/payment-workflow.yaml, the Helm template). This copies them into each chart (files/payment-workflow/ and templates/payment-workflow.yaml) and makes sure
each chart's values.yaml has the paymentWorkflow block.
  scripts/sync-payment-workflow-addon.py          copy
  scripts/sync-payment-workflow-addon.py --check  exit 1 if any chart is out of date (for a pre-release check)"""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "demos/payment-workflow")
RUNTIME = ["activities.py", "decisions.py", "erp_mock.py", "facts.py", "inbox.html", "inbox.py", "recommend.py", "rules.py", "sap_facts.py", "sap_rules.py", "temporal_wait.py", "worker.py", "workflows.py", "gateway.py", "gateway_map.py", "manifest.gateway.json"]
CHARTS = ["resource-manager/omnigateeksstack/helm-deployer-lambda/omnigate-chart", "resource-manager/omnigateokestack/helm/omnigate", "resource-manager/omnigategkestack/helm/omnigate", "resource-manager/omnigateaksstack/helm/omnigate"]
VALUES = '''
# Opt-in demo add-on (off by default): the payment-exception workflow from demos/payment-workflow, as one extra pod (a Temporal dev server, the workflow worker,
# the approval inbox and a mock ERP). It needs demoDataset=treasury, is for the free edition only (a deployment holding a signed licence renders nothing), and is
# PRIVATE: the inbox is a ClusterIP Service with no sign-in, reached with `kubectl port-forward svc/<release>-payment-workflow 8085:8085`. The code comes from a
# ConfigMap and runs on the stock python image; the Temporal SDK is installed from PyPI when the pod starts. Nothing is ever written to a real ERP.
paymentWorkflow:
  enabled: false
  pythonImage: docker.io/library/python:3.12-slim
  # Temporal CLI image (its dev server), v1.5.1, pinned by digest.
  temporalImage: docker.io/temporalio/temporal@sha256:597a5dbbcc6e7716b326dde4a51622d5ea0879eb0cf06ff8a94381361d0a987d
  temporalSdkVersion: "1.30.0"
  storageSize: 1Gi
  approvalTimeoutMinutes: 2880
  # dry-run: an approved action only shows the call it would send. live: it goes to the mock ERP in the pod (still nothing real).
  writeBack: dry-run
'''
GATEWAY = '''  # Commercial edition only: put the workflow behind the app's own workflow API (Ask and Agency start, show and decide the runs). Needs a signed licence
  # (omnigate.license) and omnigate.adminApiToken; there is NO inbox in this mode; only the app's pods can reach the gateway (port 8094, bearer token). The app must be
  # restarted once after a first licence activation. token: leave empty to derive one from omnigate.adminApiToken.
  gateway:
    enabled: false
    token: ""
'''
def want(path, content):  # (path, bytes) -> True if the file already holds it
    return os.path.exists(path) and open(path, "rb").read() == content
def main(check):
    bad = []
    tpl = open(os.path.join(SRC, "chart/payment-workflow.yaml"), "rb").read()
    for chart in CHARTS:
        base = os.path.join(ROOT, chart)
        jobs = [(os.path.join(base, "templates/payment-workflow.yaml"), tpl)] + [(os.path.join(base, "files/payment-workflow", f), open(os.path.join(SRC, f), "rb").read()) for f in RUNTIME]
        for path, content in jobs:
            if not want(path, content):
                bad.append(os.path.relpath(path, ROOT))
                if not check:
                    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(content)
        vp = os.path.join(base, "values.yaml"); v = open(vp).read()
        if "\npaymentWorkflow:\n" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check: open(vp, "w").write(v.rstrip("\n") + "\n" + VALUES + GATEWAY)
        elif "\n  gateway:\n" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                assert "\n  writeBack: dry-run\n" in v, vp
                open(vp, "w").write(v.replace("\n  writeBack: dry-run\n", "\n  writeBack: dry-run\n" + GATEWAY, 1))
    if check:
        print("out of date:\n  " + "\n  ".join(bad) if bad else "the four charts are in sync"); return 1 if bad else 0
    print("updated %d files" % len(bad)); return 0
if __name__ == "__main__": sys.exit(main("--check" in sys.argv))
