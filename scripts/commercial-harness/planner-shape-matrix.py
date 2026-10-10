#!/usr/bin/env python3
"""Maps which query shapes OmniGate's parallel hash join engine accepts, and why it declines the rest.

  KUBECONFIG=... OMNIGATE_API_TOKEN=... planner-shape-matrix.py [--pod 0] [--md out.md]

Runs a fixed set of realistic joins between the two TPC-H databases (LINEITEM in `lineitem`, ORDERS and
CUSTOMER in `postgres1`) on one pod and, for each, reads that pod's log for the engine decision. Needs
"Debug logging for query planning" on, because the planner only says why it declined at debug level.
Each query is run alone so the log lines after it belong to it.

Results are about the planner's decision, not about answer correctness; check answers with
verify-correctness.py. A query reported as "declined" still returns the right answer (it runs on a single
node through Calcite instead); the cost is that it can never be shared across replicas.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

LI, O, C = "lineitem.lineitem", "postgres1.orders", "postgres1.customer"
J2 = f"FROM {LI} l JOIN {O} o ON l.l_orderkey = o.o_orderkey"
J3 = f"{J2} JOIN {C} c ON o.o_custkey = c.c_custkey"

QUERIES = [
    # (group, name, sql)
    ("aggregate", "COUNT(*) GROUP BY column", f"SELECT o.o_orderpriority, COUNT(*) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "plain COUNT(*), no GROUP BY", f"SELECT COUNT(*) {J2}"),
    ("aggregate", "SUM(column)", f"SELECT o.o_orderpriority, SUM(l.l_quantity) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "AVG(column)", f"SELECT o.o_orderpriority, AVG(l.l_quantity) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "MIN and MAX(column)", f"SELECT o.o_orderpriority, MIN(l.l_quantity), MAX(l.l_quantity) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "two aggregates (COUNT + SUM)", f"SELECT o.o_orderpriority, COUNT(*), SUM(l.l_quantity) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "SUM(a * b)  [expression argument]", f"SELECT o.o_orderpriority, SUM(l.l_extendedprice * (1 - l.l_discount)) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "SUM(CASE WHEN ...)", f"SELECT o.o_orderpriority, SUM(CASE WHEN l.l_returnflag = 'R' THEN 1 ELSE 0 END) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "ROUND(SUM(column), 2)", f"SELECT o.o_orderpriority, ROUND(SUM(l.l_extendedprice), 2) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "SUM(column) / COUNT(*)  [arithmetic on aggregates]", f"SELECT o.o_orderpriority, SUM(l.l_quantity) / COUNT(*) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "COUNT(DISTINCT column)", f"SELECT o.o_orderpriority, COUNT(DISTINCT l.l_suppkey) {J2} GROUP BY o.o_orderpriority"),
    ("aggregate", "HAVING", f"SELECT o.o_orderpriority, COUNT(*) {J2} GROUP BY o.o_orderpriority HAVING COUNT(*) > 100"),
    ("grouping", "GROUP BY expression (EXTRACT year)", f"SELECT EXTRACT(YEAR FROM l.l_shipdate), COUNT(*) {J2} GROUP BY EXTRACT(YEAR FROM l.l_shipdate)"),
    ("grouping", "GROUP BY two columns", f"SELECT o.o_orderpriority, l.l_returnflag, COUNT(*) {J2} GROUP BY o.o_orderpriority, l.l_returnflag"),
    ("shape", "ORDER BY aggregate DESC LIMIT", f"SELECT o.o_orderpriority, COUNT(*) AS n {J2} GROUP BY o.o_orderpriority ORDER BY n DESC LIMIT 3"),
    ("shape", "WHERE filter on both sides", f"SELECT o.o_orderpriority, COUNT(*) {J2} WHERE l.l_quantity > 10 AND o.o_totalprice > 1000 GROUP BY o.o_orderpriority"),
    ("shape", "LEFT JOIN", f"SELECT o.o_orderpriority, COUNT(*) FROM {LI} l LEFT JOIN {O} o ON l.l_orderkey = o.o_orderkey GROUP BY o.o_orderpriority"),
    ("shape", "join, no aggregate, LIMIT", f"SELECT l.l_orderkey, o.o_orderpriority {J2} LIMIT 10"),
    ("shape", "join, projected expression, no aggregate", f"SELECT l.l_orderkey, l.l_extendedprice * (1 - l.l_discount) AS rev {J2} LIMIT 10"),
    ("shape", "three-way join, COUNT(*) GROUP BY", f"SELECT c.c_mktsegment, COUNT(*) {J3} GROUP BY c.c_mktsegment"),
    ("shape", "three-way join, SUM(column)", f"SELECT c.c_mktsegment, SUM(l.l_quantity) {J3} GROUP BY c.c_mktsegment"),
    ("shape", "three-way join, SUM(a * b)", f"SELECT c.c_mktsegment, SUM(l.l_extendedprice * (1 - l.l_discount)) {J3} GROUP BY c.c_mktsegment"),
]


def sh(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


def post(sql, token, timeout):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("http://127.0.0.1:18095/api/query", data=json.dumps({"sql": sql}).encode(), headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read())
        return time.time() - t0, body, None
    except urllib.error.HTTPError as e:
        return time.time() - t0, None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return time.time() - t0, None, str(e)[:80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pod", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--md", help="also write the table as markdown to this file")
    ap.add_argument("--token", default=os.environ.get("OMNIGATE_API_TOKEN"))
    a = ap.parse_args()
    pod = f"omnigate-omnigate-{a.pod}"
    pf = subprocess.Popen(["kubectl", "port-forward", f"pod/{pod}", "18095:8080"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    try:
        time.sleep(4)
        for group, name, sql in QUERIES:
            t_start = time.time()
            elapsed, body, err = post(sql, a.token, a.timeout)
            time.sleep(1.5)
            log = sh("kubectl", "logs", pod, f"--since={int(time.time() - t_start) + 3}s")
            used = any("executing via the parallel hash join engine" in l for l in log.splitlines())
            reasons = []
            for l in log.splitlines():
                if "parallel join planner:" in l:
                    msg = l.split("parallel join planner:", 1)[1].strip()
                    if msg not in reasons:
                        reasons.append(msg)
            ok = body is not None and body.get("success")
            nrows = len(body["rows"]) if ok else None
            verdict = "PARALLEL" if used else ("declined" if ok else "ERROR")
            reason = "" if used else ("; ".join(reasons) or (err or (str(body)[:80] if body and not ok else "no planner message")))
            rows.append((group, name, verdict, nrows, elapsed, reason))
            print(f"{verdict:9} {elapsed:5.1f}s  {name}" + (f"\n          -> {reason}" if reason else ""), flush=True)
    finally:
        pf.terminate()

    n_par = sum(1 for r in rows if r[2] == "PARALLEL")
    print(f"\n{n_par} of {len(rows)} shapes used the parallel engine on {pod}")
    if a.md:
        with open(a.md, "w") as f:
            f.write("| Query shape | Engine | Rows | Planner's reason when declined |\n|---|---|---|---|\n")
            for g, name, verdict, nrows, el, reason in rows:
                f.write(f"| {name} | {verdict} | {nrows if nrows is not None else '-'} | {reason.replace('|', '/')} |\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
