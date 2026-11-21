"""python3 -m unittest agency/local/test_refresh_questions.py (from the repo root). The comparison that finds approved questions whose SQL changed after they were seeded."""
import importlib.util, os, unittest
spec = importlib.util.spec_from_file_location("rq", os.path.join(os.path.dirname(os.path.abspath(__file__)), "refresh-questions.py")); rq = importlib.util.module_from_spec(spec); spec.loader.exec_module(rq)

class Stale(unittest.TestCase):
    def test_a_changed_sql_is_stale_an_unchanged_one_is_not_and_whitespace_does_not_count(self):
        bank = [{"id": "1", "question": "A", "referenceSql": "SELECT s.tier FROM t s"}, {"id": "2", "question": "B", "referenceSql": "SELECT 1 "}, {"id": "3", "question": "C", "referenceSql": "SELECT 9"}]
        wanted = {"A": "SELECT s.business_criticality AS tier FROM t s", "B": "SELECT 1", "C": "SELECT 9"}
        self.assertEqual([e["id"] for e in rq.stale(bank, wanted)], ["1"])
    def test_a_bank_entry_that_is_not_in_the_files_is_left_alone(self):
        self.assertEqual(rq.stale([{"id": "9", "question": "someone else's", "referenceSql": "SELECT 1"}], {"A": "SELECT 2"}), [])
    def test_a_missing_reference_sql_in_the_bank_counts_as_stale(self):
        self.assertEqual(len(rq.stale([{"id": "1", "question": "A"}], {"A": "SELECT 1"})), 1)

if __name__ == "__main__": unittest.main()
