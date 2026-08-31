# OmniGate — free-edition container image

This repo holds the build recipe for the **free edition only** — the edition with the
connection/backend-count caps baked in (`Edition.current()` reads a marker file this `Dockerfile`
writes, which wins over any `OMNIGATE_EDITION` env var override).

**The commercial (unrestricted) Dockerfile and the generic/default Dockerfile intentionally do not
live here** — both stay in the `Server` repo, so only people with access to this repo (and thus the
free-edition licensing limitations) get this recipe; the unrestricted build stays private.

## What's here

- `Dockerfile` — the free-edition multi-stage build (was `Dockerfile.free` in `Server`).
- `docker-compose.yml` — local dev stack (OmniGate + Postgres).
- `docker/init-scott.sql` — seed data for the compose Postgres service.
- `.dockerignore`

## Build context caveat

`docker-compose.yml`'s `build: .` (and a plain `docker build .` here) needs `pom.xml`, `src/`, and
`web/` from the `Server` repo present in this same directory to actually build — this repo holds
the *recipe*, not a copy of the source. A CI pipeline building this image needs to check out `Server`
into this directory (or an equivalent multi-context build) before running `docker build`.
