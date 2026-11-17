#!/usr/bin/env python3
"""What a person choosing packs for a cloud stack needs to see, and which choices the charts can deploy today (docs/agency-design.md, section 4; phase 6).

  python3 scripts/deploy_options.py check       fail if packs/deploy-options.json is out of date (re-measures with helm when it is installed, else only checks the file is consistent)
  python3 scripts/deploy_options.py generate    re-measure with helm and rewrite packs/deploy-options.json
  python3 scripts/deploy_options.py resolve bom treasury      what that selection would cost and whether the charts can deploy it

The cost of a selection is NOT the sum of its packs: it is the base (the app and Postgres) plus each COMPONENT a selected pack needs once (MariaDB for a pack with an `mdb`
source, the embedding model for a pack that needs one, the object store for a `files` source). The component costs are measured from `helm template` on the four charts
(requests of the long-running workloads, and volume sizes), and the formula is checked against every configuration the charts render today, so a chart change that moves a number
fails `check`. The charts take a list of packs (`demoDatasets`) and compose any mix of them, except that the Smithsonian pack (object store, loader, vocabulary) is only deployed
with all six; every mix in SAMPLE_SELECTIONS is rendered with helm and its measured cost must equal the cost this model predicts."""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import packs as P

OUT = os.path.join(ROOT, "packs", "deploy-options.json")
CHARTS = {"aws": "resource-manager/omnigateeksstack/helm-deployer-lambda/omnigate-chart", "oci": "resource-manager/omnigateokestack/helm/omnigate",
          "gcp": "resource-manager/omnigategkestack/helm/omnigate", "azure": "resource-manager/omnigateaksstack/helm/omnigate"}
USERS = "omnigate.appUsers=demo:lJX+xXgLcPmnjyXStA9VQQ==:HdoV/jHar1OSBbnTk8Iu8fbLcoBGFJ/Qe83zERd4Mac=::"      # any valid entry: the chart refuses to render without one
DATASETS = ["supply-chain", "it-risk", "bom", "treasury", "all-packs"]
# What each component is, in the chart's words: which source / need pulls it in.
COMPONENT_OF = {"mariadb": lambda p: any(s["id"] == "mdb" for s in p["sources"]), "embedding": lambda p: bool(p.get("needsEmbeddingModel")),
                "objectStore": lambda p: any(s["id"] == "files" for s in p["sources"])}
COMPONENT_TEXT = {"base": "the app and Postgres", "mariadb": "MariaDB (a pack with an mdb source)", "embedding": "the embedding model (approved questions are only matched with it)",
                  "objectStore": "the in-cluster object store and its loader (the museum directory)"}
CANONICAL = ["supply-chain", "manufacturing", "it-risk", "smithsonian", "bom", "treasury"]          # the order the charts put a selection in
# Selections rendered with helm on every `check`/`generate`: the cost model must predict what each one costs, and each must render on the four charts.
SAMPLE_SELECTIONS = [["supply-chain"], ["manufacturing"], ["bom", "treasury"], ["it-risk", "treasury"], ["it-risk", "bom"], ["supply-chain", "bom"], ["supply-chain", "treasury"],
                     ["manufacturing", "bom", "treasury"], ["supply-chain", "it-risk", "bom", "treasury"], ["supply-chain", "manufacturing", "it-risk", "bom", "treasury"]]
FIT_NOTE = "Measured 2026-11-13 on AWS (eks-stack-v1.0.32, default t4g.medium): 2048 Mi of memory requests used 83% of what the node could give, so there is no room for a second large workload."


def mem_mi(s):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(Ki|Mi|Gi|k|M|G)?", s.strip().strip('"'))
    f = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "k": 0.000954, "M": 0.9537, "G": 953.67, None: 1 / 1048576}[m.group(2)]
    return float(m.group(1)) * f


def cpu_milli(s):
    s = s.strip().strip('"'); return float(s[:-1]) if s.endswith("m") else float(s) * 1000


