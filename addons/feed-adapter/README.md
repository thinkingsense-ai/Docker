# Feed adapter

Reads public RSS and Atom feeds every 30 minutes, keeps what a short set of readable rules calls a possible AI-hacking story, groups headlines about one event into a **candidate**, and writes it all into the `rca` tables (design: `docs/agency-it-risk-flow.md`, section 5). **Watch** lists the candidates and **Sources** shows each feed's health, both through approved questions the Server answers as the signed-in person.

It is a lead finder, not an analyst. It never traces, grades or publishes anything: a person opens a candidate, and the trace step (find the primary source, grade each link) is **not built yet**. A news headline is only ever a lead, never evidence of a cause.

## What it stores

**Metadata only:** the headline, its link, its date, the source, a hash, and why the rules matched. The adapter reads a short description to match on and drops it; no article text is stored. Items older than 400 days are deleted unless a candidate cites them. Because every item keeps `first_seen_at`, counts over time (items per week per source, leads per week by claim type) are real, which a live read of a feed (it holds only its last 20 to 50 items) could not give.

**Reuse terms have not been read for any feed.** Only `robots.txt` is honoured (below). Counsel should see this next to the licence register before anything beyond a demo.

## How it behaves

- **Polite:** one conditional request per feed per pass (ETag and Last-Modified), `robots.txt` honoured under the agent name `ThinkingSenseFeedReader` (4xx = no rules, 5xx or unreachable = not fetched, a disallowed feed is recorded as `blocked_by_robots`), at least a second between requests to one host, responses capped at 3 MB, 200 items per feed, 20 s timeout. The user agent carries the product name and `thinkingsense.ai`, no personal details.
- **Safe parsing:** a feed with a document type declaration or entities is refused (no expansion); only `http` and `https` addresses become links, and the UI makes a link of nothing else.
- **Health is recorded, never hidden:** each pass writes `last_status` (`ok`, `not_modified`, `blocked_by_robots`, `http_error`, `parse_error`, `unreachable`), the error and the last success per feed. A feed that fails keeps its last good ETag. One feed (Schneier) answered 403 once during testing after repeated passes in an hour, then recovered: Sources showed it as failing in between.
- **Writes as its own role:** `feed_writer` (created in `demos/it-risk-rca/grant-rca.sql`, local-demo password) may write the feed tables and the candidates it creates, and nothing else. It uses the `psql` client with values bound as one JSON document, so no database driver is added to the image.

## The rules (demo rules, for Leo's review)

`rules.py`, readable and tested, not a measured classifier. A **context** feed never creates a candidate. A story needs AI (the word, `LLM`, `deepfake`, a model vendor...) plus an incident or a weakness; a story that *claims an AI attack* needs AI plus an attack plus an incident, so "AI-powered attacks are rising" is not a candidate. Reporting says `ai-attack-claimed`; an official source says `ai-attack-confirmed`; AI with an outage or vulnerability but no attack is `ai-adjacent`. Digests and promotions ("This month in security", "In Other News", "Feedback Friday", webinars) never match. Clustering: two headlines are one candidate within two days if they share a name, or within a week if they share two; two existing candidates are never merged.

**Measured on 2026-11-20 (one pass of the 12 starter feeds):** 330 headlines, 23 matched before the roundup rule and 18 after (about 5%), 11 candidates. Precision and recall are NOT measured: that is the pilot's job (build step 8), with Leo reading what it caught and missed.

## Run it

Off unless added (it reads the internet). From the repository root, with a stack that carries `demos/it-risk-rca`:

```bash
docker compose --project-directory . -f <pack compose> -f demos/it-risk-rca/docker-compose.rca.yml -f addons/feed-adapter/docker-compose.feed.yml up --build
```

The local sandbox adds it with `AGENCY_FEED=on agency/local/up.sh`. One pass without the loop: `python adapter.py --once`. Tests (no network, no database): `python3 -m unittest discover -s addons/feed-adapter/tests`.

## Known limits

- The feed tables need a fresh Postgres volume or a manual reload of `seed-rca-postgres.sql` and `grant-rca.sql` on an existing stack.
- **The question seeder skips a question already in the bank by its text**, so a changed reference SQL (the Watch question gained the lead columns) does not reach an existing stack until its bank entry is deleted (`POST /api/question-bank/delete`) and the seeder re-run.
- The cloud charts do not carry the `rca` schema or this adapter. The local sandbox's feed runs against real third-party sites; do not point many stacks at the same feeds.
- Not built: a trace step for a candidate, a Trends panel (counts over time are in the data), feeds that need a filter (OpenAI, DeepMind, The Hacker News, BleepingComputer after terms), X.
