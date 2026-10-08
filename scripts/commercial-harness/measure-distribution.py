#!/usr/bin/env python3
"""Shows whether ONE query's work was spread across the replicas.

OmniGate logs nothing when it ships part of a join to another node, so this measures it from outside:
it runs a query on a chosen coordinator pod and reads every pod's CPU time (/proc/1/stat, the JVM) before
and after. If the other replicas did real work, their CPU rises; if the coordinator did it all, they stay
at idle. An idle baseline is measured first and subtracted.

  KUBECONFIG=... measure-distribution.py --sql "SELECT ..." [--coordinator 0] [--runs 3]

It also reports, from the coordinator's log, whether the parallel hash join engine was used at all (and, with
planner debug logging on, why it declined). A join that never used the parallel engine cannot be shared.

Reading the result: "peer CPU" well above the baseline noise, and a sensible share of the total, means work
reached the other replicas. Compare a run with cross-replica joins on against one with them off
(omnigate_remote_join_enabled) to be sure the difference is the feature and not the load balancer.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request

LOCAL_PORT = 18090
TICK_MS = 10  # /proc/<pid>/stat is in clock ticks; Linux uses 100 per second


def sh(*cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"{' '.join(cmd)} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def replicas():
    out = sh("kubectl", "get", "statefulset", "omnigate-omnigate", "-o", "jsonpath={.spec.replicas}")
    return int(out.strip())


def cpu_ms(pod):
    out = sh("kubectl", "exec", pod, "--", "sh", "-c", "awk '{print $14+$15}' /proc/1/stat").strip()
    return int(out.splitlines()[-1]) * TICK_MS


def snapshot(pods):
    return {p: cpu_ms(p) for p in pods}


def run_query(sql, timeout):
    req = urllib.request.Request(f"http://127.0.0.1:{LOCAL_PORT}/api/query",
                                 data=json.dumps({"sql": sql}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return time.time() - t0, body


def engine_lines(pod, since):
    log = sh("kubectl", "logs", pod, f"--since={since}s", check=False)
    used = [l for l in log.splitlines() if "executing via the parallel hash join engine" in l]
    why = [l.split(" - ", 1)[-1] for l in log.splitlines() if "parallel join planner:" in l]
    return len(used), why[-2:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True)
    ap.add_argument("--coordinator", type=int, default=0, help="which omnigate-omnigate-N takes the request")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--idle-seconds", type=int, default=6)
    a = ap.parse_args()

    n = replicas()
    pods = [f"omnigate-omnigate-{i}" for i in range(n)]
    coord = pods[a.coordinator]
    if n < 2:
        sys.exit("only one replica: there is nothing to share work with")

    pf = subprocess.Popen(["kubectl", "port-forward", f"pod/{coord}", f"{LOCAL_PORT}:8080"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        print(f"coordinator {coord}; {n} replicas; measuring idle baseline for {a.idle_seconds}s ...")
        b0 = snapshot(pods)
        time.sleep(a.idle_seconds)
        b1 = snapshot(pods)
        idle_rate = {p: (b1[p] - b0[p]) / a.idle_seconds for p in pods}  # CPU ms per second at rest

        start = time.time()
        rows_seen, results = set(), []
        for i in range(a.runs):
            before = snapshot(pods)
            elapsed, body = run_query(a.sql, a.timeout)
            after = snapshot(pods)
            if not body.get("success"):
                sys.exit(f"query failed: {str(body)[:300]}")
            rows_seen.add(json.dumps(body["rows"], sort_keys=True))
            work = {p: max(0.0, (after[p] - before[p]) - idle_rate[p] * elapsed) for p in pods}
            results.append((elapsed, work))
            peers = sum(w for p, w in work.items() if p != coord)
            total = sum(work.values()) or 1.0
            print(f"run {i + 1}: {elapsed:6.1f}s  " + "  ".join(f"{p[-1]}={w:7.0f}ms" for p, w in work.items())
                  + f"   peers hold {100 * peers / total:4.1f}% of the work")

        used, why = engine_lines(coord, int(time.time() - start) + 30)
        print("\nresult rows identical across runs:", "yes" if len(rows_seen) == 1 else "NO -- DIFFERENT ANSWERS")
        print(f"parallel hash join engine used on {coord}: {used} time(s)")
        if not used:
            print("  not used; planner said:", why or "(nothing logged; enable debug logging for query planning)")
        med = statistics.median(sum(w for p, w in r[1].items() if p != coord) for r in results)
        coord_med = statistics.median(r[1][coord] for r in results)
        print(f"median CPU: coordinator {coord_med:.0f} ms, other replicas {med:.0f} ms combined")
        print("verdict:", "work reached other replicas" if used and med > 0.1 * max(coord_med, 1)
              else "no evidence the work was shared (see above)")
    finally:
        pf.terminate()


if __name__ == "__main__":
    main()
