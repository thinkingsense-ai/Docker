# Commercial-edition test harness

What to run after deploying the OKE stack with a commercial image, in order. Each step says what it
proves and what it does not.

## 0. Deploy

Upload the stack zip (Resource Manager, My configuration). Set the commercial image repository and
tag, the private registry username and token, 2+ replicas, and the Autonomous Database OCID so the
stack whitelists the nodes itself. For the larger dataset tick **Load the TPC-H demo dataset**.

Checks that need no script: `kubectl get pods` all `1/1`; every omnigate pod logs
`cluster joined` and Ignite shows `Baseline size=<replicas>`; no `ORA-` errors.

## 1. Correctness: `verify-correctness.py`

```bash
./verify-correctness.py --url http://<load-balancer-ip>:8080 --tpch 0.1
```

Compares the cluster's answers with ground truth computed outside OmniGate (fixed answers for the
seeded demo; DuckDB's deterministic TPC-H generator for the dataset). Run it with 1 replica and again with
2 or more; a single wrong digit fails it. Proves: answers are right, including joins across a Postgres
and a Parquet backend. Does **not** prove a query was shared across nodes.

## 2. OpenID Connect across replicas: `oidc-test.sh`

Needs an identity provider, with these redirect URIs registered (the proxy makes the browser use
`localhost`, which providers accept over plain http):

- `http://localhost:8080/auth/oidc/callback`
- `http://localhost:8080/app/oidc/callback`

Set the stack's single sign-on fields (issuer, client ID, client secret, at least one admin email), then:

```bash
KUBECONFIG=... ./oidc-test.sh            # login on pod 0, callback on pod 1
KUBECONFIG=... ./oidc-test.sh --swap     # the other way round
```

Sign in at `http://localhost:8080/app/oidc/login` and `/auth/oidc/login`. The script prints which pod
started and which finished the login. Pass = you are signed in. A login that starts on one replica
and ends on another used to fail (Server#12); it needs the same `OMNIGATE_OIDC_STATE_SECRET` on every
replica, which the stack sets. Also add your email as a business user (Settings, Users & access, single
sign-on) before testing the Ask app.

## 3. Parallel and cross-node queries: `measure-distribution.py`

Tick **Load the TPC-H demo dataset** with **TPC-H LINEITEM storage = postgres** (the default), and tick
**Debug logging for query planning**. LINEITEM then lives in a second Postgres database, so the big join is
database to database, which is the only shape the parallel hash join can plan.

OmniGate logs nothing when it ships work to another node, so sharing is measured from outside: the tool runs
a query on one chosen pod and reads every pod's CPU time before and after, minus an idle baseline.

```bash
export KUBECONFIG=...
SQL="SELECT o.o_orderpriority, COUNT(*), SUM(l.l_extendedprice*(1-l.l_discount)) FROM lineitem.lineitem l JOIN postgres1.orders o ON l.l_orderkey = o.o_orderkey GROUP BY o.o_orderpriority ORDER BY 1"
./measure-distribution.py --sql "$SQL" --coordinator 0 --runs 3
```

Then redeploy (or re-apply) with **Share join work across replicas** off and run it again. The comparison is the
evidence: with it on, the other replicas' CPU should rise; with it off, only the coordinator works. Also run
`verify-correctness.py` both ways, since sharing work must not change the answer.

Facts established so far (v0.10.4 on OKE):

- Joins that include the S3/Parquet backend are never planned by the parallel engine; the planner logs (debug
  level only) "one side of the join isn't exactly one backend leaf ... skipping". That is why LINEITEM now defaults to Postgres.
- The parallel engine is skipped below `OMNIGATE_PARALLEL_JOIN_MIN_ROWS` (default 10000 rows).
- The tool also reports whether the engine was used at all (from the coordinator's log) and, if it was not,
  the planner's stated reason.

## Known issues that affect testing

- **Server#13**: in cluster mode, startup aborts when the schema has foreign keys (a non-serializable
  `JoinKey`). The TPC-H loader therefore omits foreign keys by default (`tpch.foreignKeys=false`).
- The Parquet connector loads a whole file onto the heap. The stack sets the JVM heap to 65% of the pod
  (about 2GB), enough for scale factor 0.1 (600,000 lineitem rows) but probably not scale factor 1.
