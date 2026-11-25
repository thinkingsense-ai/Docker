"""python3 agency/chart/tests/test_values.py   (needs helm; skipped without it). Guards the agency values: the image keys sit in the agency block and nowhere else, are pinned by digest, and an
install with agency.enabled and NO image override renders a real image for the Agency pod (the first AWS rehearsals always passed an override, which hid a missing default)."""
import os, re, shutil, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D

def render(chart, *sets):
    a = ["helm", "template", "rel", os.path.join(ROOT, chart), "--set", D.USERS] + [x for s in sets for x in ("--set", s)]
    return subprocess.run(a, capture_output=True, text=True)

@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class Values(unittest.TestCase):
    def test_images_are_in_the_agency_block_only_and_pinned(self):
        for cloud, chart in D.CHARTS.items():
            with self.subTest(chart=cloud):
                v = open(os.path.join(ROOT, chart, "values.yaml")).read(); head, _, tail = v.partition("\nagency:\n")
                self.assertNotRegex(head, r"(?m)^  image: .*omnigate/agency", "an Agency image key leaked into another block")
                self.assertEqual(len(re.findall(r"(?m)^  image: us-docker\.pkg\.dev/thinkingsense/omnigate/agency:\S+@sha256:[0-9a-f]{64}$", tail)), 1)
                self.assertEqual(len(re.findall(r"(?m)^    image: us-docker\.pkg\.dev/thinkingsense/omnigate/agency-workflows:\S+@sha256:[0-9a-f]{64}$", tail)), 1)
    def test_the_default_image_renders_without_an_override(self):
        for cloud, chart in D.CHARTS.items():
            with self.subTest(chart=cloud):
                r = render(chart, "agency.enabled=true", "demoDatasets={agency-risk}"); self.assertEqual(r.returncode, 0, r.stderr)
                m = re.search(r"- name: agency\n\s+image: (\S+)", r.stdout); self.assertTrue(m and m.group(1).startswith("us-docker.pkg.dev/thinkingsense/omnigate/agency:"), m and m.group(1))
                r = render(chart, "agency.enabled=true", "agency.workflows.enabled=true", "demoDatasets={agency-risk}", "omnigate.license=x", "omnigate.adminApiToken=t"); self.assertEqual(r.returncode, 0, r.stderr)
                imgs = set(re.findall(r"image: (\S*agency-workflows\S*)", r.stdout)); self.assertEqual(len(imgs), 1, imgs)
    def test_the_feed_is_off_by_default_and_renders_when_asked(self):
        for cloud, chart in D.CHARTS.items():
            with self.subTest(chart=cloud):
                off = render(chart, "agency.enabled=true", "demoDatasets={agency-risk}"); self.assertEqual(off.returncode, 0, off.stderr); self.assertNotIn("agency-feed", off.stdout)
                on = render(chart, "agency.enabled=true", "agency.feed.enabled=true", "demoDatasets={agency-risk}"); self.assertEqual(on.returncode, 0, on.stderr)
                imgs = set(re.findall(r"image: (\S*agency-feed\S*)", on.stdout)); self.assertEqual(len(imgs), 1, imgs)
                self.assertRegex(next(iter(imgs)), r"@sha256:[0-9a-f]{64}$"); self.assertIn("feed_writer", on.stdout); self.assertIn("FEED_INTERVAL_MINUTES", on.stdout)
    def test_the_feed_refuses_to_install_without_what_it_needs(self):
        chart = D.CHARTS["aws"]
        self.assertNotEqual(render(chart, "agency.feed.enabled=true").returncode, 0)
        r = render(chart, "agency.enabled=true", "agency.feed.enabled=true", "demoDataset=treasury"); self.assertNotEqual(r.returncode, 0); self.assertIn("agency-risk", r.stderr)
if __name__ == "__main__": unittest.main()
