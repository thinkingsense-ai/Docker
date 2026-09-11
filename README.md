# OmniGate — free-edition container image

This repo holds the build recipe for OmniGate's **free edition** — the edition with the
connection/backend-count caps baked in (`Edition.current()` reads a marker file this `Dockerfile`
writes, which wins over any `OMNIGATE_EDITION` env var override — 100 concurrent connections, 2
named backends; not feature-limited, only capped on scale).

**This repo is fully self-contained and public.** It builds the image by downloading a
pre-compiled `omnigate.jar` and the pre-built web UI from this repo's own
[GitHub Releases](https://github.com/thinkingsense-ai/Docker/releases) — no other repo, no source
code, and no private access of any kind is needed. OmniGate's source lives in a separate, private
repo; you're running the compiled artifact, the same way you'd run any closed-source product's
Docker image.

## The absolute minimum: one command, no config

You need [Docker](https://docs.docker.com/get-docker/) and nothing else:

```bash
git clone https://github.com/thinkingsense-ai/Docker.git
cd Docker
docker compose up --build
```

This starts OmniGate **and** a disposable, pre-seeded Postgres database (the classic `emp`/`dept`
schema) — real, queryable data with zero setup, so you can see the whole product work before
connecting anything of your own. Give it a minute the first time (it's downloading the jar/web UI
and pulling the Postgres image).

### Where to go once it's running

| | URL | Sign in with |
|---|---|---|
| 🛠️ **Admin console** | **http://localhost:8080/admin** | *(no login by default — see warning below)* |
| 💬 **Ask app** (ask a question in English) | **http://localhost:8080/** | username `demo`, password `demo` |

That's it — two URLs, one on the same port by default. Open the Admin console to see your data
sources and connect your own; open the Ask app and log in with `demo`/`demo` to actually ask it a
question.

> **⚠️ Before you put this anywhere reachable by anyone but you**: the admin console above ships
> **unauthenticated** in this quick-start config — anyone who can reach that URL can see and change
> everything. Uncomment and set `OMNIGATE_AUTH_USERS`/`OMNIGATE_AUTH_API_TOKENS` in
> `docker-compose.yml` first. Same idea for the Ask app's `demo`/`demo` account — change or remove
> the `OMNIGATE_APP_USERS` line before this leaves your own machine.

**One thing you'll want to add before asking a real question**: an Anthropic API key, so the Ask
app can actually translate English into SQL. Get one at
[console.anthropic.com](https://console.anthropic.com/), then either export it before starting the
stack —

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...
docker compose up --build
```

— or put it in a `.env` file next to `docker-compose.yml` (`OMNIGATE_LLM_API_KEY=sk-ant-...`).
Without it, the gateway still starts and the seeded Postgres is still there — you just can't ask
it a question in English yet (raw SQL over any of the native wire protocols still works).

## Ask your first question — proving NL2SQL + the Ontology actually work

The seeded database is deliberately not empty and not trivial: `emp` references `dept`, salaries
vary, and nothing about that relationship is spelled out to the LLM by hand — the Ontology has to
discover it. Log in to the Ask app (`http://localhost:8080/`, `demo`/`demo`) and try:

```
Which employees have job SALESMAN in the Chicago department, ordered by salary descending?
```

(Literal column-shaped phrasing like this, rather than a business synonym like "salespeople," is
deliberate for this specific demo — the seed data has no glossary entry teaching the model that
"salespeople" means `job = 'SALESMAN'`; that's exactly what OmniGate's Metrics registry is for on
a real deployment, just not something a bare seed script provides for free.)

That question only resolves correctly if three separate things this product advertises are
actually true, and each is visible in the response:

1. **The live trace** shown while it runs — "understanding the question, generating SQL, checking
   access policy, executing, writing the answer" — is a real step-by-step trace of the pipeline
   running, not a spinner.
2. **The collapsible "SQL" panel** on the answer shows the exact generated SQL — a real join the
   Ontology's own foreign-key extraction made possible:
   ```sql
   SELECT e.empno, e.ename, e.job, e.sal FROM emp e JOIN dept d ON e.deptno = d.deptno
   WHERE LOWER(e.job) = LOWER('SALESMAN') AND LOWER(d.loc) = LOWER('Chicago')
   ORDER BY e.sal DESC
   ```
3. **The narrated answer + result table** should name four real rows from the seed data — Allen
   ($1,600), Turner ($1,500), then Ward and Martin tied at $1,250 — not a hallucinated table or a
   canned response.

To see *why* that join was possible before you even ask a question, open
`http://localhost:8080/admin` → **Ontology review** and look for the `emp.deptno → dept.deptno`
relationship — either in the relationship list, or as an edge in the **Semantic Graph** panel on
the same page (an interactive node graph of the same data; also fetchable directly at
`GET /api/ontology.json`). That relationship was extracted automatically the moment the seeded
backend was introspected at startup — zero manual mapping. It shows up already-accepted rather
than sitting in a review queue because a plain declared foreign key is exactly the
high-confidence, auto-acceptable case; a relationship inferred from data sampling instead of a
declared FK would wait for a human to approve it.

## Ports — the simple version

**By default there is exactly one port: `8080`.** Both apps live there, split only by URL path —
`/admin` for the admin console, `/` for the Ask app (the table above). You never need to think
about ports at all unless you want the advanced setup below.

### Advanced: putting the Ask app on its own separate port

Only do this if you specifically want to expose the Ask app to the public internet while keeping
the admin console reachable only from inside your own network. Set `OMNIGATE_ASK_PORT` alongside
the existing `OMNIGATE_HTTP_PORT`:

```yaml
environment:
  OMNIGATE_HTTP_PORT: "8080"   # admin console + /api + /app only, once ASK_PORT is set
  OMNIGATE_ASK_PORT: "8081"    # Ask app only
ports:
  - "8080:8080"
  - "8081:8081"
```

**This is a hard split, not a mirror**: once `OMNIGATE_ASK_PORT` is set, port 8080 stops serving
the Ask app's own routes (404s them) and port 8081 stops serving `/admin`/admin API routes (404s
those). Leave `OMNIGATE_ASK_PORT` unset (the default in this repo's `docker-compose.yml`) to keep
the original single-port behavior — nothing else changes either way.

Every port this image can expose, and what each one is for:

| Port | Protocol | Purpose |
|---|---|---|
| `8080` | HTTP | Admin console (`/admin`) + Ask app (`/`) + `/api/*` + `/app/*` + `/mcp*` — unless split, see above |
| `8081` | HTTP | Ask app only, when `OMNIGATE_ASK_PORT` is set |
| `8443` | HTTPS | Same as 8080, when TLS is configured (`OMNIGATE_TLS_*`) |
| `5433` | Postgres wire | Query any registered backend using a plain `psql`/Postgres client |
| `3306` | MySQL wire | Same, using a MySQL client |
| `1521` | Oracle wire | Same, using an Oracle client |
| `7070` | gRPC | Native JDBC driver, if you're using OmniGate's own driver rather than a wire-protocol client |
| `2484` | TCP | Oracle TLS variant, when TLS is configured |

## Add your own backend

The seeded Postgres is a demo, not the point. Add a real backend one of two ways:

**A. Live, via the admin console (no restart)** — go to **Data sources**, click
**+ add data source**, and fill in a name and connection string (credentials support a
`vault://`/`cyberark://` reference too, resolved at connect time). **Discover schemas** does a
real dry-run connection before you save. Clicking **Save** hot-reloads the connection pool
immediately — the three onboarding pipelines (metadata, data-driven sampling, statistics) kick off
automatically, same as they did for the seeded Postgres, with their live progress shown right
there on the page.

**B. At container start, via `OMNIGATE_BACKENDS`** (format: `name=jdbcUrl|user|password`,
`;`-separated for more than one). Edit the `OMNIGATE_BACKENDS` line already in
`docker-compose.yml` and add your backend alongside the seeded `demo` one:

```yaml
OMNIGATE_BACKENDS: "demo=jdbc:postgresql://postgres:5432/postgres|postgres|postgres;crm=jdbc:postgresql://your-host:5432/crm|user|pass"
```

then `docker compose up --build` again.

Either way, once a backend is registered you can ask questions that span it and the seeded demo
data together — that's the federation story: one question, multiple real backends, one answer.

## A bigger, real demo: the supply chain fixture

Want to try a genuine multi-source federated question (real cross-database joins, not the
single-table `emp`/`dept` demo above)? See [`fixtures/supply-chain/`](fixtures/supply-chain/) — a
real supply-chain story with three infrastructure tiers to match what you have available: four
real database engines (Postgres/MySQL/Oracle/SQL Server), a single-Postgres variant (just four
schemas, zero extra infrastructure), or a mixed CSV/object-storage + Postgres variant. All three
are live-verified to return the same correct answer to the same canonical question. See
[`fixtures/supply-chain/DOCKER-USAGE.md`](fixtures/supply-chain/DOCKER-USAGE.md) for how to run
each tier against this repo's own Docker image.

## What's here

- `Dockerfile` — downloads the pre-compiled `omnigate.jar` and web UI from this repo's own
  [Releases](https://github.com/thinkingsense-ai/Docker/releases) (pinned to a specific tag via
  the `OMNIGATE_RELEASE_TAG` build arg) and packages them into a slim JRE image with the
  free-edition marker baked in, plus a real bundled local reasoning model (see below). No build
  tools, no source — the JRE image itself pulls in `curl`, `libgomp1`, and a `llama-server` binary.
- `docker-compose.yml` — the local dev stack described above (OmniGate + a seeded Postgres).
- `docker/init-scott.sql` — the seed data for that Postgres service. Deliberately seeded into the
  default `public` schema, not a separate named schema — OmniGate's own schema introspection only
  scans a connecting account's default schema, so anything in another schema is invisible to
  NL2SQL/the Ontology with no error at all.
- `NOTICE-qwen.txt` — the license attribution the bundled local model requires (see below).
- `.dockerignore`

## The bundled local reasoning model — real, private, out-of-the-box NL2SQL

This image bundles a real local model (Qwen2.5-3B-Instruct, quantized, ~2GB) plus a real
`llama-server` binary (from [llama.cpp](https://github.com/ggml-org/llama.cpp)), wired up
automatically via `OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH`/`OMNIGATE_ASSISTANT_MODEL_PATH`. Set
`OMNIGATE_LLM_MODE=local-only` and NL2SQL works with **zero external configuration and zero data
ever leaving the container** — no `OMNIGATE_LLM_API_KEY`, no outbound API calls at all. See the
Server repo's `LlmMode` for the other three modes (`local-first`, `cloud-first`,
`customer-model-only`).

**License, read before using this in anything but non-commercial evaluation**: Qwen2.5-3B-Instruct
is distributed under Alibaba's own "Qwen RESEARCH LICENSE AGREEMENT" — **non-commercial use only**.
This free/developer image is exactly that use case; if you need a local model for a *commercial*
deployment, either bring your own (point `OMNIGATE_ASSISTANT_MODEL_PATH`/
`OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH` at a model you're licensed to use commercially — Microsoft's
MIT-licensed Phi-3.5-mini-instruct or Apache-2.0-licensed Qwen2.5-1.5B/7B-Instruct are real,
verified-commercially-usable alternatives in a similar size class) or use `OMNIGATE_LLM_MODE=
cloud-first`/`customer-model-only` instead. The required attribution notice is shipped as
`NOTICE-qwen.txt` in the image and this repo.

**Memory**: running two local model instances simultaneously (one for NL2SQL, one for embeddings —
see `OMNIGATE_EMBEDDING_MODEL_PATH` if you want to point the embeddings role at a different,
smaller model) needs real headroom. Confirmed live: a Docker host/VM with only ~7-8GB of total
memory available was not enough — the kernel OOM-killed the NL2SQL model process under load while
the embeddings process was also running. Give Docker at least 8GB, ideally more, or point
`OMNIGATE_EMBEDDING_MODEL_PATH` at a genuinely small dedicated embeddings model to reduce the
simultaneous footprint.

## Picking up a newer release

`docker build --build-arg OMNIGATE_RELEASE_TAG=v0.2.0 .` (or edit the `ARG` default in
`Dockerfile`) points the build at a different published release without touching anything else in
this repo.