# The long-running workloads (and their volumes) by name, release prefix stripped, and the component each belongs to. A workload this table does not know fails the build:
# a new pod in a chart must be placed in the cost model on purpose.
WORKLOAD_COMPONENT = {"omnigate": "base", "postgres": "base", "mariadb": "mariadb", "packs-embed": "embedding", "packs-s3": "objectStore"}


def measure(rendered):
    """Memory (Mi), CPU (milli) requests of the long-running workloads (every replica) and the size (Gi) of their volumes, from `helm template` output, in total and per
    component (`byComponent`)."""
    by = {}
    def add(name, m=0.0, c=0.0, d=0.0):
        comp = WORKLOAD_COMPONENT.get(name.split("-", 1)[1] if "-" in name else name)
        if comp is None: raise SystemExit("the chart renders a workload or volume called %r that the deploy-options cost model does not know: place it in WORKLOAD_COMPONENT" % name)
        t = by.setdefault(comp, [0.0, 0.0, 0.0]); t[0] += m; t[1] += c; t[2] += d
    for doc in re.split(r"(?m)^---\s*$", rendered):
        kind = re.search(r"(?m)^kind: (\w+)", doc)
        if not kind: continue
        nm = re.search(r"(?m)^metadata:\s*\n(?:\s+.*\n)*?  name: (\S+)", doc)
        name = nm.group(1) if nm else "rel-?"
        if kind.group(1) in ("PersistentVolumeClaim",):
            add(re.sub(r"-data$", "", name), d=sum(float(x) for x in re.findall(r"(?m)^\s+storage: (\d+)Gi", doc)))
        if kind.group(1) not in ("Deployment", "StatefulSet"): continue
        rep = re.search(r"(?m)^  replicas: (\d+)", doc); n = int(rep.group(1)) if rep else 1
        body = re.split(r"(?m)^\s+containers:\s*$", doc, maxsplit=1)[1] if re.search(r"(?m)^\s+containers:\s*$", doc) else ""
        body = re.split(r"(?m)^\s+volumes:\s*$", body, maxsplit=1)[0]
        m = c = 0.0
        for r in re.finditer(r"(?m)^\s+requests:\s*\n((?:\s+(?:cpu|memory): \S+\n?){1,2})", body):
            for k, v in re.findall(r"(cpu|memory): (\S+)", r.group(1)):
                if k == "memory": m += mem_mi(v)
                else: c += cpu_milli(v)
        add(name, m * n, c * n, n * sum(float(x) for x in re.findall(r"(?m)^\s+storage: (\d+)Gi", doc.split("volumeClaimTemplates:", 1)[1])) if "volumeClaimTemplates:" in doc else 0)
    tot = [sum(v[i] for v in by.values()) for i in range(3)]
    return {"memoryMi": round(tot[0]), "cpuMilli": round(tot[1]), "diskGi": round(tot[2]),
            "byComponent": {k: {"memoryMi": round(v[0]), "cpuMilli": round(v[1]), "diskGi": round(v[2])} for k, v in sorted(by.items())}}


def helm_render(chart, dataset=None, selection=None):
    sel = ["--set", "demoDatasets={%s}" % ",".join(selection)] if selection else ["--set", "demoDataset=" + dataset]
    r = subprocess.run(["helm", "template", "rel", os.path.join(ROOT, chart), "--set", USERS] + sel, capture_output=True, text=True)
    if r.returncode: raise SystemExit("helm template failed for %s/%s: %s" % (chart, dataset or selection, r.stderr.strip()[:300]))
    return r.stdout


def components_of(pack_ids, ms):
    by = {p["id"]: p for p in ms}
    return sorted({c for i in pack_ids for c, f in COMPONENT_OF.items() if f(by[i])})


def cloud_packs(ms): return [p for p in ms if p["inAllPacks"] and not (set(p["editions"]) <= {"docker"})]


