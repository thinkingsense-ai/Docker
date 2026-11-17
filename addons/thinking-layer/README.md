# Thinking layer (phase 2 skeleton)

The small service between the front-ends (Agency, later Ask and Claude) and the OmniGate Server. See [docs/agency-spec.md](../../docs/agency-spec.md) section 4 and
[docs/agency-design.md](../../docs/agency-design.md). Standard library Python, no dependencies, no database.

What works now:

| Route | What |
|---|---|
| `POST /login`, `POST /logout`, `GET /whoami` | Signs in to the Server's business-user login; the layer holds the Server's cookie and gives the browser its own `HttpOnly` cookie |
| `GET /packs` | The pack catalogue (`packs/catalogue.json`) with whether each pack is loaded: a Workspace named for it, an approved-question category, or unknown |
| `POST /ask` | Sets the session's Workspace to the pack (or the default for All data), asks, and returns the answer with an **evidence block**; with `Accept: text/event-stream` it relays the Server's events and puts an `evidence` event just before `done` |
| `GET /decisions?runId=` | The hash-chained decision record for a run the Server shows this user, with the chain verified here. Needs `AGENCY_DECISION_FILE` (the Server's `OMNIGATE_WORKFLOW_DECISION_FILE`, shared read-only) |
| `GET /status`, `GET /tools`, `GET /health` | Reachability, whether the workflow routes exist (the free edition answers 404), and the tool list generated from `contract.json` |

Run the tests (a fake Server stands in): `python3 -m unittest discover -s addons/thinking-layer/tests` from the repository root.
Run beside a pack stack: see `docker-compose.layer.yml`.

Things to know:
- **Scope.** The Server limits a Workspace by data source, not schema (Server#109), and on today's stacks no Workspace exists for a pack until the generated `packs/workspaces.yaml` is loaded. The evidence block says which case applied: `server-backends`, `agency-hint` (opt-in `AGENCY_SCOPE_HINT=on`, which appends the pack's data sets to the question; its effect on accuracy is **not measured**) or `none`.
- **One question at a time per session**, because the Workspace is session state on the Server.
- **Decisions.** The Server has no business-user route for the decision record in v0.10.19, so the layer reads the shared file. A route would remove that; to raise with Kumar.
- **Edition.** The Server does not report its edition to business users; `/status` infers "workflows available" from the workflow route answering.
- The layer logs no question text and no file content. Sessions are in memory (a restart signs everyone out).
- Not built yet: uploads, search, workflow start/queue/approve (phases 4 and 5), the UI (phase 3), MCP `tools/call`.
