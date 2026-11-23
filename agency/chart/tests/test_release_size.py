"""python3 agency/chart/tests/test_release_size.py   (needs helm; skipped without it). Helm stores a release in ONE Secret, capped at 1 MiB (1,048,576 bytes), and a deploy that goes over fails
at the last step with `Secret "sh.helm.release.v1.omnigate.v1" is invalid: data: Too long`: that is how the first AWS clean-room failed, when the Agency code and UI were carried in the chart.
This estimates the stored size the way Helm does (the chart's files base64-encoded in JSON, with the rendered manifest, gzipped, then base64) and requires every chart, for the selections
that matter, to stay under a budget with a safety margin. The estimate matched the real failure (1.08 MB estimated, over the limit; the deploy was rejected)."""
import base64, gzip, json, os, shutil, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D
LIMIT = 1048576; BUDGET = int(LIMIT * 0.80)          # a fifth of headroom: the estimate is not Helm's exact encoding
SIX = "supply-chain,manufacturing,it-risk,smithsonian,bom,treasury"
CASES = {"all-packs": ["demoDataset=all-packs"], "it-risk + Agency": ["agency.enabled=true", "demoDatasets={it-risk,agency-risk}"],
         "all six + Agency": ["agency.enabled=true", "demoDatasets={%s,agency-risk}" % SIX],
         "all six + Agency + workflows": ["agency.enabled=true", "agency.workflows.enabled=true", "demoDatasets={%s,agency-risk}" % SIX, "omnigate.license=x", "omnigate.adminApiToken=t"]}

def stored_size(chart, sets):
    files = []
    for d, _, fs in os.walk(chart):
        for f in fs:
            p = os.path.join(d, f); files.append({"name": os.path.relpath(p, chart), "data": base64.b64encode(open(p, "rb").read()).decode()})
    a = ["helm", "template", "omnigate", chart, "--set", D.USERS] + [x for s in sets for x in ("--set", s)]
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[:300])
    return len(base64.b64encode(gzip.compress(json.dumps({"chart": {"files": files}, "manifest": r.stdout}).encode(), 9)))

@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class ReleaseSize(unittest.TestCase):
    def test_every_chart_and_selection_fits_with_headroom(self):
        for cloud, chart in D.CHARTS.items():
            for label, sets in CASES.items():
                with self.subTest(chart=cloud, case=label):
                    n = stored_size(os.path.join(ROOT, chart), sets)
                    self.assertLess(n, BUDGET, "%s / %s: about %d bytes stored, budget %d, Helm's cap %d" % (cloud, label, n, BUDGET, LIMIT))
if __name__ == "__main__": unittest.main()
