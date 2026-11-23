#!/usr/bin/env python3
"""Keep the Agency cloud add-on identical in the four stack charts. Single sources: addons/thinking-layer (the layer's Python files and contract.json), packs/catalogue.json,
agency/chart/web.tgz (the built UI, see scripts/agency_bundle.py) and agency/chart/agency.yaml (the Helm template). They are copied into each chart (files/agency/ and
templates/agency.yaml), and each chart's values.yaml gets the agency block (with that cloud's load balancer annotations).
  scripts/sync-agency-addon.py          copy
  scripts/sync-agency-addon.py --check  exit 1 if any chart is out of date (also checks the UI bundle against agency/web); for a pre-release check"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYER = os.path.join(ROOT, "addons/thinking-layer")
PY = ["app.py", "adapters.py", "audit.py", "catalogue.py", "decisions.py", "evidence.py", "tools.py", "uploads.py", "upstream.py"]
# (published file name, source path)
FILES = [(f, os.path.join(LAYER, f)) for f in PY] + [("contract.json", os.path.join(LAYER, "contract.json")), ("catalogue.json", os.path.join(ROOT, "packs/catalogue.json")), ("web.tgz", os.path.join(ROOT, "agency/chart/web.tgz"))]
# chart -> the load balancer annotations that cloud's own Ask Service carries (a layer behind a buffering load balancer would stall the streamed answers)
CHARTS = {
    "resource-manager/omnigateeksstack/helm-deployer-lambda/omnigate-chart": {"service.beta.kubernetes.io/aws-load-balancer-type": "external", "service.beta.kubernetes.io/aws-load-balancer-nlb-target-type": "instance", "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing"},
    "resource-manager/omnigateokestack/helm/omnigate": {"oci.oraclecloud.com/load-balancer-type": "nlb"},
    "resource-manager/omnigategkestack/helm/omnigate": {},
    "resource-manager/omnigateaksstack/helm/omnigate": {"service.beta.kubernetes.io/azure-load-balancer-internal": "false"},
}
# The Agency IT-risk investigation data (the `agency-risk` pack): seeds and approved questions, copied to each chart's files/ (not files/agency/) so the pack composer can read them.
DATA = [("seed-rca-postgres.sql", "demos/it-risk-rca/seed-rca-postgres.sql"), ("seed-estate-postgres.sql", "demos/it-risk-estate/seed-estate-postgres.sql"), ("seed-register-postgres.sql", "demos/it-risk-register/seed-register-postgres.sql"),
        ("demo-questions-rca.json", "demos/it-risk-rca/demo-questions-rca.json"), ("demo-questions-estate.json", "demos/it-risk-estate/demo-questions-estate.json"),
        ("demo-questions-priorities.json", "demos/it-risk-estate/demo-questions-priorities.json"), ("demo-questions-register.json", "demos/it-risk-register/demo-questions-register.json")]
def closure(start):
    """The local .py files the worker and the gateway import (so the list cannot go stale), plus the workflow manifest."""
    import ast
    src = os.path.join(ROOT, "demos/payment-workflow"); seen, todo = set(), list(start)
    while todo:
        f = todo.pop()
        if f in seen: continue
        seen.add(f)
        for n in ast.walk(ast.parse(open(os.path.join(src, f)).read())):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
            for m in names:
                m = m.split(".")[0] + ".py"
                if os.path.exists(os.path.join(src, m)): todo.append(m)
    return sorted(seen) + ["manifest.gateway.json"]
def values(annotations):
    ann = "".join('      %s: "%s"\n' % (k, v) for k, v in annotations.items())
    return '''
# Opt-in second front end (off by default): Agency, installed beside the Ask app. The layer's code and the built UI come from ConfigMaps and run on the stock python image, so there is
# no image to publish. It signs people in with the app's own business-user logins and asks the app's internal address; a restart signs everyone out (sessions are in memory).
# It gets its own public Service (the same allowed client addresses as the Ask app apply). The workflow screens need the commercial edition and the workflow engine (not wired here yet).
agency:
  enabled: false
  pythonImage: docker.io/library/python:3.12-slim
  # Where browsers reach Agency (needed only for single sign-on: the provider returns here). Leave empty otherwise.
  publicUrl: ""
  # Optional link shown in the header to the admin console (a convenience, not a control: the console has its own sign-in).
  adminUrl: ""
  # After install and upgrade a Job loads one Workspace per pack plus `all-data` (only when the Server has no Workspace yet; it never overwrites yours) and sets what the logins
  # listed in `grants` may do. Nothing is granted unless listed. Example entry:
  #   - { username: alice, canSeeSql: false, canSeeSources: false, canUploadFiles: true, canStartWorkflows: true, canApprove: false }
  bootstrap:
    enabled: true
    grants: []
  # Commercial edition only. The Agency workflows (incident brief, vulnerability exception, risk assessment, major-incident decision; the payment exception too with the Treasury pack)
  # behind the app's own workflow API: one pod with a Temporal dev server, the worker and the gateway. Needs agency.enabled, the agency-risk pack, a signed licence and
  # omnigate.adminApiToken; excludes paymentWorkflow.gateway. Write-back is a dry run; recommendations come from the rules unless set to "model" (then omnigate.llmApiKey is used).
  workflows:
    enabled: false
    writeBack: dry-run
    recommendations: rules-only
    approvalTimeoutMinutes: 2880
    storageSize: 1Gi
    gatewayToken: ""            # empty derives one from omnigate.adminApiToken
    registerWriterPassword: ""  # empty derives one from omnigate.adminApiToken
  service:
    type: LoadBalancer
    port: 8097
    annotations:%s''' % ((" {}\n" if not ann else "\n" + ann))
WF = '''  # Commercial edition only. The Agency workflows (incident brief, vulnerability exception, risk assessment, major-incident decision; the payment exception too with the Treasury pack)
  # behind the app's own workflow API: one pod with a Temporal dev server, the worker and the gateway. Needs agency.enabled, the agency-risk pack, a signed licence and
  # omnigate.adminApiToken; excludes paymentWorkflow.gateway. Write-back is a dry run; recommendations come from the rules unless set to "model" (then omnigate.llmApiKey is used).
  workflows:
    enabled: false
    writeBack: dry-run
    recommendations: rules-only
    approvalTimeoutMinutes: 2880
    storageSize: 1Gi
    gatewayToken: ""            # empty derives one from omnigate.adminApiToken
    registerWriterPassword: ""  # empty derives one from omnigate.adminApiToken
'''
def want(path, content): return os.path.exists(path) and open(path, "rb").read() == content
def main(check):
    bad = []
    if subprocess.run([sys.executable, os.path.join(ROOT, "scripts/agency_bundle.py"), "check"], capture_output=True).returncode != 0:
        bad.append("agency/chart/web.tgz (built from older sources: scripts/agency_bundle.py build)")
    tpl = open(os.path.join(ROOT, "agency/chart/agency.yaml"), "rb").read()
    for chart, ann in CHARTS.items():
        base = os.path.join(ROOT, chart)
        wf = [(os.path.join(base, "files/agency-workflows", f), open(os.path.join(ROOT, "demos/payment-workflow", f), "rb").read()) for f in closure(["worker.py", "gateway.py"])]
        jobs = wf + [(os.path.join(base, "templates/agency-workflows.yaml"), open(os.path.join(ROOT, "agency/chart/agency-workflows.yaml"), "rb").read()), (os.path.join(base, "templates/_agency.tpl"), open(os.path.join(ROOT, "agency/chart/_agency.tpl"), "rb").read())] + [(os.path.join(base, "templates/agency.yaml"), tpl), (os.path.join(base, "templates/agency-bootstrap.yaml"), open(os.path.join(ROOT, "agency/chart/agency-bootstrap.yaml"), "rb").read())] + [(os.path.join(base, "files/agency", n), open(src, "rb").read()) for n, src in FILES] + [(os.path.join(base, "files", n), open(os.path.join(ROOT, src), "rb").read()) for n, src in DATA]
        for path, content in jobs:
            if not want(path, content):
                bad.append(os.path.relpath(path, ROOT))
                if not check:
                    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(content)
        vp = os.path.join(base, "values.yaml"); v = open(vp).read()
        if "\nagency:\n" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check: open(vp, "w").write(v.rstrip("\n") + "\n" + values(ann))
        elif "\n  workflows:\n    enabled" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                assert "\n  service:\n    type: LoadBalancer" in v, vp
                open(vp, "w").write(v.replace("\n  service:\n    type: LoadBalancer", "\n" + WF.rstrip("\n") + "\n  service:\n    type: LoadBalancer", 1))
        elif "\n  bootstrap:\n" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                block = values(ann)
                new = block[block.index("  # After install and upgrade"):block.index("  service:")]
                assert '  adminUrl: ""\n  service:' in v, vp
                open(vp, "w").write(v.replace('  adminUrl: ""\n  service:', '  adminUrl: ""\n' + new + "  service:", 1))
    if check:
        print("out of date:\n  " + "\n  ".join(bad) if bad else "the four charts are in sync"); return 1 if bad else 0
    print("updated %d files" % len(bad)); return 0
if __name__ == "__main__": sys.exit(main("--check" in sys.argv))
