#!/usr/bin/env python3
"""Keep the Agency cloud add-on identical in the four stack charts. Single sources: agency/chart/agency.yaml, agency-bootstrap.yaml, agency-workflows.yaml and _agency.tpl (the Helm templates),
the workflow pod's code (the files demos/payment-workflow's worker and gateway import) and the IT-risk data files. They are copied into each chart (templates/ and files/), and each chart's
values.yaml gets the agency block (with that cloud's load balancer annotations). The layer and the UI are NOT copied: they ship as an image (addons/thinking-layer/Dockerfile), because
a Helm release is stored in one Secret capped at 1 MiB and carrying the code in the chart took it past that.
  scripts/sync-agency-addon.py          copy
  scripts/sync-agency-addon.py --check  exit 1 if any chart is out of date; for a pre-release check"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYER = os.path.join(ROOT, "addons/thinking-layer")
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
# The published images, pinned by digest (Build Agency image run 45315200946, tag 0.1.0, built from addons/thinking-layer and demos/payment-workflow). Update both after each publish.
AGENCY_IMAGE = "us-docker.pkg.dev/thinkingsense/omnigate/agency:0.1.1@sha256:496d701be290bca0108cf217bd8775636409520da211a08992b494dc40205d22"
WORKFLOWS_IMAGE = "us-docker.pkg.dev/thinkingsense/omnigate/agency-workflows:0.1.1@sha256:1876a2d324ff6776bbef96ac9b199543ba37bebe6736e13b36c54f36140ae493"
FEED_IMAGE = "us-docker.pkg.dev/thinkingsense/omnigate/agency-feed:0.1.2@sha256:5ce51badba99bf1cef96610aabb7055eebdcd89666f10865603d9cccb8406c09"
def values(annotations):
    ann = "".join('      %s: "%s"\n' % (k, v) for k, v in annotations.items())
    return '''
# Opt-in second front end (off by default): Agency, installed beside the Ask app. The layer's code and the built UI come from ConfigMaps and run on the stock python image, so there is
# no image to publish. It signs people in with the app's own business-user logins and asks the app's internal address; a restart signs everyone out (sessions are in memory).
# It gets its own public Service (the same allowed client addresses as the Ask app apply). The workflow screens need the commercial edition and the workflow engine (not wired here yet).
agency:
  enabled: false
  pythonImage: docker.io/library/python:3.12-slim   # the bootstrap Job and the workflow pod run on this
  # The Agency image (addons/thinking-layer/Dockerfile: the layer and the built UI), built by the Build images workflow.
  image: @AGENCY_IMAGE@
  # HTTPS for Agency, like the Ask app: a self-signed certificate is made at install (and kept across upgrades) unless secretName names your own kubernetes.io/tls Secret.
  tls:
    enabled: true
    secretName: ""
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
    # Built from demos/payment-workflow/Dockerfile by the Build Agency image workflow (the code, the Temporal SDK and the psql client).
    image: @WORKFLOWS_IMAGE@
    writeBack: dry-run
    recommendations: rules-only
    approvalTimeoutMinutes: 2880
    storageSize: 1Gi
    gatewayToken: ""            # empty derives one from omnigate.adminApiToken
    registerWriterPassword: ""  # empty derives one from omnigate.adminApiToken
@FEED@@TOUR@  service:
    type: LoadBalancer
    port: 8097
    annotations:%s'''.replace("@AGENCY_IMAGE@", AGENCY_IMAGE).replace("@WORKFLOWS_IMAGE@", WORKFLOWS_IMAGE).replace("@FEED@", FEED_RAW.replace("@FEED_IMAGE@", FEED_IMAGE).replace("%", "%%")).replace("@TOUR@", TOUR_RAW.replace("%", "%%")) % ((" {}\n" if not ann else "\n" + ann))
WF_RAW = '''  # Commercial edition only. The Agency workflows (incident brief, vulnerability exception, risk assessment, major-incident decision; the payment exception too with the Treasury pack)
  # behind the app's own workflow API: one pod with a Temporal dev server, the worker and the gateway. Needs agency.enabled, the agency-risk pack, a signed licence and
  # omnigate.adminApiToken; excludes paymentWorkflow.gateway. Write-back is a dry run; recommendations come from the rules unless set to "model" (then omnigate.llmApiKey is used).
  workflows:
    enabled: false
    # Built from demos/payment-workflow/Dockerfile by the Build Agency image workflow (the code, the Temporal SDK and the psql client).
    image: @WORKFLOWS_IMAGE@
    writeBack: dry-run
    recommendations: rules-only
    approvalTimeoutMinutes: 2880
    storageSize: 1Gi
    gatewayToken: ""            # empty derives one from omnigate.adminApiToken
    registerWriterPassword: ""  # empty derives one from omnigate.adminApiToken
'''
WF = WF_RAW.replace("@WORKFLOWS_IMAGE@", WORKFLOWS_IMAGE)
FEED_RAW = '''  # The live feed: a small read-only pod reads 12 public news and advisory feeds every intervalMinutes and writes headlines (metadata only, no article text) into the rca feed tables,
  # so Watch shows events under review and Sources shows each feed's health. Needs agency.enabled and the agency-risk pack; the pod needs the public internet (port 443). The publishers'
  # reuse terms have not been read, so it is OFF by default. dbPassword empty = a random one kept across upgrades.
  feed:
    enabled: false
    # Built from addons/feed-adapter/Dockerfile by the Build Agency image workflow.
    image: @FEED_IMAGE@
    intervalMinutes: 30
    dbPassword: ""
'''
TOUR_RAW = '''  # A "Quickstart tour" button for the IT-risk screens that only READ (events under review, sources, problem record, exposure, priorities, notifications): it signs in nobody else and starts
  # no run, so it is safe on a shared stack and can be played again. (The full demo tour, which signs in demo people, is for the local sandbox only and is not wired here.)
  tour:
    readOnly: false
'''
FEED = FEED_RAW.replace("@FEED_IMAGE@", FEED_IMAGE)
def want(path, content): return os.path.exists(path) and open(path, "rb").read() == content
def main(check):
    bad = []
    tpl = open(os.path.join(ROOT, "agency/chart/agency.yaml"), "rb").read()
    for chart, ann in CHARTS.items():
        base = os.path.join(ROOT, chart)
        wf = [(os.path.join(base, "files/agency-workflows", f), open(os.path.join(ROOT, "demos/payment-workflow", f), "rb").read()) for f in ["manifest.gateway.json"]]
        jobs = wf + [(os.path.join(base, "templates/agency-workflows.yaml"), open(os.path.join(ROOT, "agency/chart/agency-workflows.yaml"), "rb").read()), (os.path.join(base, "templates/_agency.tpl"), open(os.path.join(ROOT, "agency/chart/_agency.tpl"), "rb").read())] + [(os.path.join(base, "templates/agency.yaml"), tpl), (os.path.join(base, "templates/agency-bootstrap.yaml"), open(os.path.join(ROOT, "agency/chart/agency-bootstrap.yaml"), "rb").read()), (os.path.join(base, "templates/agency-feed.yaml"), open(os.path.join(ROOT, "agency/chart/agency-feed.yaml"), "rb").read())] + [(os.path.join(base, "files", n), open(os.path.join(ROOT, src), "rb").read()) for n, src in DATA]
        for path, content in jobs:
            if not want(path, content):
                bad.append(os.path.relpath(path, ROOT))
                if not check:
                    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(content)
        wdir = os.path.join(base, "files/agency-workflows")
        for f in (sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []):
            if f != "manifest.gateway.json":
                bad.append(os.path.relpath(os.path.join(wdir, f), ROOT) + " (the workflow code now ships as an image)")
                if not check: os.remove(os.path.join(wdir, f))
        stale = os.path.join(base, "files/agency")
        if os.path.isdir(stale):
            bad.append(os.path.relpath(stale, ROOT) + " (the layer's code now ships as an image)")
            if not check:
                import shutil; shutil.rmtree(stale)
        vp = os.path.join(base, "values.yaml"); v = open(vp).read()
        if "\nagency:\n" in v and "\n  tls:\n    enabled" not in v.split("\nagency:\n", 1)[1]:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                assert "\n  # Where browsers reach Agency" in v, vp
                v = v.replace("\n  # Where browsers reach Agency", "\n  # HTTPS for Agency, like the Ask app: a self-signed certificate is made at install (and kept across upgrades) unless secretName names your own kubernetes.io/tls Secret.\n  tls:\n    enabled: true\n    secretName: \"\"\n  # Where browsers reach Agency", 1)
                open(vp, "w").write(v)
        if "\n  workflows:\n    enabled: false" in v and "omnigate-agency-workflows" not in v and "omnigate/agency-workflows" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                v = v.replace("\n  workflows:\n    enabled: false\n", "\n  workflows:\n    enabled: false\n    # Built from demos/payment-workflow/Dockerfile by the Build Agency image workflow (the code, the Temporal SDK and the psql client).\n    image: us-docker.pkg.dev/thinkingsense/omnigate/agency-workflows:0.1.0\n", 1)
                open(vp, "w").write(v)
        if "\nagency:\n" in v and "\n  image: us-docker.pkg.dev/thinkingsense/omnigate/agency:" not in v:
            bad.append(os.path.relpath(vp, ROOT))
            if not check:
                assert "\n  pythonImage: docker.io/library/python:3.12-slim" in v, vp
                v = v.replace("\n  pythonImage: docker.io/library/python:3.12-slim", "\n  pythonImage: docker.io/library/python:3.12-slim   # the bootstrap Job and the workflow pod run on this\n  # The Agency image (addons/thinking-layer/Dockerfile: the layer and the built UI), built by the Build images workflow.\n  image: us-docker.pkg.dev/thinkingsense/omnigate/agency:0.1.0", 1)
                open(vp, "w").write(v)
        if "\nagency:\n" in v and "\n  feed:\n    enabled" not in v:
            bad.append(os.path.relpath(vp, ROOT) + " (feed block)")
            if not check:
                assert "\n  service:\n    type: LoadBalancer" in v, vp
                v = v.replace("\n  service:\n    type: LoadBalancer", "\n" + FEED.rstrip("\n") + "\n  service:\n    type: LoadBalancer", 1)
                open(vp, "w").write(v)
        if "\nagency:\n" in v and "\n  tour:\n    readOnly" not in v:
            bad.append(os.path.relpath(vp, ROOT) + " (tour block)")
            if not check:
                assert "\n  service:\n    type: LoadBalancer" in v, vp
                v = v.replace("\n  service:\n    type: LoadBalancer", "\n" + TOUR_RAW.rstrip("\n") + "\n  service:\n    type: LoadBalancer", 1)
                open(vp, "w").write(v)
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
    import re
    for chart in CHARTS:
        vp = os.path.join(ROOT, chart, "values.yaml"); v = open(vp).read()
        # The Agency image keys belong to the agency block, and only there. An earlier version of this script put them after the FIRST `pythonImage:` line, which is the paymentWorkflow block's:
        # repair that, then make sure the agency block has its own `image:`.
        head, sep, tail = v.partition("\nagency:\n")
        fixed = re.sub(r"(?m)^  pythonImage: docker\.io/library/python:3\.12-slim[^\n]*\n(?:  # The Agency image[^\n]*\n  image: [^\n]*\n)+", "  pythonImage: docker.io/library/python:3.12-slim\n", head)
        if sep and not re.search(r"(?m)^  image: ", tail.split("\n  workflows:\n", 1)[0]):
            tail = tail.replace("  pythonImage: docker.io/library/python:3.12-slim\n", "  pythonImage: docker.io/library/python:3.12-slim   # the bootstrap Job and the workflow pod run on this\n  # The Agency image (addons/thinking-layer/Dockerfile: the layer and the built UI), built by the Build Agency image workflow.\n  image: " + AGENCY_IMAGE + "\n", 1)
        tail = re.sub(r"(    # Built from demos/payment-workflow[^\n]*\n    image: [^\n]*\n)\1+", r"\1", tail)          # an earlier run of this script could add the pair twice
        if fixed + sep + tail != v:
            bad.append(os.path.relpath(vp, ROOT) + " (agency image placement)")
            if not check: open(vp, "w").write(fixed + sep + tail)
        v = fixed + sep + tail if not check else v
        n = re.sub(r"(?m)^  image: (?:ghcr\.io/thinkingsense-ai/omnigate-agency|us-docker\.pkg\.dev/thinkingsense/omnigate/agency)[:@]\S+$", "  image: " + AGENCY_IMAGE, v)
        n = re.sub(r"(?m)^    image: (?:ghcr\.io/thinkingsense-ai/omnigate-agency-workflows|us-docker\.pkg\.dev/thinkingsense/omnigate/agency-workflows)[:@]\S+$", "    image: " + WORKFLOWS_IMAGE, n)
        n = re.sub(r"(?m)^    image: us-docker\.pkg\.dev/thinkingsense/omnigate/agency-feed[:@]\S+$", "    image: " + FEED_IMAGE, n)
        if n != v:
            bad.append(os.path.relpath(vp, ROOT) + " (image pins)")
            if not check: open(vp, "w").write(n)
    if check:
        print("out of date:\n  " + "\n  ".join(bad) if bad else "the four charts are in sync"); return 1 if bad else 0
    print("updated %d files" % len(bad)); return 0
if __name__ == "__main__": sys.exit(main("--check" in sys.argv))
