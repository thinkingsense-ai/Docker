# ThinkingSense — free-edition container image

Run ThinkingSense — ask plain-English questions across your databases, governed and explained —
on your own machine or server with one command.

This is the **free edition**: scale-capped (100 concurrent connections, 2 named backends), not
feature-limited. This repo is fully self-contained and public — it downloads a pre-compiled
`omnigate.jar` and the pre-built web UI from this repo's own
[GitHub Releases](https://github.com/thinkingsense-ai/Docker/releases). No source code and no
private access of any kind is needed; you're running the compiled artifact, the same way you'd
run any closed-source product's Docker image. (The internal package/env-var names still say
`omnigate` in places — that's the product's original internal name, unrelated to anything you
need to know to run it.)

## Deploy it: one command

You need [Docker](https://docs.docker.com/get-docker/) and nothing else.

```bash
git clone https://github.com/thinkingsense-ai/Docker.git
cd Docker
docker compose up --build
```

This starts ThinkingSense **and** a disposable, pre-seeded Postgres database — real, queryable
data with zero setup, so you can see it work before connecting anything of your own. The first
run takes a minute or two (downloading the jar/web UI, pulling the Postgres image).

**Just want the image, no clone?** The same image is also published pre-built to GitHub Container
Registry — `docker pull ghcr.io/thinkingsense-ai/server:0.80` (or `:latest`) — built from source
by the `thinkingsense-ai/Server` repo's own Dockerfile rather than downloaded from a release.
Point it at your own Postgres via `OMNIGATE_BACKENDS` (see the Server repo's README) instead of
using this repo's `docker-compose.yml`.

### Where to go once it's running

| | URL | Sign in with |
|---|---|---|
| 🛠️ **Admin console** | **http://localhost:8080/admin** | *(no login by default — see warning below)* |
| 💬 **Ask** (ask a question in plain English) | **http://localhost:8080/** | username `demo`, password `demo` |

Open the admin console to see your data sources and connect your own; open Ask and sign in with
`demo`/`demo` to ask it a question.

> **⚠️ Before this is reachable by anyone but you**: the admin console ships **unauthenticated**
> in this quick-start config. Uncomment and set `OMNIGATE_AUTH_USERS`/`OMNIGATE_AUTH_API_TOKENS`
> in `docker-compose.yml` first. Same for Ask's `demo`/`demo` account — change or remove the
> `OMNIGATE_APP_USERS` line before this leaves your own machine.

### Add an API key so it can actually answer questions

Get an Anthropic API key at [console.anthropic.com](https://console.anthropic.com/), then either
export it before starting —

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...
docker compose up --build
```

— or put it in a `.env` file next to `docker-compose.yml` (`OMNIGATE_LLM_API_KEY=sk-ant-...`).
Without it, ThinkingSense still starts and the seeded database is still there — you just can't
ask a question in plain English yet. (There's also a real, fully private local-model mode with no
external API at all — see [below](#a-fully-private-option-no-external-api-key-needed).)

## Try it

With the seeded demo running, ask (at `http://localhost:8080/`, signed in as `demo`):

```
Which employees have job SALESMAN in the Chicago department, ordered by salary descending?
```

You'll see the real steps as it answers — understanding the question, generating SQL, checking
access policy, executing, writing the answer — then the exact SQL it generated (a real join it
figured out on its own from the schema, no manual mapping) and a real result: Allen ($1,600),
Turner ($1,500), then Ward and Martin tied at $1,250.

To see how it knew `emp` and `dept` relate, open **http://localhost:8080/admin → Ontology
review** — that relationship was discovered automatically the moment the database was connected.

## Add your own database

The seeded Postgres is a demo. Connect a real one two ways:

**A. Live, from the admin console (no restart)** — go to **Data sources → + add data source**,
enter a name and connection string, click **Discover schemas** to test the connection, then
**Save**. It connects immediately and starts learning the schema in the background.

**B. At startup, via an environment variable** — edit the `OMNIGATE_BACKENDS` line in
`docker-compose.yml`:

```yaml
OMNIGATE_BACKENDS: "demo=jdbc:postgresql://postgres:5432/postgres|postgres|postgres;crm=jdbc:postgresql://your-host:5432/crm|user|pass"
```

(format: `name=jdbcUrl|user|password`, separate multiple with `;`), then `docker compose up
--build` again.

Once connected, you can ask questions that span your database and the seeded demo data together —
that's the point: one question, multiple real sources, one answer.

## Ports

**By default there is exactly one port: `8080`** — the admin console at `/admin`, Ask at `/`. You
don't need to think about ports beyond this unless you want to expose Ask publicly while keeping
the admin console private, in which case see
[`docs/advanced-ports.md`](docs/advanced-ports.md) for the split-port setup and the full port
reference table.

## Features

ThinkingSense is a federated NL2SQL gateway — ask a plain-English question, it figures out which
of your connected data sources answer it, generates and governs the SQL, and explains itself. The
free edition here is scale-capped, not feature-limited — everything below is real and included:

- **Cross-database federation** — one question can join across Postgres, MySQL, Oracle, SQL
  Server, and more real database engines in a single query, plus non-JDBC sources (S3/Parquet,
  Iceberg, Delta Lake, MongoDB, Cassandra, DynamoDB, Kafka, and 19+ SaaS REST connectors like
  Salesforce/HubSpot/Jira/GitHub via OAuth).
- **Automatic ontology discovery** — foreign keys, naming conventions, sampled data, and even
  documents are mined to learn what your tables mean and how they relate, with every suggestion
  reviewed by an admin before it's trusted (see **Admin → Ontology review**).
- **Governed, explainable answers** — every question goes through a visible pipeline (schema
  fidelity checks, access-policy enforcement, execution) shown step-by-step, with the generated
  SQL, a real execution plan, and a confidence score you can inspect.
- **Question Bank & Rollups** — approve a question once and it's answered instantly from then on
  with zero LLM cost; frequently-asked aggregate questions can be auto-detected and pre-computed.
- **Proactive Insights** — approved questions are re-run on a schedule to catch material changes
  or broken queries automatically, with alerts pushed to Slack.
- **Dashboards, Skills, and a group-scoped MCP server** — save question collections as live
  dashboards, create named shortcuts to common questions, and expose your data to Claude or any
  MCP-compatible agent, scoped to exactly the groups/backends that caller is a member of.
- **A tiered model architecture** — a small fast local model answers simple questions instantly, a
  larger local model handles multi-step reasoning, a real tabular ML model (TabPFN) handles
  predictive questions, and a frontier cloud model is the fallback for anything the others can't
  handle — configurable independently, including a fully private, no-external-API mode.
- **Real execution engine improvements** — SEMI/ANTI joins, window functions, set operations,
  and LIMIT/OFFSET all execute natively (not just pushed down), verified against the full 22-query
  TPC-H benchmark suite.
- **Admin console** — data source management, live schema/ontology browsing, access-control
  groups, cost & usage tracking, audit log, and a full review queue for every auto-suggested
  change (never auto-applied without a human).

## Multi-node deployment (high availability)

The single-container quick-start above is for evaluation and small deployments. For production
high-availability/horizontal-scale deployment behind a load balancer, three real, working
Infrastructure-as-Code stacks are provided under [`resource-manager/`](resource-manager/):

### Start with OCI (Oracle Cloud) — the most complete, sized for the Always-Free tier

**[`resource-manager/omnigateokestack/`](resource-manager/omnigateokestack/)** deploys ThinkingSense
onto a real Oracle Kubernetes Engine (OKE) cluster via Terraform + Helm, one-click deployable
through the OCI Console's Resource Manager. It already includes:

- A real **Network Load Balancer (NLB)** in front of ThinkingSense — chosen deliberately over a
  classic Layer-7 load balancer, which was confirmed live to buffer/break the Ask app's streaming
  (SSE) responses. The NLB is pure L4 TCP passthrough and doesn't.
- **Multi-node / high-availability support**: set `omnigate_replica_count` (2–4) plus a real,
  separately-provisioned shared Postgres for `omnigate_config_db_url`/`user`/`password`, and the
  chart automatically switches from a single-pod local-disk config store to a shared one every
  replica can safely read from, with the NLB load-balancing across however many replicas are
  running — no additional networking configuration needed. See
  [`resource-manager/omnigateokestack/README.md`](resource-manager/omnigateokestack/README.md#going-multi-node-high-availability--horizontal-scale)
  for the exact console/CLI steps.

```bash
oci resource-manager stack create \
  --compartment-id <ocid> --region <region> \
  --config-source resource-manager/omnigateokestack \
  --display-name thinkingsense-oke \
  --variables '{"compartment_ocid":"<ocid>","region":"<region>","omnigate_app_password":"<password>","omnigate_llm_api_key":"<anthropic-key>","omnigate_replica_count":3,"omnigate_config_db_url":"jdbc:postgresql://<managed-db-host>:5432/omnigate_config","omnigate_config_db_user":"<user>","omnigate_config_db_password":"<password>"}'
```

### AWS and GCP — real stacks, not yet given the same multi-node treatment

- **[`resource-manager/omnigateeksstack/`](resource-manager/omnigateeksstack/)** — AWS EKS,
  Helm + CloudFormation.
- **[`resource-manager/omnigategkestack/`](resource-manager/omnigategkestack/)** — GCP GKE,
  Helm + Terraform.

Both are real, working single-node deployments today. They have not yet received the
`replicaCount`/external-shared-config-database enhancement the OKE stack above just got — that
work is a natural next step (the underlying Helm chart mechanism is the same one to port), but is
not yet done. If multi-node HA on AWS or GCP is a near-term need, start from the OKE stack's own
`helm/omnigate/` chart as the reference implementation.

## A bigger demo: real multi-database federation

To see a genuine cross-database join (not the single-table demo above), see
[`fixtures/supply-chain/`](fixtures/supply-chain/) — a real supply-chain scenario across four
separate database engines (or a lighter single-Postgres/CSV variant if you don't want to run all
four). See [`fixtures/supply-chain/DOCKER-USAGE.md`](fixtures/supply-chain/DOCKER-USAGE.md).

## A fully private option: no external API key needed

This image also bundles a real local model — no data ever leaves the container, no API key, no
internet access required for it to answer questions. Set `OMNIGATE_LLM_MODE=local-only`. See
[`docs/local-model.md`](docs/local-model.md) for the license terms (research/non-commercial use
for the bundled model — commercial alternatives are listed there) and memory requirements
(give Docker at least 8GB).

## What's here

- `Dockerfile` — downloads the pre-built jar/web UI from this repo's
  [Releases](https://github.com/thinkingsense-ai/Docker/releases) and packages a runnable image.
  Pin a specific version with the `OMNIGATE_RELEASE_TAG` build arg.
- `docker-compose.yml` — the local stack: seeded Postgres + local-model sidecars + ThinkingSense.
- `docker/seed.sql` — the demo seed data.
- `fixtures/` — the bigger multi-database demo (see above).
- `NOTICE-qwen.txt` — license attribution for the bundled local model.

## Upgrading

`docker build --build-arg OMNIGATE_RELEASE_TAG=v0.8.0 .` (or edit the `ARG` default in
`Dockerfile`, which already points at the latest) picks a different published release. See
[Releases](https://github.com/thinkingsense-ai/Docker/releases) for what's new in each one.
