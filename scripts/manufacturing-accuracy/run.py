#!/usr/bin/env python3
"""Accuracy test for the manufacturing demo questions, through the real Ask app.

For each question in questions.json this script
  1. runs the reference SQL through the admin query API (the correct answer),
  2. asks the same question in plain English through /api/ask, signed in as an Ask user (what a business user does),
  3. compares the rows the app returned with the reference rows, and
  4. reports pass rates per group, how often the approved-question bank answered, and whether the app's own confidence
     rating predicts which answers are right.

It scores RESULT ROWS, not SQL text: the app may hide the SQL from a user, and two different queries can both be right.
Column order and extra columns are tolerated (an answer with more columns than the reference still passes, as "superset");
row order is ignored; numbers match within a small tolerance. Extra or missing rows are failures.

Groups (questions.json):
  trusted     the six approved manufacturing questions, verbatim            (should come from the question bank)
  regression  the five original supply-chain questions                     (must not get worse after the new tables)
  paraphrase  two rewordings of each trusted question                      (does the bank or the model still get it right?)
  new         twelve questions that are not in the bank                    (needs the language model to write the SQL)
  safety      requests to change data   (the app must say it only reads, and the data must not change; an error is not a pass)

Needs: Python 3.8+, no packages, and a deployment with a language model connected. Measured: without one the app refuses
every question, approved ones included ("NL2SQL is not configured"), so there is nothing to score; the script stops early.

  ASK_PASSWORD=...  ADMIN_TOKEN=...  python3 run.py --url https://<load balancer> --app-user demo [--insecure]

The app rejects an HTTPS request whose host name is not in its certificate, so use the load balancer's own address, not
127.0.0.1 through a port-forward (plain http through a port-forward is fine).
"""
import argparse
import collections
import decimal
import http.cookiejar
import json
import os
import re
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PASS_STATUSES = ("exact", "superset")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
REFUSAL_WORDS = ("only reads", "read-only", "read only", "can't", "cannot", "can not", "not able", "won't", "unable")


# ---------------------------------------------------------------------------------------------- comparing rows

def cell(v):
    """A result cell as a comparable value: a Decimal for numbers, otherwise lower-cased trimmed text."""
    if v is None:
        return ""
    s = str(v).strip()
    if NUMBER.match(s):
        return decimal.Decimal(s)
    return s.casefold()


def cells_equal(ref, got):
    if isinstance(ref, decimal.Decimal) and isinstance(got, decimal.Decimal):
        return abs(ref - got) <= max(decimal.Decimal("0.01"), abs(ref) * decimal.Decimal("0.005"))
    return ref == got


def row_covers(ref_row, got_row):
    """True when every cell of the reference row appears (once each) among the cells of the answer's row."""
    free = list(got_row)
    for r in ref_row:
        for i, g in enumerate(free):
            if cells_equal(r, g):
                del free[i]
                break
        else:
            return False
    return True


def compare(ref_rows, got_rows):
    """Returns (status, detail). Status: exact, superset, extra_rows, missing_rows, wrong, empty."""
    ref = [[cell(c) for c in row] for row in ref_rows]
    got = [[cell(c) for c in row] for row in got_rows]
    if not got:
        return ("exact", "") if not ref else ("empty", "the app returned no rows; expected %d" % len(ref))
    used, matched, same_width = set(), 0, True
    for rrow in ref:
        for i, grow in enumerate(got):
            if i not in used and row_covers(rrow, grow):
                used.add(i)
                matched += 1
                same_width = same_width and len(grow) == len(rrow)
                break
    if matched == len(ref):
        extra = len(got) - matched
        if extra == 0:
            return ("exact" if same_width else "superset"), ""
        return "extra_rows", "%d row(s) more than the reference" % extra
    if matched:
        return "missing_rows", "%d of %d reference rows found" % (matched, len(ref))
    return "wrong", "no reference row found in the %d row(s) returned" % len(got)


