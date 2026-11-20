"""One approval for the brief and the exposure rating: the facts reader, the gate rule, the digest and the action. No Temporal needed."""
import copy, json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import exposure_facts as EF, exposure_rules as X, rca_rules as R, facts as base
from test_rca import july
GOLD = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "exposure_gold.json")))["cases"]
QUESTIONS = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "demo-questions-estate.json")))

def with_exposure(answers, **kw):
    f = july(); f["exposure"] = dict({"assessed": True, "case_id": "jul-2026-breakout", "answers": copy.deepcopy(answers)}, **kw); return f

class Gate(unittest.TestCase):
    def test_a_complete_rating_lets_the_brief_publish_and_is_named_in_the_notes(self):
        g = R.gate(with_exposure(GOLD[0]["answers"]), "alice")
        self.assertEqual(g["allowed_actions"], [R.PUBLISH, R.HOLD]); self.assertEqual(g["exposure"]["level"], "Critical"); self.assertEqual(g["exposure"]["set_by"], [4, 5])
        self.assertIn("Exposure: Critical: set by questions 4 and 5.", g["notes"])
    def test_an_incomplete_rating_blocks_publishing_and_says_which_question(self):
        miss = next(c for c in GOLD if "missing answer" in c["name"])
        g = R.gate(with_exposure(miss["answers"]), "alice")
        self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(any("question 3" in b and "incomplete" in b for b in g["blocks"]))
    def test_an_unread_estate_blocks_publishing_it_is_not_a_clean_one(self):
        f = july(); f["exposure"] = {"assessed": False, "error": "the estate could not be read: boom"}
        g = R.gate(f, "alice"); self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertIn("boom", " ".join(g["blocks"]))
    def test_a_case_with_no_estate_mapping_publishes_without_a_rating(self):
        f = july(); f["exposure"] = {"assessed": False, "reason": "no technology in the estate is mapped to this case, so there is no exposure to rate"}
        g = R.gate(f, "alice"); self.assertEqual(g["allowed_actions"], [R.PUBLISH, R.HOLD]); self.assertIsNone(g["exposure"])
    def test_old_facts_without_exposure_still_work(self):
        g = R.gate(july(), "alice"); self.assertEqual(g["allowed_actions"], [R.PUBLISH, R.HOLD]); self.assertIsNone(g["exposure"])
    def test_the_rating_is_recomputed_never_trusted(self):
        f = with_exposure(GOLD[0]["answers"], rating={"level": "Low"}); self.assertEqual(R.gate(f, "alice")["exposure"]["level"], "Critical")

class Digest(unittest.TestCase):
    def test_changing_an_answer_or_the_rating_changes_the_digest(self):
        a = R.brief_digest(with_exposure(GOLD[0]["answers"])); b = R.brief_digest(with_exposure(GOLD[1]["answers"]))
        self.assertNotEqual(a, b)
        c = copy.deepcopy(GOLD[0]["answers"]); c["recovery"]["rows"][0][-1] = "1"
        self.assertNotEqual(a, R.brief_digest(with_exposure(c)))
    def test_the_same_answers_give_the_same_digest(self):
        self.assertEqual(R.brief_digest(with_exposure(GOLD[0]["answers"])), R.brief_digest(with_exposure(GOLD[0]["answers"])))
    def test_a_brief_without_exposure_has_no_exposure_key_in_its_body(self):
        self.assertEqual(R.brief_digest(july()), R.brief_digest(dict(july(), exposure=None)))

class Reader(unittest.TestCase):
    def setUp(self): self.q = base.query_table; self.env = dict(os.environ)
    def tearDown(self): base.query_table = self.q; os.environ.clear(); os.environ.update(self.env)
    def test_the_sql_is_the_approved_questions_sql(self):
        for k, q in zip(EF.KEYS, QUESTIONS):
            self.assertEqual(EF.SQL[k].format(p="pg.", case="nov-2026-cluster"), q["referenceSql"].strip(), k)
    def test_it_keeps_the_columns_of_an_empty_answer(self):
        def fake(sql, ws=None):
            return (["n"], [[3]]) if "COUNT(*)" in sql else (["system", "tier"], [])
        base.query_table = fake
        e = EF.gather("nov-2026-cluster"); self.assertTrue(e["assessed"]); self.assertEqual(e["answers"]["systems"], {"columns": ["system", "tier"], "rows": []})
    def test_no_mapping_means_not_assessed(self):
        base.query_table = lambda sql, ws=None: (["n"], [[0]])
        e = EF.gather("jul-2026-breakout"); self.assertFalse(e["assessed"]); self.assertIn("no technology", e["reason"])
    def test_a_failed_read_is_an_error_not_a_clean_estate(self):
        def boom(sql, ws=None): raise RuntimeError("schema estate not found")
        base.query_table = boom
        e = EF.gather("nov-2026-cluster"); self.assertFalse(e["assessed"]); self.assertIn("not found", e["error"])
    def test_it_can_be_switched_off_and_refuses_a_odd_case_id(self):
        os.environ["EXPOSURE_ENABLED"] = "off"; self.assertFalse(EF.gather("x")["assessed"])
        os.environ["EXPOSURE_ENABLED"] = "on"
        with self.assertRaises(RuntimeError): EF.gather("x'; DROP")
    def test_the_prefix_is_applied(self):
        seen = []; os.environ["EXPOSURE_TABLE_PREFIX"] = "pg."
        def fake(sql, ws=None): seen.append(sql); return (["n"], [[0]])
        base.query_table = fake; EF.gather("nov-2026-cluster"); self.assertIn("pg.estate.scenario_technology", seen[0])

if __name__ == "__main__": unittest.main()
