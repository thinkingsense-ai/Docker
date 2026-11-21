"""Feed adapter: parsing, politeness, the rule-based filter, clustering and one full pass against a fake store. No network, no database."""
import datetime as dt, json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import adapter, feedreader as F, rules as R

NOW = dt.datetime(2026, 11, 20, 12, 0, 0)
RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>t</title>
<item><title>AI-powered attack takes down Microsoft 365 in a major outage</title><link>https://Example.com/a/?utm_source=x&amp;id=7#frag</link><pubDate>Fri, 20 Nov 2026 09:00:00 GMT</pubDate>
<description>&lt;p&gt;Some &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>A recipe for soup</title><guid>https://example.com/soup</guid><pubDate>Mon, 01 Jan 2029 00:00:00 GMT</pubDate></item>
<item><link>https://example.com/no-title</link></item></channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>FAA ground stop: AI hackers blamed</title><link rel="alternate" href="https://news.example/faa"/><link rel="self" href="https://x/self"/><updated>2026-11-19T10:00:00Z</updated><summary>s</summary></entry></feed>"""
RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Old style feed</title><link>https://example.org/o</link><dc:date>2026-11-18T08:00:00Z</dc:date></item></rdf:RDF>"""

class Parse(unittest.TestCase):
    def test_rss_title_link_date_and_a_cleaned_description(self):
        a, b = F.parse(RSS, NOW)[:2]
        self.assertEqual(a["url"], "https://example.com/a?id=7")                                    # host lower-cased, tracking and fragment gone, slash gone
        self.assertEqual(a["published"], dt.datetime(2026, 11, 20, 9)); self.assertEqual(a["description"], "Some text")
        self.assertEqual(b["url"], "https://example.com/soup"); self.assertIsNone(b["published"])    # a date in 2029 is wrong, so unknown
        self.assertEqual(len(F.parse(RSS, NOW)), 2)                                                  # an item with no title is skipped
    def test_atom_uses_the_alternate_link(self): self.assertEqual(F.parse(ATOM, NOW)[0]["url"], "https://news.example/faa")
    def test_rdf(self): self.assertEqual(F.parse(RDF, NOW)[0]["published"], dt.datetime(2026, 11, 18, 8))
    def test_a_document_type_or_entities_are_refused(self):
        for bad in (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>', b'<rss><!ENTITY a "b"></rss>'):
            with self.assertRaises(ValueError): F.parse(bad)
    def test_not_a_feed_or_not_xml(self):
        for bad in (b"<html><body/></html>", b"nope"):
            with self.assertRaises(ValueError): F.parse(bad)
    def test_the_same_article_from_two_feeds_is_one_hash(self):
        self.assertEqual(F.seen_hash("a", "https://x.com/p", "T"), F.seen_hash("b", "https://x.com/p", "Other"))
        self.assertNotEqual(F.seen_hash("a", "", "One story"), F.seen_hash("b", "", "One story"))      # without an address the source is part of the key

class Fake(F.Fetcher):
    """A fetcher whose network is a dict: url -> (status, headers, body)."""
    def __init__(self, web): super().__init__(sleep=lambda s: None); self.web = web; self.calls = []
    def get(self, url, headers=None):
        self.calls.append((url, dict(headers or {}))); r = self.web[url]
        if isinstance(r, Exception): raise r
        return r

class Polite(unittest.TestCase):
    def web(self, **kw): return dict({"https://h.example/robots.txt": (404, {}, b""), "https://h.example/feed": (200, {"etag": "e1"}, RSS)}, **kw)
    def test_no_robots_file_means_no_rules_and_the_feed_is_read(self):
        r = Fake(self.web()).fetch("https://h.example/feed"); self.assertEqual(r["status"], "ok"); self.assertEqual(r["etag"], "e1")
    def test_a_disallowing_robots_file_blocks_the_fetch_and_the_feed_is_never_requested(self):
        f = Fake(self.web(**{"https://h.example/robots.txt": (200, {}, b"User-agent: *\nDisallow: /feed")}))
        self.assertEqual(f.fetch("https://h.example/feed")["status"], "blocked_by_robots"); self.assertNotIn("https://h.example/feed", [c[0] for c in f.calls])
    def test_our_own_agent_name_is_honoured(self):
        f = Fake(self.web(**{"https://h.example/robots.txt": (200, {}, b"User-agent: ThinkingSenseFeedReader\nDisallow: /")}))
        self.assertEqual(f.fetch("https://h.example/feed")["status"], "blocked_by_robots")
    def test_an_unreadable_robots_file_means_do_not_fetch(self):
        for w in ((503, {}, b""), OSError("down")):
            self.assertEqual(Fake(self.web(**{"https://h.example/robots.txt": w})).fetch("https://h.example/feed")["status"], "unreachable")
    def test_the_request_is_conditional_and_a_304_is_not_modified(self):
        f = Fake(self.web(**{"https://h.example/feed": (304, {}, b"")})); r = f.fetch("https://h.example/feed", "e1", "Mon")
        self.assertEqual(r["status"], "not_modified"); h = f.calls[-1][1]; self.assertEqual((h["If-None-Match"], h["If-Modified-Since"]), ("e1", "Mon"))
    def test_http_errors_and_bad_xml_are_reported_not_raised(self):
        self.assertEqual(Fake(self.web(**{"https://h.example/feed": (500, {}, b"")})).fetch("https://h.example/feed")["error"], "HTTP 500")
        self.assertEqual(Fake(self.web(**{"https://h.example/feed": (200, {}, b"<html/>")})).fetch("https://h.example/feed")["status"], "parse_error")
    def test_a_host_is_not_hit_twice_without_a_pause(self):
        waits = []; f = Fake(self.web()); f.sleep = waits.append; f.fetch("https://h.example/feed"); f.fetch("https://h.example/feed"); self.assertTrue(waits and waits[-1] > 0)

class Filter(unittest.TestCase):
    def c(self, t, kind="reporting", d=""): return R.classify(t, d, kind)
    def test_a_claim_needs_ai_an_attack_and_an_incident(self): self.assertEqual(self.c("AI-powered attack takes down a hospital network in a major outage")[:2], (True, R.CLAIMED))
    def test_an_official_source_saying_it_is_confirmed_not_claimed(self): self.assertEqual(self.c("CISA warns AI-driven ransomware attack disrupts hospitals", "official")[:2], (True, R.CONFIRMED))
    def test_a_general_trend_piece_is_not_a_candidate(self): self.assertFalse(self.c("AI-powered attacks are rising, a report says")[0])
    def test_ai_with_an_outage_or_a_weakness_but_no_attack_is_adjacent(self):
        self.assertEqual(self.c("Microsoft patch fixes bug that caused an outage, AI helped find it")[1], R.ADJACENT); self.assertEqual(self.c("AI finds a zero-day vulnerability in a router")[1], R.ADJACENT)
    def test_no_ai_no_candidate(self): self.assertFalse(self.c("Ransomware attack causes outage at a hospital")[0])
    def test_ai_must_be_a_word_not_a_fragment(self):
        for t in ("Said the maid in Spain", "An ai outage attack", "Trained a model on the AIR data breach"): self.assertFalse(self.c(t)[0], t)
    def test_roundups_and_promotions_are_not_one_incident(self):
        for x in ("This month in security with Tony Anscombe, September edition", "In Other News: AI hack, outage and breach", "Industry Reactions to Major Outages and AI Patching Debate: Feedback Friday"):
            self.assertFalse(self.c(x + " attack outage AI")[0], x)
    def test_context_feeds_never_create_a_candidate(self): self.assertFalse(self.c("AI-powered attack takes down a network in a major outage", "context")[0])
    def test_the_description_is_read_to_match_but_the_title_alone_can_miss(self):
        self.assertFalse(self.c("A bad day for a bank")[0]); self.assertTrue(self.c("A bad day for a bank", d="Hackers using AI caused an outage at the bank.")[0])

def row(i, title, hours, ctype=R.CLAIMED, cid=None, src="A"): return {"item_id": i, "title": title, "when": NOW + dt.timedelta(hours=hours), "claim_type": ctype, "candidate_id": cid, "source": src}

class Cluster(unittest.TestCase):
    def test_two_headlines_naming_the_same_company_within_two_days_are_one_candidate(self):
        g = R.cluster([row(1, "Microsoft 365 down: AI attack suspected", 0), row(2, "Microsoft says outage not an attack", 20, R.ADJACENT, src="B")])
        self.assertEqual(len(g), 1); self.assertEqual(g[0]["item_ids"], [1, 2]); self.assertEqual(g[0]["claim_type"], R.CLAIMED); self.assertEqual(g[0]["summary"], "2 headlines from A, B.")
    def test_unrelated_stories_stay_apart(self): self.assertEqual(len(R.cluster([row(1, "Microsoft outage blamed on AI", 0), row(2, "Chase breach blamed on AI", 1)])), 2)
    def test_one_shared_name_a_week_apart_is_not_enough_two_are(self):
        self.assertEqual(len(R.cluster([row(1, "Chase outage", 0), row(2, "Chase hit again", 5 * 24)])), 2)
        self.assertEqual(len(R.cluster([row(1, "Chase Visa outage", 0), row(2, "Chase Visa hit again", 5 * 24)])), 1)
    def test_an_item_keeps_its_candidate_and_two_candidates_are_never_merged(self):
        g = R.cluster([row(1, "Chase outage", 0, cid=1000), row(2, "Chase outage again", 5, cid=1001), row(3, "Chase outage update", 6)])
        self.assertEqual(sorted(x["candidate_id"] for x in g if x["candidate_id"]), [1000, 1001])
    def test_a_new_item_joins_an_existing_candidate(self):
        g = R.cluster([row(1, "FAA ground stop blamed on AI", 0, cid=1000), row(2, "FAA says contractor upgrade caused it", 10, R.ADJACENT)])
        self.assertEqual(len(g), 1); self.assertEqual(g[0]["candidate_id"], 1000); self.assertEqual(g[0]["item_ids"], [1, 2])
    def test_the_candidate_takes_the_strongest_claim_type_and_the_earliest_headline(self):
        g = R.cluster([row(2, "FAA update", 5, R.ADJACENT), row(1, "FAA ground stop: AI hackers", 0, R.CLAIMED)])[0]
        self.assertEqual((g["claim_type"], g["title"]), (R.CLAIMED, "FAA ground stop: AI hackers")); self.assertEqual(g["lead_item_id"], 1)     # the lead is the earliest headline, the one whose title the candidate carries

class FakeStore:
    def __init__(self): self.sources = []; self.items = []; self.runs = {}; self.groups = None; self.purged = None; self.states = {}
    def upsert_sources(self, s): self.sources = s
    def source_states(self): return self.states
    def record_run(self, r): self.runs[r["id"]] = r
    def insert_items(self, rows):
        new = [r for r in rows if r["seen_hash"] not in {i["seen_hash"] for i in self.items}]; self.items += new; return len(new)
    def recent_matched(self, since):
        return [{"item_id": n, "title": i["title"], "when": i["published_at"] or i["first_seen_at"], "claim_type": i["claim_type"], "source": i["source_id"], "candidate_id": None} for n, i in enumerate(self.items, 1) if i["matched"]]
    def apply_clusters(self, g): self.groups = g
    def purge(self, before): self.purged = before

class Pass(unittest.TestCase):
    SRC = [{"id": "sw", "name": "SW", "kind": "reporting", "url": "https://h.example/feed"}, {"id": "ctx", "name": "Ctx", "kind": "context", "url": "https://c.example/feed"}, {"id": "dead", "name": "Dead", "kind": "official", "url": "https://d.example/feed"}]
    def web(self): return {"https://h.example/robots.txt": (404, {}, b""), "https://h.example/feed": (200, {}, RSS), "https://c.example/robots.txt": (404, {}, b""), "https://c.example/feed": (200, {}, RSS),
                           "https://d.example/robots.txt": OSError("no route")}
    def test_a_pass_records_each_sources_health_stores_metadata_only_and_clusters(self):
        st = FakeStore(); out = adapter.run_once(self.SRC, st, Fake(self.web()), NOW, log=lambda s: None)
        self.assertEqual({s["source"]: s["status"] for s in out}, {"sw": "ok", "ctx": "ok", "dead": "unreachable"})
        self.assertTrue(st.runs["sw"]["success"]); self.assertFalse(st.runs["dead"]["success"]); self.assertEqual(st.runs["dead"]["items"], 0)
        self.assertEqual(len(st.items), 2)                                                          # the shared article is one item: the second feed's copy is a duplicate
        self.assertTrue(all(set(r) == {"source_id", "url", "title", "published_at", "first_seen_at", "seen_hash", "matched", "claim_type", "match_terms"} for r in st.items))   # no description column
        self.assertEqual(len(st.groups), 1); self.assertEqual(st.groups[0]["claim_type"], R.CLAIMED); self.assertEqual(st.purged, (NOW - dt.timedelta(days=400)).isoformat())
    def test_a_second_pass_adds_nothing_new(self):
        st = FakeStore(); f = Fake(self.web()); adapter.run_once(self.SRC, st, f, NOW, log=lambda s: None); n = len(st.items)
        out = adapter.run_once(self.SRC, st, f, NOW, log=lambda s: None); self.assertEqual(len(st.items), n); self.assertEqual(sum(s["new"] for s in out), 0)
    def test_the_stored_etag_goes_back_as_a_conditional_request(self):
        st = FakeStore(); st.states = {"sw": {"etag": "e9", "last_modified": None}}; f = Fake(self.web()); adapter.run_once(self.SRC[:1], st, f, NOW, log=lambda s: None)
        self.assertEqual([c[1] for c in f.calls if c[0].endswith("/feed")][0].get("If-None-Match"), "e9")
    def test_the_shipped_feed_list_is_valid_and_has_the_three_kinds(self):
        s = adapter.load_sources(os.path.join(os.path.dirname(__file__), "..", "feeds.json")); self.assertEqual({x["kind"] for x in s}, {"reporting", "official", "context"}); self.assertEqual(len({x["id"] for x in s}), len(s))

if __name__ == "__main__": unittest.main()
