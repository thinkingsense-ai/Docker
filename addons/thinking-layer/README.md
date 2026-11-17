# Thinking layer (phase 2 skeleton, plus what the phase 3 UI needs)

The small service between the front-ends (Agency, later Ask and Claude) and the OmniGate Server. See [docs/agency-spec.md](../../docs/agency-spec.md) section 4 and
[docs/agency-design.md](../../docs/agency-design.md). Standard library Python, no dependencies, no database.

What works now:

| Route | What |
|---|---|
| `POST /login`, `POST /logout`, `GET /whoami` | Signs in to the Server's business-user login; the layer holds the Server's cookie and gives the browser its own `HttpOnly` cookie |
| `GET /packs` | The pack catalogue (`packs/catalogue.json`) with whether each pack is loaded: a Workspace named for it, an approved-question category, or unknown |
| `POST /ask` | Sets the session's Workspace to the pack (or the default for All data), asks, and returns the answer with an **evidence block**; with `Accept: text/event-stream` it relays the Server's events and puts an `evidence` event just before `done` |
| `GET /decisions?runId=` | The hash-chained decision record for a run the Server shows this user, with the chain verified here. Needs `AGENCY_DECISION_FILE` (the Server's `OMNIGATE_WORKFLOW_DECISION_FILE`, shared read-only) |
| `GET /starters?pack=`, `GET /conversations`, `GET /conversations/get?id=` | Pass-through to the Server's starter questions (only catalogue pack ids are forwarded) and the signed-in user's conversations; the id is URL-encoded |
| `GET/POST /preferences` | Per-user preference (`pack` only, validated) keyed by Server username; in memory, or a JSON file when `AGENCY_PREFS_FILE` is set |
| `GET /` and other non-API paths | The built Agency UI from `AGENCY_WEB_DIST` (single-page fallback, path-escape safe, CSP `default-src 'self'`); never for `/app/` or `/api/` |
| `GET /status`, `GET /tools`, `GET /health` | Reachability, whether the workflow routes exist (the free edition answers 404), and the tool list generated from `contract.json` |

Run the tests (a fake Server stands in): `python3 -m unittest discover -s addons/thinking-layer/tests` from the repository root.
Run beside a pack stack: see `docker-compose.layer.yml`.

Things to know:
- **Scope.** The Server limits a Workspace by data source, not schema (Server#109), and on today's stacks no Workspace exists for a pack until the generated `packs/workspaces.yaml` is loaded. The evidence block says which case applied: `server-backends`, `agency-hint` (opt-in `AGENCY_SCOPE_HINT=on`, which appends the pack's data sets to the question; its effect on accuracy is **not measured**) or `none`.
- **One question at a time per session**, because the Workspace is session state on the Server.
- **Decisions.** The Server has no business-user route for the decision record in v0.10.19, so the layer reads the shared file. A route would remove that; to raise with Kumar.
- **Edition.** The Server does not report its edition to business users; `/status` infers "workflows available" from the workflow route answering.
- The layer logs no question text and no file content. Sessions are in memory (a restart signs everyone out).
- The UI is `agency/web` (see its README); the Dockerfile builds it and the layer serves it on the same port.
- Not built yet: uploads, search, workflow start/queue/approve (phases 4 and 5), MCP `tools/call`.