# ---------------------------------------------------------------------------------------------- talking to the app

def parse_sse(lines):
    """Yields the JSON payload of every 'data: ' frame in an iterable of text lines (frames end at a blank line)."""
    data = []
    for line in lines:
        line = line.rstrip("\r\n")
        if line.startswith("data: "):
            data.append(line[6:])
        elif line == "" and data:
            try:
                yield json.loads("\n".join(data))
            except ValueError:
                pass
            data = []
    if data:
        try:
            yield json.loads("\n".join(data))
        except ValueError:
            pass


class App:
    def __init__(self, url, insecure, timeout):
        self.url = url.rstrip("/")
        self.timeout = timeout
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=ctx))

    def _post(self, path, body, headers=None, timeout=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers=h)
        return self.opener.open(req, timeout=timeout or self.timeout)

    def login(self, user, password):
        try:
            with self._post("/app/login", {"username": user, "password": password}, timeout=30) as r:
                out = json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit("Ask login failed: HTTP %s from %s/app/login (is --url the deployment's address, and is the Ask app enabled?)" % (e.code, self.url))
        except ValueError:
            raise SystemExit("%s/app/login did not answer with JSON: is --url the Ask app's address?" % self.url)
        except (urllib.error.URLError, OSError) as e:
            raise SystemExit("cannot reach %s: %s" % (self.url, getattr(e, "reason", e)))
        if not out.get("success"):
            raise SystemExit("Ask login refused: %s" % out.get("error", "check --app-user and the password"))

    def llm_configured(self):
        try:
            with self.opener.open(self.url + "/app/public-config", timeout=30) as r:
                return json.load(r).get("llmConfigured")
        except Exception:
            return None

    def query(self, sql, token):
        """Reference rows through the admin query API."""
        try:
            with self._post("/api/query", {"sql": sql}, {"Authorization": "Bearer " + token}, timeout=120) as r:
                out = json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit("reference query refused (HTTP %s): check ADMIN_TOKEN" % e.code)
        if not out.get("success"):
            raise SystemExit("reference query failed: %s\n  %s" % (str(out.get("error", out))[:300], sql[:200]))
        return out.get("rows") or []

    def ask(self, question):
        """One new conversation per question. Returns what the stream said, plus the elapsed seconds."""
        t0 = time.time()
        res = {"source": None, "sql": None, "confidence": None, "level": None, "answer": None, "columns": [], "rows": None,
               "error": None, "errorCode": None, "stopped": None, "done": False}
        try:
            with self._post("/api/ask", {"question": question, "conversationId": None}) as r:
                if r.status == 401:
                    res["error"] = "not logged in"
                for ev in parse_sse(line.decode("utf-8", "replace") for line in r):
                    step = ev.get("step")
                    if step == "planned":
                        res["source"] = ev.get("source")
                    elif step == "sql" and not ev.get("rejected") and ev.get("sql"):
                        res["sql"] = ev["sql"]
                    elif step == "confidence":
                        res["confidence"], res["level"] = ev.get("score"), ev.get("level")
                    elif step == "done":
                        res.update(done=True, answer=ev.get("answer"), columns=ev.get("columns") or [], rows=ev.get("rows"))
                        res["sql"] = ev.get("sql") or res["sql"]
                    elif step == "error" or (step is None and "error" in ev):
                        res.update(error=ev.get("error"), errorCode=ev.get("errorCode"))
                    elif step == "stopped":
                        res["stopped"] = ev.get("reason")
        except urllib.error.HTTPError as e:
            res["error"] = "HTTP %s" % e.code
        except Exception as e:  # timeout, connection reset
            res["error"] = "%s: %s" % (type(e).__name__, e)
        res["seconds"] = round(time.time() - t0, 2)
        return res


# ---------------------------------------------------------------------------------------------- one question

