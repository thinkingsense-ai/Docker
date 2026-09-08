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
and pulling the Postgres image). Once the startup log settles, open:

- **`http://localhost:8080/admin`** — the admin console (data sources, ontology, access policy).
  **Unauthenticated by default** in this quick-start config — fine for trying it out locally,
  **not** fine for anything reachable beyond your own machine (uncomment and set
  `OMNIGATE_AUTH_USERS`/`OMNIGATE_AUTH_API_TOKENS` in `docker-compose.yml` before you expose this
  anywhere).
- **`http://localhost:8080/`** — the Ask app. Unlike the admin console, this **always** requires
  signing in (a business-user question always runs under a real access-control identity, never
  anonymously) — this compose file ships one working demo account for exactly this purpose:
  **username `demo`, password `demo`**. Log in with it, then change or remove the
  `OMNIGATE_APP_USERS` line in `docker-compose.yml` before running this anywhere but your own
  machine.

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

## Ports — Admin console vs. Ask app

By default **one port serves both apps**: `http://localhost:8080/admin` (the admin console) and
`http://localhost:8080/` (the Ask app) — differentiated only by path, same server.

If you want them on **two separate ports** instead (useful if you want to expose the Ask app
publicly while keeping the admin console reachable only on an internal network), set
`OMNIGATE_ASK_PORT` alongside the existing `OMNIGATE_HTTP_PORT`:

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

## What's here

- `Dockerfile` — downloads the pre-compiled `omnigate.jar` and web UI from this repo's own
  [Releases](https://github.com/thinkingsense-ai/Docker/releases) (pinned to a specific tag via
  the `OMNIGATE_RELEASE_TAG` build arg) and packages them into a slim JRE image with the
  free-edition marker baked in. No build tools, no source, nothing beyond `curl` and a JRE.
- `docker-compose.yml` — the local dev stack described above (OmniGate + a seeded Postgres).
- `docker/init-scott.sql` — the seed data for that Postgres service. Deliberately seeded into the
  default `public` schema, not a separate named schema — OmniGate's own schema introspection only
  scans a connecting account's default schema, so anything in another schema is invisible to
  NL2SQL/the Ontology with no error at all.
- `.dockerignore`

## Picking up a newer release

`docker build --build-arg OMNIGATE_RELEASE_TAG=v0.2.0 .` (or edit the `ARG` default in
`Dockerfile`) points the build at a different published release without touching anything else in
this repo.
