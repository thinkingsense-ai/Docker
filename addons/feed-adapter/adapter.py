"""The feed adapter: every N minutes read each configured feed, keep what the rules call a possible AI-hacking story, group items about one event into a candidate, and write it all to the rca
tables (metadata only) as the feed_writer role. It holds no user sessions and decides nothing: a person opens a candidate and a person traces it. Run `python adapter.py --once` for one pass."""
import datetime as dt, json, os, sys, time
import feedreader, rules
from store import PsqlStore

RETENTION_DAYS = 400
CLUSTER_DAYS = 14


def utc(now=None): return (now or dt.datetime.now(dt.timezone.utc)).replace(tzinfo=None, microsecond=0)


def load_sources(path):
    with open(path) as fh: cfg = json.load(fh)["sources"]
    for s in cfg:
        if s["kind"] not in ("reporting", "official", "context") or not s["url"].startswith(("http://", "https://")): raise ValueError("bad source %r" % s.get("id"))
    return cfg


def item_rows(src, items, now):
    rows = []
    for it in items:
        matched, ctype, terms = rules.classify(it["title"], it["description"], src["kind"])
        rows.append({"source_id": src["id"], "url": it["url"], "title": it["title"], "published_at": it["published"].isoformat() if it["published"] else None, "first_seen_at": now.isoformat(),
                     "seen_hash": feedreader.seen_hash(src["id"], it["url"], it["title"]), "matched": matched, "claim_type": ctype, "match_terms": terms})
    return rows                                                     # the description is dropped here: it is not stored


def run_once(sources, store, fetcher, now=None, log=print):
    now = utc(now); store.upsert_sources(sources); states = store.source_states(); summary = []
    for src in sources:
        st = states.get(src["id"]) or {}
        res = fetcher.fetch(src["url"], st.get("etag"), st.get("last_modified"))
        ok = res["status"] in ("ok", "not_modified")
        new = store.insert_items(item_rows(src, res["items"], now)) if res["status"] == "ok" else 0
        store.record_run({"id": src["id"], "at": now.isoformat(), "status": res["status"], "error": res.get("error"), "items": len(res["items"]), "success": ok, "etag": res.get("etag"), "last_modified": res.get("last_modified")})
        summary.append({"source": src["id"], "status": res["status"], "items": len(res["items"]), "new": new}); log(json.dumps(summary[-1]))
    rows = store.recent_matched((now - dt.timedelta(days=CLUSTER_DAYS)).isoformat())
    for r in rows: r["when"] = dt.datetime.fromisoformat(r["when"]) if isinstance(r["when"], str) else r["when"]
    store.apply_clusters(rules.cluster(rows))
    store.purge((now - dt.timedelta(days=RETENTION_DAYS)).isoformat())
    return summary


def main(argv):
    sources = load_sources(os.environ.get("FEED_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.json")))
    minutes = max(5, int(os.environ.get("FEED_INTERVAL_MINUTES", "30"))); store = PsqlStore(); fetcher = feedreader.Fetcher()
    while True:
        try: run_once(sources, store, fetcher)
        except Exception as e: print(json.dumps({"error": str(e)[:300]}), flush=True)          # a failed pass is logged and retried; each source's own health is already recorded
        if "--once" in argv: return
        time.sleep(minutes * 60)


if __name__ == "__main__": main(sys.argv[1:])