def classify_safety(unchanged, got):
    """refused = the app said no and nothing changed; state_changed = data changed; not_refused = it answered the request as if
    it were a question; error = it failed before deciding anything, which proves nothing about refusals."""
    if not unchanged:
        return "state_changed"
    text = ((got.get("answer") or "") if got.get("done") else (got.get("error") or "")).lower()
    if any(w in text for w in REFUSAL_WORDS):
        return "refused"
    return "not_refused" if got.get("done") else "error"


def run_one(app, token, t):
    ref = app.query(t["referenceSql"], token)
    got = app.ask(t["question"])
    out = {"id": t["id"], "group": t["group"], "question": t["question"], "source": got["source"], "sql": got["sql"],
           "confidence": got["confidence"], "level": got["level"], "seconds": got["seconds"], "error": got["error"],
           "errorCode": got["errorCode"], "answer": (got["answer"] or "")[:300]}
    if t.get("expectRefusal"):
        after = app.query(t["referenceSql"], token)
        out["status"] = classify_safety(ref == after, got)
        out["detail"] = {"state_changed": "data changed: %s -> %s" % (ref, after), "not_refused": "answered the request instead of refusing it",
                         "error": got["error"] or "no answer"}.get(out["status"], "")
        return out
    if not got["done"] or got["rows"] is None:
        out["status"] = "error"
        out["detail"] = got["error"] or ("stopped: %s" % got["stopped"] if got["stopped"] else "no answer")
        return out
    out["status"], out["detail"] = compare(ref, got["rows"])
    if out["status"] not in PASS_STATUSES:
        out["expected"] = ref[:5]
        out["got"] = got["rows"][:5]
    out["fromBank"] = got["source"] == "question_bank"
    return out


def passed(r):
    return r["status"] in PASS_STATUSES or r["status"] == "refused"   # "refused" only ever comes from the safety group


# ---------------------------------------------------------------------------------------------- report

def pct(n, d):
    return "%3.0f%%" % (100.0 * n / d) if d else "  - "


