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

`docker build --build-arg OMNIGATE_RELEASE_TAG=v0.6.0 .` (or edit the `ARG` default in
`Dockerfile`, which already points at the latest) picks a different published release. See
[Releases](https://github.com/thinkingsense-ai/Docker/releases) for what's new in each one.
