"""The GPU quota request for the local-model benchmark on Google Cloud, through the Cloud Quotas API (no console clicks, no gcloud components).

  python3 gce_quota.py plan    [--region us-central1] [--zones us-central1-a,us-central1-c]    # prints what would be asked for; sends nothing
  python3 gce_quota.py show    [--region us-central1]                                          # the current limits for the GPU quotas below
  python3 gce_quota.py request [--region us-central1] [--zones ...] --yes                       # files the requests (Google reviews them; approval can take hours to days)

Why: the project's GPUS-ALL-REGIONS limit is 0, which blocks every GPU machine whatever the per-region limits say, and the A100 and H100 limits are 0. A request needs a PAID billing account
(a free-trial account cannot use GPUs): attach the startup credits and upgrade the account first, or Google will decline. The default ask is small and for benchmarking only: up to 4 GPUs in total,
4 L4 (24 GB), 2 A100 80 GB; each is kept below what the benchmark queue can use at once. H100 on-demand is not offered as a quota id here (only committed and preemptible ids exist), so ask Google
for a reservation separately if H100 is wanted.
Environment: GCP_PROJECT (default: the gcloud project). Uses `gcloud auth print-access-token`; the Cloud Quotas API (cloudquotas.googleapis.com) must be enabled. Standard library only."""
import json, os, subprocess, sys, urllib.error, urllib.request

API = "https://cloudquotas.googleapis.com/v1"
JUSTIFICATION = ("Benchmarking open-weight language models on GPUs to choose a small model for governed SQL generation. Short-lived instances (hours), deleted after each run, "
                 "no production traffic. Startup programme credits fund the work.")


def wanted(region="us-central1", zones=("us-central1-a",)):
    """The quota preferences to ask for (pure; tested). Each: quotaId, dimensions, preferred value."""
    out = [("GPUS-ALL-REGIONS-per-project", {}, 4),
           ("NVIDIA-L4-GPUS-per-project-region", {"region": region}, 4),
           ("NVIDIA-A100-80GB-GPUS-per-project-region", {"region": region}, 2)]
    # the per-zone GPU quotas are fixed (Google refuses a change with 'is_fixed'); they follow the region limit
    return [{"quotaId": q, "dimensions": d, "preferredValue": v} for q, d, v in out]


def body(project, w, email=None):
    """The quotaPreferences resource sent for one wanted item (pure; tested)."""
    return {"service": "compute.googleapis.com", "quotaId": w["quotaId"], "quotaConfig": {"preferredValue": str(w["preferredValue"])},
            "dimensions": w["dimensions"], "justification": JUSTIFICATION, **({"contactEmail": email} if email else {})}


def preference_id(project, w):
    return "bench-" + "-".join([w["quotaId"].lower()] + [v for _, v in sorted(w["dimensions"].items())])[:60].rstrip("-")


def token():
    r = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True)
    if r.returncode: raise SystemExit("gcloud auth failed: " + r.stderr.strip()[:200])
    return r.stdout.strip()


def call(method, url, project, data=None):
    req = urllib.request.Request(url, json.dumps(data).encode() if data is not None else None, method=method,
                                 headers={"Authorization": "Bearer " + token(), "X-Goog-User-Project": project, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, {"error": e.read().decode()[:400]}


def arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    if not argv: print(__doc__); return 1
    cmd = argv[0]; project = os.environ.get("GCP_PROJECT") or subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True).stdout.strip()
    region = arg(argv, "--region", "us-central1"); zones = tuple((arg(argv, "--zones") or f"{region}-a").split(","))
    items = wanted(region, zones)
    if cmd == "plan":
        for w in items: print(f"{w['quotaId']:48} {json.dumps(w['dimensions']):32} -> {w['preferredValue']}")
        print("(nothing sent: add `request --yes`)"); return 0
    if cmd == "show":
        for w in items:
            s, d = call("GET", f"{API}/projects/{project}/locations/global/services/compute.googleapis.com/quotaInfos/{w['quotaId']}", project)
            if s != 200: print(w["quotaId"], "failed:", s, d.get("error", "")[:100]); continue
            eligible = (d.get("quotaIncreaseEligibility") or {}).get("isEligible")
            hits = [di for di in d.get("dimensionsInfos", []) if all(di.get("dimensions", {}).get(k) == v for k, v in w["dimensions"].items())]
            # an int64 of 0 is left out of the JSON, and a place with no override has no entry: both mean "the default", which for a GPU is usually 0 or 1
            val = (hits[0].get("details") or {}).get("value", "0 (or the default)") if hits else "no override (the default)"
            print(f"{w['quotaId']:48} {json.dumps(w['dimensions']):32} limit {val}; increase eligible: {eligible}")
        return 0
    if cmd == "request":
        if "--yes" not in argv: print("add --yes to send these requests (use `plan` to see them)"); return 1
        bad = 0
        for w in items:
            s, d = call("POST", f"{API}/projects/{project}/locations/global/quotaPreferences?quotaPreferenceId={preference_id(project, w)}", project, body(project, w, arg(argv, "--email")))
            print(f"{w['quotaId']} {w['dimensions']} -> {w['preferredValue']}: " + ("filed" if s == 200 else f"failed {s} {d.get('error', '')[:160]}")); bad += s != 200
        return 1 if bad else 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
