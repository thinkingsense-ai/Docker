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

## 3. Parallel and cross-node queries (not done yet)

What is known so far, from testing on OKE with v0.10.4:

- Joins that include the S3/Parquet backend are never planned by the parallel engine: the planner logs
  (at debug level only) "one side of the join isn't exactly one backend leaf ... skipping". Database to
  database joins are, but only above `OMNIGATE_PARALLEL_JOIN_MIN_ROWS` (default 10000).
- Nothing is logged when work is actually shipped to another node, so sharing cannot be proven from logs.
  Compare each pod's CPU time (`/proc/1/stat`) before and after a heavy join instead.
- Set **Debug logging for query planning** (`omnigate_debug_federation`) to see the planner's reasons.

Next: load LINEITEM into a second Postgres database so the join is database to database, then compare CPU.

## Known issues that affect testing

- **Server#13**: in cluster mode, startup aborts when the schema has foreign keys (a non-serializable
  `JoinKey`). The TPC-H loader therefore omits foreign keys by default (`tpch.foreignKeys=false`).
- The Parquet connector loads a whole file onto the heap. The stack sets the JVM heap to 65% of the pod
  (about 2GB), enough for scale factor 0.1 (600,000 lineitem rows) but probably not scale factor 1.