def derive(ms, renders, mixes=None):
    """Component costs from the renders, and the check that base + components reproduces every render. `renders` is {cloud: {dataset: measure()}}."""
    cloud = {p["id"]: p for p in cloud_packs(ms)}
    cfg = {"supply-chain": ["supply-chain", "manufacturing"], "it-risk": ["it-risk"], "bom": ["bom"], "treasury": ["treasury"], "all-packs": sorted(cloud)}
    for c, rs in renders.items():
        if rs != renders[next(iter(renders))]: raise SystemExit("the four charts do not request the same resources for the same data set (%s differs)" % c)
    r = renders[next(iter(renders))]
    KEYS = ("memoryMi", "cpuMilli", "diskGi")
    # Each component's cost is read from the workloads of that component in the render where it appears: nothing is derived by subtracting one data set from another.
    comp = {"base": dict(r["supply-chain"]["byComponent"]["base"])}
    for c, ds in (("mariadb", "it-risk"), ("embedding", "bom"), ("objectStore", "all-packs")): comp[c] = dict(r[ds]["byComponent"][c])
    for ds, ids in cfg.items():
        needs = ["base"] + components_of(ids, ms)
        if sorted(r[ds]["byComponent"]) != sorted(needs): raise SystemExit("%s renders the components %s but its packs need %s: a chart changed or the packs' needs are wrong" % (ds, sorted(r[ds]["byComponent"]), sorted(needs)))
        for c in needs:
            if r[ds]["byComponent"][c] != comp[c]: raise SystemExit("%s: component %s costs %s there but %s in %s: the cost model is wrong or a chart changed" % (ds, c, r[ds]["byComponent"][c], comp[c], "its first render"))
        want = {k: sum(comp[c][k] for c in needs) for k in KEYS}
        if {k: r[ds][k] for k in KEYS} != want: raise SystemExit("components give %s for %s, the chart renders %s" % (want, ds, {k: r[ds][k] for k in KEYS}))
    verified = []
    for sel, rs in (mixes or {}).items():
        ids = sel.split(",")
        for c, m in rs.items():
            needs = ["base"] + components_of(ids, ms)
            if sorted(m["byComponent"]) != sorted(needs): raise SystemExit("[%s] on the %s chart renders the components %s but the model predicts %s" % (sel, c, sorted(m["byComponent"]), sorted(needs)))
            want = {k: sum(comp[n][k] for n in needs) for k in KEYS}
            if {k: m[k] for k in KEYS} != want: raise SystemExit("[%s] on the %s chart costs %s but the model predicts %s" % (sel, c, {k: m[k] for k in KEYS}, want))
        verified.append({"packs": ids, **{k: next(iter(rs.values()))[k] for k in KEYS}})
    return comp, cfg, {ds: {k: v for k, v in x.items() if k != "byComponent"} for ds, x in r.items()}, verified


def build(renders, mixes=None):
    ms = P.load_manifests(); cat = {e["id"]: e for e in json.loads(P.catalogue(ms))["packs"]}
    comp, cfg, r, verified = derive(ms, renders, mixes)
    return {
        "note": "Generated by scripts/deploy_options.py from packs/*/pack.json and `helm template` of the four charts. Do not edit; run `python3 scripts/deploy_options.py generate`.",
        "components": {k: dict(v, what=COMPONENT_TEXT[k]) for k, v in comp.items()},
        "packs": [{"id": p["id"], "title": p["title"], "summary": p["summary"], "tables": cat[p["id"]]["tables"], "approvedQuestions": cat[p["id"]]["questions"]["approved"],
                   "connectors": sorted({s["id"] for s in p["sources"]}), "needs": components_of([p["id"]], ms), "extends": p.get("extends"), "capabilities": p.get("capabilities", []),
                   "editions": p["editions"], "licence": p["licence"]} for p in cloud_packs(ms)],
        "excluded": [{"id": p["id"], "reason": "Docker only: " + ("non-commercial data and models" if p["licence"].get("nonCommercial") else "not built for the cloud stacks")} for p in ms if p not in cloud_packs(ms)],
        "configurations": [dict(demoDataset=ds, packs=ids, **r[ds]) for ds, ids in cfg.items()],
        "verifiedSelections": [dict(v, memoryMi=v["memoryMi"]) for v in verified],
        "fit": FIT_NOTE,
        "rules": [
            "The charts take a list of packs (demoDatasets) and compose any mix of them. One pack or all six gives exactly the stack the matching demoDataset always gave; any other mix is deployed the all-packs way (one connector per kind, schemas discovered) holding only the chosen packs and their approved questions.",
            "The Smithsonian pack (object store, loader, vocabulary) is only deployed together with all six packs for now.",
            "A pack that extends another needs it: manufacturing adds tables to the supply-chain schemas, so it brings supply-chain along.",
            "Cost is the base plus each component a selected pack needs, once. Adding a pack to a selection that already needs a component costs nothing in memory.",
            "Free edition: at most 3 data sources. The packs share one Postgres connector, one MariaDB and one object store, so no mix goes over; supply-chain registers its three schemas as its three.",
            "The payment-workflow add-on needs the treasury pack on its own (all packs is not supported yet).",
        ],
    }


