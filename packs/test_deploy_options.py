"""python3 -m unittest discover -s packs   (from the repository root)"""
import json, os, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D

O = json.load(open(os.path.join(HERE, "deploy-options.json")))
SAMPLE = """
kind: PersistentVolumeClaim
metadata:
  name: rel-omnigate-data
spec:
  resources:
    requests:
      storage: 2Gi
---
kind: Deployment
metadata:
  name: rel-omnigate
spec:
  replicas: 2
  template:
    spec:
      initContainers:
        - name: init
          resources:
            requests:
              cpu: 999m
              memory: 999Mi
      containers:
        - name: app
          resources:
            limits:
              memory: 3Gi
            requests:
              cpu: 500m
              memory: 1Gi
      volumes:
        - name: v
---
kind: StatefulSet
metadata:
  name: rel-postgres
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: db
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
  volumeClaimTemplates:
    - spec:
        resources:
          requests:
            storage: 5Gi
---
kind: Job
spec:
  template:
    spec:
      containers:
        - resources:
            requests:
              cpu: 4
              memory: 8Gi
"""


class T(unittest.TestCase):
    def test_the_generated_file_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "deploy_options.py"), "check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_measure_counts_replicas_ignores_init_containers_and_jobs_and_adds_volumes(self):
        m = D.measure(SAMPLE)
        self.assertEqual({k: m[k] for k in ("memoryMi", "cpuMilli", "diskGi")}, {"memoryMi": 2 * 1024 + 256, "cpuMilli": 2 * 500 + 100, "diskGi": 2 + 5})
        self.assertEqual(m["byComponent"]["base"]["memoryMi"], 2 * 1024 + 256)

    def test_units(self):
        self.assertEqual((D.mem_mi("1Gi"), D.mem_mi("512Mi"), D.cpu_milli("500m"), D.cpu_milli('"1"')), (1024, 512, 500, 1000))

    def test_the_cost_model_reproduces_every_configuration(self):
        base = O["components"]["base"]
        for c in O["configurations"]:
            needs = {n for p in c["packs"] for n in next(x for x in O["packs"] if x["id"] == p)["needs"]}
            for k in ("memoryMi", "cpuMilli", "diskGi"): self.assertEqual(base[k] + sum(O["components"][n][k] for n in needs), c[k], (c["demoDataset"], k))

    def renders(self):
        cm = {"base": dict(memoryMi=1280, cpuMilli=600, diskGi=7), "mariadb": dict(memoryMi=256, cpuMilli=100, diskGi=2), "embedding": dict(memoryMi=512, cpuMilli=250, diskGi=0),
              "objectStore": dict(memoryMi=0, cpuMilli=0, diskGi=1)}
        need = {"supply-chain": ["base"], "it-risk": ["base", "mariadb"], "bom": ["base", "embedding"], "treasury": ["base", "mariadb", "embedding"], "all-packs": ["base", "mariadb", "embedding", "objectStore"]}
        out = {}
        for ds, cs in need.items():
            out[ds] = {k: sum(cm[c][k] for c in cs) for k in ("memoryMi", "cpuMilli", "diskGi")}; out[ds]["byComponent"] = {c: dict(cm[c]) for c in cs}
        return out

    def test_a_cost_model_that_disagrees_with_the_charts_fails_loudly(self):
        ms = D.P.load_manifests(); good = self.renders(); D.derive(ms, {"aws": good})
        bad = json.loads(json.dumps(good)); bad["all-packs"]["byComponent"]["base"]["memoryMi"] += 700; bad["all-packs"]["memoryMi"] += 700      # the app asking for more memory in the all-packs set only
        with self.assertRaises(SystemExit): D.derive(ms, {"aws": bad})
        other = json.loads(json.dumps(good)); other["bom"]["byComponent"]["embedding"]["memoryMi"] += 1; other["bom"]["memoryMi"] += 1
        with self.assertRaises(SystemExit): D.derive(ms, {"aws": good, "oci": other})         # the four charts disagree
        extra = json.loads(json.dumps(good)); extra["treasury"]["byComponent"]["objectStore"] = dict(memoryMi=0, cpuMilli=0, diskGi=1)
        with self.assertRaises(SystemExit): D.derive(ms, {"aws": extra})                       # a pack rendering a component its manifest does not declare

    def test_a_workload_the_cost_model_does_not_know_fails_the_build(self):
        with self.assertRaises(SystemExit): D.measure(SAMPLE.replace("name: rel-postgres", "name: rel-newthing"))

    def test_one_pack_and_all_packs_give_the_stack_the_matching_dataset_always_gave(self):
        for p in ("it-risk", "bom", "treasury"):
            r = D.resolve([p], O); self.assertTrue(r["supported"], p); self.assertEqual((r["demoDataset"], r["demoDatasets"]), (p, [p]))
        r = D.resolve(["supply-chain", "manufacturing"], O); self.assertEqual(r["demoDataset"], "supply-chain")           # the default supply-chain stack always carried manufacturing
        r = D.resolve([p["id"] for p in O["packs"]], O); self.assertEqual((r["supported"], r["demoDataset"], r["memoryRequestsMi"]), (True, "all-packs", 2048))
        self.assertEqual(r["demoDatasets"], D.CANONICAL)

    def test_a_mix_is_deployable_with_its_real_cost_and_the_list_to_give_the_chart(self):
        r = D.resolve(["treasury", "bom"], O)
        self.assertTrue(r["supported"]); self.assertIsNone(r["demoDataset"]); self.assertEqual(r["demoDatasets"], ["bom", "treasury"]); self.assertEqual(r["problems"], [])
        self.assertEqual(r["memoryRequestsMi"], 2048)                                                                       # no more memory than treasury alone
        self.assertEqual(D.resolve(["bom"], O)["memoryRequestsMi"], 1792); self.assertEqual(D.resolve(["treasury"], O)["memoryRequestsMi"], 2048)

    def test_the_list_follows_the_charts_order_whatever_order_it_was_given(self):
        self.assertEqual(D.resolve(["treasury", "bom", "supply-chain"], O)["demoDatasets"], ["supply-chain", "bom", "treasury"])

    def test_smithsonian_only_comes_with_all_six(self):
        for sel in (["smithsonian"], ["bom", "smithsonian"], ["supply-chain", "it-risk", "bom", "treasury", "smithsonian"]):
            r = D.resolve(sel, O); self.assertFalse(r["supported"], sel); self.assertTrue(any("only deployed together with all" in x for x in r["problems"]), sel)
            self.assertIsNone(r["demoDatasets"])

    def test_every_verified_selection_is_deployable_and_its_cost_is_what_resolve_says(self):
        self.assertGreaterEqual(len(O["verifiedSelections"]), 8)
        for v in O["verifiedSelections"]:
            r = D.resolve(v["packs"], O); self.assertTrue(r["supported"], v["packs"])
            self.assertEqual((r["memoryRequestsMi"], r["cpuRequestsMilli"], r["diskGi"]), (v["memoryMi"], v["cpuMilli"], v["diskGi"]), v["packs"])

    def test_adding_a_pack_that_needs_no_new_component_costs_nothing(self):
        self.assertEqual(D.resolve(["treasury", "bom"], O)["memoryRequestsMi"], D.resolve(["treasury"], O)["memoryRequestsMi"])
        self.assertGreater(D.resolve(["bom", "it-risk"], O)["memoryRequestsMi"], D.resolve(["bom"], O)["memoryRequestsMi"])      # MariaDB is new there

    def test_a_pack_that_extends_another_brings_it_along(self):
        r = D.resolve(["manufacturing"], O); self.assertEqual(r["selected"], ["manufacturing", "supply-chain"]); self.assertTrue(any("needs supply-chain" in n for n in r["notes"]))

    def test_docker_only_packs_unknown_ids_and_empty_selections_are_refused_with_a_reason(self):
        self.assertTrue(any("Docker only" in x for x in D.resolve(["treasury", "sounds"], O)["problems"]))
        self.assertTrue(any("no such pack" in x for x in D.resolve(["nope"], O)["problems"]))
        r = D.resolve([], O); self.assertFalse(r["supported"]); self.assertTrue(any("nothing selected" in x for x in r["problems"]))
        self.assertFalse(D.resolve(["treasury", "sounds"], O)["supported"])

    def test_payment_workflow_add_on_needs_treasury_on_its_own(self):
        self.assertTrue(D.resolve(["treasury"], O)["paymentWorkflowAddOn"]); self.assertFalse(D.resolve(["treasury", "bom"], O)["paymentWorkflowAddOn"]); self.assertFalse(D.resolve(["bom"], O)["paymentWorkflowAddOn"])

    def test_a_selection_is_the_same_whatever_order_or_repeats(self):
        self.assertEqual(D.resolve(["bom", "treasury", "bom"], O), D.resolve(["treasury", "bom"], O))

    def test_every_pack_names_only_known_components_and_every_configuration_only_known_packs(self):
        ids = {p["id"] for p in O["packs"]}
        for p in O["packs"]: self.assertTrue(set(p["needs"]) <= set(O["components"]) - {"base"}, p["id"])
        for c in O["configurations"]: self.assertTrue(set(c["packs"]) <= ids, c["demoDataset"])
        self.assertEqual({e["id"] for e in O["excluded"]}, {"sounds"})


if __name__ == "__main__": unittest.main()
