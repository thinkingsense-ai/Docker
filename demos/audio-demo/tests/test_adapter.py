"""python3 -m unittest discover -s demos/audio-demo/tests   (no torch needed)"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import adapter

R = {"seconds": 12.0, "group": {"guess": "bird", "margin": 0.2},
     "birdnet_expected": [{"scientific": "Cardinalis cardinalis", "common": "Northern Cardinal", "confidence": 0.9}],
     "birdnet_all": [{"scientific": "Zonotrichia leucophrys", "common": "White-crowned Sparrow", "confidence": 0.95}],
     "nearest": [{"id": "xc1", "species": "Cardinalis cardinalis", "common": "Northern Cardinal", "country": "US", "license": "CC BY-NC-SA", "similarity": 0.8, "audio": "/audio/xc1"}],
     "species": {"scientific": "Cardinalis cardinalis", "recordings": 6}}

class T(unittest.TestCase):
    def test_accepts_by_extension_or_mime(self):
        self.assertTrue(adapter.accepts("a.WAV")); self.assertTrue(adapter.accepts("noext", "audio/mpeg; charset=x")); self.assertFalse(adapter.accepts("a.pdf", "application/pdf"))
    def test_manifest_is_honest_about_licence(self):
        self.assertTrue(adapter.MANIFEST["nonCommercial"]); self.assertIn("non-commercial", adapter.MANIFEST["licence"])
    def test_record_flags_confident_disagreement_and_names_the_species_in_prompts(self):
        r = adapter.record(R, "clip.wav")
        self.assertTrue(any("confidently wrong" in n for n in r["notes"]))
        self.assertTrue(all("Cardinalis cardinalis" in p or "xc1" in p for p in r["askPrompts"])); self.assertEqual(len(r["askPrompts"]), 4)
        self.assertNotIn("audio", r["result"]["nearest"][0])         # no media path leaks into the record
    def test_record_without_a_confident_bird_has_no_prompts(self):
        r = adapter.record(dict(R, birdnet_expected=[], species=None, group={"guess": "fish", "margin": 0.1}), "x.wav")
        self.assertEqual(r["askPrompts"], [])
        self.assertTrue(any("nothing confident" in n for n in r["notes"])); self.assertTrue(any("fish" in n for n in r["notes"]))
    def test_a_weak_guess_offers_no_species_questions(self):
        weak = dict(R, birdnet_expected=[{"scientific": "Cardinalis cardinalis", "common": "Northern Cardinal", "confidence": 0.01}])
        r = adapter.record(weak, "tone.wav"); self.assertEqual(r["askPrompts"], []); self.assertIsNone(r["result"]["species"])
        self.assertTrue(any("only 1%" in n for n in r["notes"]))
    def test_an_engine_error_is_raised(self):
        with self.assertRaises(ValueError): adapter.record({"error": "The clip is shorter than one second."}, "x.wav")

if __name__ == "__main__": unittest.main()