def resolve(ids, opts=None):
    """What the selection would cost and whether the charts can deploy it, and the `demoDatasets` list to give the chart. Pure: reads packs/deploy-options.json."""
    o = opts or json.load(open(OUT)); by = {p["id"]: p for p in o["packs"]}; problems, notes = [], []
    sel = list(dict.fromkeys(ids))
    for i in list(sel):
        if i in by: continue
        ex = next((e for e in o["excluded"] if e["id"] == i), None)
        problems.append("%s: %s" % (i, ex["reason"] if ex else "no such pack")); sel.remove(i)
    if not sel and not problems: problems.append("nothing selected: choose at least one pack")
    for i in list(sel):
        e = by[i].get("extends")
        if e and e not in sel: sel.append(e); notes.append("%s needs %s, which was added" % (i, e))
    needs = sorted({c for i in sel for c in by[i]["needs"]})
    tot = dict(o["components"]["base"]); tot.pop("what", None)
    for c in needs:
        for k in tot: tot[k] += o["components"][c][k]
    allp = sorted(by)
    if "smithsonian" in sel and len(sel) != len(allp): problems.append("smithsonian: the Smithsonian pack (object store, loader, vocabulary) is only deployed together with all %d packs for now" % len(allp))
    cfg = next((c["demoDataset"] for c in o["configurations"] if sorted(c["packs"]) == sorted(sel)), None)
    supported = bool(sel) and not problems
    order = [i for i in CANONICAL if i in sel] + sorted(i for i in sel if i not in CANONICAL)
    return {"selected": sorted(sel), "supported": supported, "demoDatasets": order if supported else None, "demoDataset": cfg if supported else None, "components": ["base"] + needs,
            "memoryRequestsMi": tot["memoryMi"], "cpuRequestsMilli": tot["cpuMilli"], "diskGi": tot["diskGi"], "problems": problems, "notes": notes,
            "paymentWorkflowAddOn": sel == ["treasury"]}


def text(o): return json.dumps(o, indent=2, ensure_ascii=False) + "\n"


def measured():
    if not shutil.which("helm"): return None
    base = {c: {ds: measure(helm_render(ch, ds)) for ds in DATASETS} for c, ch in CHARTS.items()}
    mixes = {",".join(sel): {c: measure(helm_render(ch, selection=sel)) for c, ch in CHARTS.items()} for sel in SAMPLE_SELECTIONS}
    return base, mixes


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "resolve":
        print(json.dumps(resolve(argv[2:]), indent=2)); return 0
    cur = json.load(open(OUT)) if os.path.isfile(OUT) else None
    m = measured()
    if m is None:
        if cmd == "generate": print("helm is needed to generate"); return 1
        if cur is None: print("packs/deploy-options.json is missing (and helm is not installed to make it)"); return 1
        print("ok (helm not installed: the file was not re-measured)"); return 0
    want = text(build(*m))
    if cmd == "generate":
        open(OUT, "w").write(want); print("wrote packs/deploy-options.json"); return 0
    if cur is None or text(cur) != want: print("out of date (run: python3 scripts/deploy_options.py generate)"); return 1
    print("ok: deploy options current and re-measured from the four charts"); return 0


if __name__ == "__main__": sys.exit(main(sys.argv))