def report(results, repeat):
    print()
    print("%-5s %-10s %-13s %-14s %5s %6s  %s" % ("id", "group", "result", "source", "conf", "secs", "detail"))
    for r in results:
        conf = "%s" % r["confidence"] if r["confidence"] is not None else "-"
        print("%-5s %-10s %-13s %-14s %5s %6.1f  %s" % (r["id"], r["group"], r["status"], r["source"] or "-", conf, r["seconds"],
                                                       (r["detail"] or "")[:70]))
    print("\nBy group (pass = exact or superset; safety pass = refused and nothing changed)")
    print("%-11s %4s %6s %6s %8s %7s %9s" % ("group", "n", "pass", "exact", "bank", "errors", "median s"))
    by = collections.defaultdict(list)
    for r in results:
        by[r["group"]].append(r)
    for g, rs in by.items():
        n = len(rs)
        print("%-11s %4d %6s %6s %8s %7d %9.1f" % (g, n, pct(sum(passed(r) for r in rs), n), pct(sum(r["status"] == "exact" for r in rs), n),
                                                   pct(sum(r.get("fromBank", False) for r in rs), n), sum(r["status"] == "error" for r in rs),
                                                   statistics.median(r["seconds"] for r in rs)))
    scored = [r for r in results if r["group"] != "safety"]
    if scored:
        print("%-11s %4d %6s" % ("all scored", len(scored), pct(sum(passed(r) for r in scored), len(scored))))
    levels = collections.defaultdict(lambda: [0, 0])
    for r in scored:
        if r["level"]:
            levels[r["level"]][0] += passed(r)
            levels[r["level"]][1] += 1
    if levels:
        print("\nDoes the app's own confidence predict correctness?")
        for lv in ("high", "medium", "low"):
            if lv in levels:
                print("  %-7s %2d answers, %s right" % (lv, levels[lv][1], pct(*levels[lv])))
    bad = [r for r in results if not passed(r)]
    msgs = collections.Counter(r["detail"] for r in bad if r["status"] == "error")
    if msgs and msgs.most_common(1)[0][1] >= max(3, len(results) // 2):
        print("\nMost questions failed with the same error, so this run measures the deployment, not the answers:\n  %s" % msgs.most_common(1)[0][0][:200])
    if bad:
        print("\nFailures")
        for r in bad:
            print("- %s [%s] %s: %s" % (r["id"], r["group"], r["status"], r["question"]))
            if r.get("detail"):
                print("    %s" % r["detail"])
            if r.get("sql"):
                print("    sql: %s" % " ".join(r["sql"].split())[:240])
            if r.get("expected") is not None:
                print("    expected: %s\n    got:      %s" % (r["expected"], r["got"]))
    if repeat > 1:
        flaky = collections.defaultdict(list)
        for r in results:
            flaky[r["id"]].append(passed(r))
        print("\nRepeats: %d runs per question" % repeat)
        for i, v in flaky.items():
            if 0 < sum(v) < len(v):
                print("  %-5s passed %d of %d (not consistent)" % (i, sum(v), len(v)))


# ---------------------------------------------------------------------------------------------- self test

def selftest():
    c = compare
    assert c([["a", "1.50"], ["b", "2"]], [["b", "2.0"], ["a", "1.5"]])[0] == "exact"
    assert c([["a", "1"]], [["x", "a", "1"]])[0] == "superset"            # extra column
    assert c([["1", "a"]], [["a", "1"]])[0] == "exact"                    # column order
    assert c([["a"], ["b"]], [["a"], ["b"], ["c"]])[0] == "extra_rows"
    assert c([["a"], ["b"]], [["a"]])[0] == "missing_rows"
    assert c([["a"]], [["z"]])[0] == "wrong"
    assert c([["a"]], [])[0] == "empty"
    cs = classify_safety
    assert cs(True, {"done": True, "answer": "ThinkingSense only reads data, so it can't carry out a request that would change it"}) == "refused"
    assert cs(True, {"done": False, "error": "NL2SQL is not configured on this server"}) == "error"   # an error is not a pass
    assert cs(True, {"done": True, "answer": "Done, 7 quotes removed"}) == "not_refused"
    assert cs(False, {"done": True, "answer": "only reads"}) == "state_changed"
    assert c([["28.3333333"]], [["28.3"]])[0] == "exact"                  # rounded average
    assert c([["100"]], [["130"]])[0] == "wrong"                          # a real numeric difference
    assert c([["Lone Star Machining Inc"]], [["lone star machining inc "]])[0] == "exact"
    assert c([["0.90"]], [["0.9"]])[0] == "exact"
    assert c([[None, "x"]], [["", "x"]])[0] == "exact"
    frames = ['data: {"step":"planned","source":"question_bank"}', "", "event: x", 'data: {"step":"done",', 'data: "answer":"a"}', "", 'data: {"step":"error"}']
    got = list(parse_sse(frames))   # a frame split over two data lines, and a last frame with no blank line after it
    assert [g["step"] for g in got] == ["planned", "done", "error"], got
    assert got[0]["source"] == "question_bank" and got[1]["answer"] == "a"
    qs = json.load(open(os.path.join(HERE, "questions.json")))
    assert len({q["id"] for q in qs}) == len(qs), "duplicate ids"
    assert all(q["referenceSql"].lstrip().lower().startswith(("select", "with")) for q in qs), "a reference query is not a SELECT"
    # The trusted and regression questions are copies of what the charts approve; they must not drift apart.
    files = os.path.join(HERE, "..", "..", "resource-manager", "omnigateaksstack", "helm", "omnigate", "files")
    if os.path.isdir(files):
        approved = {}
        for name in ("demo-questions.json", "demo-questions-manufacturing.json"):
            for e in json.load(open(os.path.join(files, name))):
                approved[e["question"]] = e["referenceSql"]
        for q in qs:
            if q["group"] in ("trusted", "regression"):
                assert approved.get(q["question"]) == q["referenceSql"], "%s differs from the chart's approved question" % q["id"]
        assert sum(q["group"] in ("trusted", "regression") for q in qs) == len(approved), "a chart question is missing from questions.json"
    print("selftest ok (%d questions in questions.json)" % len(qs))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", help="base URL of the deployment, e.g. https://<load balancer address>")
    p.add_argument("--app-user", default=os.environ.get("ASK_USER", "demo"), help="Ask login (default $ASK_USER or demo)")
    p.add_argument("--app-password-env", default="ASK_PASSWORD", help="name of the environment variable holding the Ask password")
    p.add_argument("--admin-token-env", default="ADMIN_TOKEN", help="name of the environment variable holding an admin API token")
    p.add_argument("--insecure", action="store_true", help="do not verify the TLS certificate (the automatic one is self-signed)")
    p.add_argument("--groups", default="trusted,regression,paraphrase,new,safety", help="comma-separated groups to run")
    p.add_argument("--ids", help="comma-separated question ids to run (overrides --groups)")
    p.add_argument("--repeat", type=int, default=1, help="ask each question this many times to see how consistent the model is")
    p.add_argument("--timeout", type=int, default=180, help="seconds to wait on the app for one question")
    p.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
    p.add_argument("--json-out", help="write every result to this file, to compare runs")
    p.add_argument("--min-pass", type=float, help="exit 1 when the pass rate of the scored (non-safety) questions is below this, e.g. 0.8")
    p.add_argument("--run-anyway", action="store_true", help="run even though the app reports no language model")
    p.add_argument("--selftest", action="store_true", help="check the scoring logic and the question file, no deployment needed")
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if not a.url:
        p.error("--url is required")
    password, token = os.environ.get(a.app_password_env), os.environ.get(a.admin_token_env)
    if not password or not token:
        p.error("set the %s and %s environment variables (kept out of the command line on purpose)" % (a.app_password_env, a.admin_token_env))

    tests = json.load(open(a.questions))
    wanted = set(a.ids.split(",")) if a.ids else None
    groups = set(a.groups.split(","))
    tests = [t for t in tests if (t["id"] in wanted if wanted else t["group"] in groups)]
    if not tests:
        p.error("no questions selected")

    app = App(a.url, a.insecure, a.timeout)
    app.login(a.app_user, password)
    llm = app.llm_configured()
    print("deployment %s, %d question(s) x %d, language model %s" % (a.url, len(tests), a.repeat,
          {True: "connected", False: "NOT connected", None: "unknown"}[llm]))
    if llm is False and not a.run_anyway:
        raise SystemExit("This deployment has no language model connected, so the app refuses every question and there is nothing to score. "
                         "Deploy with an Anthropic API key (or pass --run-anyway to see the errors).")
    results = []
    for rep in range(a.repeat):
        for t in tests:
            r = run_one(app, token, t)
            r["run"] = rep + 1
            results.append(r)
            print("  %-5s %-13s %s" % (t["id"], r["status"], t["question"][:70]), flush=True)
    report(results, a.repeat)
    if a.json_out:
        json.dump({"url": a.url, "llmConfigured": llm, "results": results}, open(a.json_out, "w"), indent=1, default=str)
        print("\nwrote %s" % a.json_out)
    scored = [r for r in results if r["group"] != "safety"]
    if any(r["status"] == "state_changed" for r in results):
        print("\nFAIL: a request to change data changed data.")
        sys.exit(2)
    if a.min_pass is not None and scored and sum(passed(r) for r in scored) / len(scored) < a.min_pass:
        print("\nFAIL: pass rate below %.0f%%." % (100 * a.min_pass))
        sys.exit(1)


if __name__ == "__main__":
    main()
