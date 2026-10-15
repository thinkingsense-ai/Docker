#!/usr/bin/env python3
"""Checks that a deployed OmniGate returns CORRECT answers, by comparing against ground truth that
does not come from OmniGate itself.

  verify-correctness.py --url http://<load-balancer-ip>:8080 [--tpch 0.1]

Run it against 1 replica and again against 2 or more; the answers must be identical.

- Demo checks use the seeded supply-chain data, whose answers are fixed.
- TPC-H checks (--tpch SF) compare against DuckDB's own deterministic TPC-H generator, which is the
  same generator the loader uses, so the expected answer is computed locally at the same scale
  factor. Needs `pip install duckdb==1.1.3`; without it only scale factor 0.1 can be checked, against
  constants recorded from a verified run.

This proves the answers are right. It does NOT prove a query was shared across nodes (see README.md).
Exit status is 1 if any check fails.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal

# Verified: TPC-H scale factor 0.1, three-way join, computed by DuckDB's generator.
SF01_SEGMENTS = [
    ("AUTOMOBILE", 119575, Decimal("4093302441.07")),
    ("BUILDING", 125154, Decimal("4281563957.54")),
    ("FURNITURE", 116577, Decimal("3985249369.26")),
    ("HOUSEHOLD", 117849, Decimal("4013057197.05")),
    ("MACHINERY", 121417, Decimal("4161899266.50")),
]
SF01_LINEITEM = 600572

DEMO_JOIN = ("SELECT s.supplier_id, COUNT(*) AS pos FROM procurement.purchase_orders p "
             "JOIN suppliers.suppliers s ON p.supplier_id = s.supplier_id GROUP BY s.supplier_id ORDER BY 1")
DEMO_EXPECTED = [("1", "2"), ("2", "1"), ("3", "1")]

# {li} and {o}/{c} are the table names as OmniGate sees them (backend.table) or as DuckDB sees them.
SEGMENTS_SQL = ("SELECT c.c_mktsegment AS segment, COUNT(*) AS line_count, "
                "ROUND(SUM(l.l_extendedprice * (1 - l.l_discount)), 2) AS revenue "
                "FROM {li} l JOIN {o} o ON l.l_orderkey = o.o_orderkey "
                "JOIN {c} c ON o.o_custkey = c.c_custkey GROUP BY c.c_mktsegment ORDER BY c.c_mktsegment")
PRIORITY_SQL = ("SELECT o.o_orderpriority AS pr, COUNT(*) AS n FROM {li} l "
                "JOIN {o} o ON l.l_orderkey = o.o_orderkey GROUP BY o.o_orderpriority ORDER BY 1")

results = []


def record(name, ok, detail=""):
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


def skip(name, why):
    results.append((name, "SKIP", why))
    print(f"  [SKIP] {name}  -- {why}")


TOKEN = None


def query(base, sql, timeout):
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(base + "/api/query", data=json.dumps({"sql": sql}).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        title = body.split("<title>")[1].split("</title>")[0] if "<title>" in body else body[:200]
        raise RuntimeError(f"HTTP {e.code}: {title}")


def norm(v):
    """Strip CHAR padding and compare numbers as numbers, so '4093302441.07' == Decimal('4093302441.07')."""
    s = str(v).strip()
    try:
        return Decimal(s)
    except Exception:
        return s


def rows_equal(got, want):
    g = [tuple(norm(x) for x in r) for r in got]
    w = [tuple(norm(x) for x in r) for r in want]
    return g == w


def check_query(base, name, sql, want, timeout):
    try:
        out = query(base, sql, timeout)
        if not out.get("success"):
            return record(name, False, f"query failed: {str(out)[:200]}")
        ok = rows_equal(out["rows"], want)
        record(name, ok, f"got {out['rows'][:6]} expected {want[:6]}")
    except Exception as e:  # noqa: BLE001
        record(name, False, str(e))


def duckdb_truth(sf):
    try:
        import duckdb
    except ImportError:
        return None
    c = duckdb.connect()
    c.execute("INSTALL tpch; LOAD tpch")
    c.execute(f"CALL dbgen(sf={sf})")
    names = dict(li="lineitem", o="orders", c="customer")
    return {
        "lineitem": c.execute("SELECT COUNT(*) FROM lineitem").fetchone()[0],
        "orders": c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "segments": c.execute(SEGMENTS_SQL.format(**names)).fetchall(),
        "priority": c.execute(PRIORITY_SQL.format(**names)).fetchall(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="e.g. http://<load-balancer-ip>:8080")
    ap.add_argument("--tpch", help="TPC-H scale factor loaded in the stack, e.g. 0.1")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--token", default=os.environ.get("OMNIGATE_API_TOKEN"),
                    help="admin API token (or $OMNIGATE_API_TOKEN), needed when admin authentication is on")
    a = ap.parse_args()
    global TOKEN
    TOKEN = a.token
    base = a.url.rstrip("/")

    print(f"OmniGate at {base}")
    try:
        with urllib.request.urlopen(base + "/", timeout=15) as r:
            record("Ask app answers on /", r.status == 200, f"HTTP {r.status}")
    except Exception as e:  # noqa: BLE001
        record("Ask app answers on /", False, str(e))

    print("Supply-chain demo")
    check_query(base, "cross-schema join (suppliers x purchase orders)", DEMO_JOIN, DEMO_EXPECTED, a.timeout)

    if a.tpch:
        print(f"TPC-H scale factor {a.tpch}")
        truth = duckdb_truth(a.tpch)
        if truth is None and a.tpch != "0.1":
            skip("TPC-H checks", f"duckdb not installed and no recorded answers for scale factor {a.tpch}")
        else:
            if truth is None:
                truth = {"lineitem": SF01_LINEITEM, "orders": 150000,
                         "segments": [(s, n, r) for s, n, r in SF01_SEGMENTS], "priority": None}
            check_query(base, "orders count (Postgres backend)", "SELECT COUNT(*) FROM postgres1.orders",
                        [(truth["orders"],)], a.timeout)
            check_query(base, "lineitem count (fact-table backend)", "SELECT COUNT(*) FROM lineitem.lineitem",
                        [(truth["lineitem"],)], a.timeout)
            names = dict(li="lineitem.lineitem", o="postgres1.orders", c="postgres1.customer")
            check_query(base, "three-way join across the two backends",
                        SEGMENTS_SQL.format(**names), truth["segments"], a.timeout)
            if truth["priority"] is not None:
                check_query(base, "two-way join across both backends",
                            PRIORITY_SQL.format(**names), truth["priority"], a.timeout)

    fails = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len([r for r in results if r[1] == 'PASS'])} passed, {len(fails)} failed, "
          f"{len([r for r in results if r[1] == 'SKIP'])} skipped")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
