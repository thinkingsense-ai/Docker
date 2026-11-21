"""The pilot harness: label parsing, intervals, feed precision and the recall estimate, the priorities scores, rank correlation, reproducible sampling and a full score() over planted sheets.
Expected values were worked out by hand. Run: python3 -m unittest demos/it-risk-pilot/test_pilot.py (from the repo root). No network, no Server."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot as P

SYS = ["Domain controllers", "Payment gateway (production)", "Payment gateway (disaster recovery)", "Branch voice and ATM link", "Backup vault", "Core banking database",
       "Customer web portal", "Back-office application servers", "Branch file servers", "Analytics warehouse", "HR system"]
OURS = ["Critical", "High", "High", "Medium", "Medium", "Medium", "Medium", "Medium", "Medium", "Low", "Low"]


def rows(his, ranks=None):
    return [{"system": s, "our_rank": i + 1, "our_rating": OURS[i], "leo_rating": his[i], "leo_rank": (ranks[i] if ranks else None)} for i, s in enumerate(SYS)]


class Labels(unittest.TestCase):
    def test_labels_are_forgiving_about_case_spaces_and_dashes_but_not_about_meaning(self):
        for s, want in (("relevant", "relevant"), ("Real and relevant", "relevant"), ("not-for-us", "not_for_us"), ("Real but not for us", "not_for_us"), ("NOT REAL", "not_real"), ("", None), ("  ", None)):
            self.assertEqual(P.norm_label(s), want, s)
        self.assertIs(P.norm_label("yes"), False); self.assertIs(P.norm_label("maybe"), False)
    def test_ratings_are_the_four_values_only(self):
        self.assertEqual(P.norm_rating(" critical "), "Critical"); self.assertIsNone(P.norm_rating("")); self.assertIs(P.norm_rating("Moderate"), False); self.assertIs(P.norm_rating("P1"), False)


class Intervals(unittest.TestCase):
    def test_wilson_matches_the_textbook_value(self):
        lo, hi = P.wilson(8, 10); self.assertAlmostEqual(lo, 0.490, 3); self.assertAlmostEqual(hi, 0.943, 3)
        self.assertIsNone(P.wilson(0, 0)); lo, hi = P.wilson(0, 10); self.assertEqual(lo, 0.0); self.assertGreater(hi, 0.2)
    def test_kendall_is_one_for_the_same_order_minus_one_for_the_reverse_and_handles_ties(self):
        same = [(i, i) for i in range(1, 6)]; rev = [(i, 6 - i) for i in range(1, 6)]
        self.assertAlmostEqual(P.kendall_tau_b(same), 1.0); self.assertAlmostEqual(P.kendall_tau_b(rev), -1.0)
        self.assertIsNone(P.kendall_tau_b([(1, 1)])); self.assertIsNone(P.kendall_tau_b([(1, 1), (1, 2)]))


class Feed(unittest.TestCase):
    def lab(self, *labels): return [{"label": l} for l in labels]
    def test_precision_counts_only_labelled_rows_and_reports_the_blank_ones(self):
        f = P.feed_scores(self.lab("relevant", "relevant", "not_for_us", "not_real", None), 5, [], 0)["raised"]
        self.assertEqual((f["labelled"], f["unlabelled"], f["relevant"]), (4, 1, 2)); self.assertAlmostEqual(f["precision_relevant"]["value"], 0.5); self.assertAlmostEqual(f["precision_real"]["value"], 0.75)
    def test_the_recall_estimate_scales_the_sample_to_the_population(self):
        # 12 raised, all labelled, 6 relevant; 200 not raised, 40 sampled, 2 relevant -> 10 estimated misses -> recall 6 / 16
        e = P.feed_scores(self.lab(*(["relevant"] * 6 + ["not_real"] * 6)), 12, self.lab(*(["relevant"] * 2 + ["not_real"] * 38)), 200)["recall_estimate"]
        self.assertAlmostEqual(e["value"], 6 / 16); self.assertLess(e["low"], e["value"]); self.assertGreater(e["high"], e["value"]); self.assertIn("ESTIMATE", e["caveat"])
    def test_no_misses_in_the_sample_still_leaves_an_honest_range_below_one(self):
        e = P.feed_scores(self.lab("relevant", "relevant"), 2, self.lab(*(["not_real"] * 20)), 200)["recall_estimate"]
        self.assertAlmostEqual(e["value"], 1.0); self.assertLess(e["low"], 0.7)            # 20 clean samples out of 200 cannot rule out many misses
    def test_without_both_sheets_there_is_no_recall(self):
        self.assertIsNone(P.feed_scores(self.lab("relevant"), 1, [], 10)["recall_estimate"])


class Priorities(unittest.TestCase):
    def test_precision_and_recall_for_critical_and_high_only(self):
        his = ["Critical", "High", "Medium", "High", "Medium", "Medium", "Medium", "Medium", "Medium", "Low", "Low"]      # he demotes the DR gateway and promotes the voice link
        c = P.priorities_scores(rows(his))["critical_high"]
        self.assertEqual((c["precision"]["k"], c["precision"]["n"], c["recall"]["k"], c["recall"]["n"]), (2, 3, 2, 3))
        self.assertEqual(c["we_said_high_he_did_not"], ["Payment gateway (disaster recovery)"]); self.assertEqual(c["he_said_high_we_did_not"], ["Branch voice and ATM link"])
    def test_full_agreement_and_the_confusion_matrix(self):
        r = P.priorities_scores(rows(list(OURS)))
        self.assertEqual((r["critical_high"]["precision"]["value"], r["critical_high"]["recall"]["value"]), (1.0, 1.0)); self.assertEqual(r["agreement"]["exact"]["k"], 11)
        self.assertEqual(r["confusion_ours_by_his"]["Medium"]["Medium"], 6); self.assertEqual(sum(sum(v.values()) for v in r["confusion_ours_by_his"].values()), 11)
    def test_agreement_within_one_step(self):
        his = list(OURS); his[0] = "High"; his[9] = "High"          # Critical->High is one step, Low->High is two
        a = P.priorities_scores(rows(his))["agreement"]; self.assertEqual((a["exact"]["k"], a["within_one_step"]["k"]), (9, 10))
    def test_unlabelled_systems_are_left_out_and_counted(self):
        his = list(OURS); his[10] = None; his[9] = None; r = P.priorities_scores(rows(his)); self.assertEqual((r["labelled"], r["unlabelled"]), (9, 2))
    def test_his_top_ten_against_ours(self):
        ranks = [1, 3, 2, 4, 5, 6, 7, 8, 9, 10, 11]            # he swaps the two gateways
        o = P.priorities_scores(rows(list(OURS), ranks))["order"]
        self.assertEqual((o["he_ranked"], o["k"], o["top_k_overlap"]["k"], o["exact_positions"]), (11, 10, 10, 9)); self.assertGreater(o["kendall_tau_b"], 0.9); self.assertLess(o["kendall_tau_b"], 1.0)
        self.assertIsNone(P.priorities_scores(rows(list(OURS)))["order"])


class Sheets(unittest.TestCase):
    def test_the_sample_is_reproducible_and_never_larger_than_the_population(self):
        a = P.sample_ids(range(1, 101), 10, 7); self.assertEqual(a, P.sample_ids(range(100, 0, -1), 10, 7)); self.assertEqual(len(a), 10); self.assertNotEqual(a, P.sample_ids(range(1, 101), 10, 8))
        self.assertEqual(P.sample_ids([3, 1, 2], 50, 1), [1, 2, 3])
    def test_a_full_pilot_is_scored_from_planted_sheets_and_bad_labels_are_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump({"created": "2026-11-21", "as_of": "2026-11-20", "raised_population": 4, "unraised_population": 100, "seed": 1, "sample_size": 4}, open(os.path.join(d, "manifest.json"), "w"))
            P.write_csv(os.path.join(d, "feed-raised.csv"), P.FEED_COLS, [{"candidate_id": i, "title": "t%d" % i, "leo_label": l} for i, l in enumerate(["relevant", "Real but not for us", "not real", "maybe"], 1000)])
            P.write_csv(os.path.join(d, "feed-not-raised.csv"), P.UNRAISED_COLS, [{"item_id": i, "title": "u", "leo_label": l} for i, l in enumerate(["not_real", "not_real", "relevant", ""], 1)])
            P.write_csv(os.path.join(d, "priorities.csv"), P.PRIO_COLS, [{"our_rank": i + 1, "system": s, "our_rating": OURS[i], "leo_rating": OURS[i], "leo_rank": str(i + 1) if i < 3 else ""} for i, s in enumerate(SYS)])
            r = P.score(d)
            self.assertEqual(len(r["errors"]), 1); self.assertIn("maybe", r["errors"][0]); self.assertEqual(r["feed"]["raised"]["labelled"], 3); self.assertEqual(r["feed"]["not_raised"]["labelled"], 3)
            self.assertEqual(r["priorities"]["critical_high"]["precision"]["value"], 1.0); self.assertEqual(r["priorities"]["order"]["he_ranked"], 3)
            md = open(os.path.join(d, "results.md")).read(); self.assertIn("Small samples", md); self.assertIn("no target false-positive rate", md); self.assertTrue(os.path.exists(os.path.join(d, "results.json")))

if __name__ == "__main__": unittest.main()
