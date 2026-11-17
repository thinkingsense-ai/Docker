# Agency: application specification (draft)

Status: draft for review, nothing built. Written 2026-11-17. Builds on [agency-design.md](agency-design.md) (architecture, packs as Workspaces, serving) and
[packs/](../packs/README.md) (phase 1). This document says what Agency does, for whom, through which API, and how we will know it works.

## 1. Purpose

Agency is a second front-end to OmniGate for people who ask questions of governed data, bring other kinds of input (audio, images, documents, tables),
and act on answers through approved workflows. It exists so we can show and ship those capabilities without a Server release for each one. It is a client of
the Server and of a small thinking-layer service; it does not contain query planning, joins, ontology or access control.

Non-goals: replacing Ask; an admin console; a second query planner; storing customer data outside the customer's own sources; training models.

## 2. Users

| User | Needs |
|---|---|
| Analyst / business user | Ask in a domain (pack/Workspace), see the answer with its evidence, follow up, save, export |
| Approver | See what is waiting, see facts and the AI recommendation, approve or reject; cannot approve their own requests |
| Presenter / evaluator | Switch domains quickly, try an upload, see what is loaded and what is not, no surprises about edition or licence |
| Claude (as a front-end) | The same operations as tools, with the same access checks |
| Operator | Know what Agency can reach, which adapters are on, which edition it is running |

## 3. Functional requirements

IDs are stable so tests and PRs can cite them. "Server" means the OmniGate Server APIs as released; a requirement that needs a Server change says so.

### 3.1 Sign-in and session
- FR-1 Sign in with the Server's business-user login (local accounts or SSO); Agency stores no passwords. Agency has its **own Server login**: its layer signs the user in at the Server's business-user login and holds that session itself, so the Workspace chosen in Agency is separate from the one chosen in Ask (decision, section 10).
- FR-2 The caller's identity is forwarded on every call; Agency never widens access. A 401/403 from Server is shown as such, not retried as another user.
- FR-3 Shows who is signed in, the edition (free/commercial) and the Server version.

### 3.2 Pack (Workspace) selection
- FR-4 Lists packs from the catalogue (`packs/catalogue.json`, later `GET /packs`) as cards: title, one-line summary, sources, tables, approved-question count, badges (edition, non-commercial data, needs embedding model, capabilities), and loaded / not loaded.
- FR-5 "Loaded" means the pack's Workspace exists on this Server and its sources answer; a pack that is described but not loaded is shown disabled with the reason.
- FR-6 Selecting a card selects the Workspace (Server session Workspace where shared, else sent with each request) and changes starters, upload options and workflow list together; one line says what changed.
- FR-7 "All data" is a distinct card with a visible accuracy warning (free-form accuracy across six packs was not measured).
- FR-8 The choice is remembered per user and set by `?pack=<id>`. The Server has no per-user preference store (see section 10), so the layer keeps a small preference table keyed by the Server username; `localStorage` is only a fallback.

### 3.3 Asking
- FR-9 A question box sends the question with the Workspace and optional attachments; shows progress while the Server plans and runs steps (the Server's own events), and a cancel control.
- FR-10 Shows the answer text, result table, and chart where the Server returns one, with the same value formatting rules as Ask for dates, money and large numbers.
- FR-11 An **evidence block** on every answer: Workspace used, whether the scope was enforced by Server or only applied by Agency (until Server#109), sources and tables touched, the SQL, whether the answer came from an approved question or was generated, and timing.
- FR-12 Follow-up questions keep the conversation; conversations are listed per user and per Workspace (Server conversations API).
- FR-13 Feedback (thumbs, with comment) and "ask an expert" are passed to the Server's feedback and help-request routes.
- FR-14 Export an answer as the Server's report (CSV/PDF where Server offers it); add to a dashboard where the Server's dashboard API allows.
- FR-15 Starter questions for the selected pack, marked approved or suggested, clickable.

### 3.4 Uploads and modalities
- FR-16 A drop zone accepts only types some enabled adapter handles; the list comes from the adapter catalogue, not a constant in the page.
- FR-17 Each upload becomes an **upload record** (id, name, kind, adapter, derived rows/vectors, licence note, owner, expiry). Records are private to the uploader unless sharing is on (FR-17a).
- FR-17a **Sharing within the group.** An admin setting `uploadSharing` (`off` default, `workspace`) lets an uploader share a record with the other members of the Workspace it was uploaded in; a shared record is read-only to them, shows who shared it and when, and can be unshared or deleted by its owner and by an admin. Only users with the Server's `canUploadFiles` grant can upload; sharing never extends a grant or a Workspace's access rules. Ask's own uploads are conversation-only and visible to no one else, so this is new behaviour in Agency, not a copy of an Ask setting.
- FR-18 After ingest the page offers "ask about this" prompts that name the upload record; the question and the derived data go to the Server like any other.
- FR-19 Audio: an identify action returning BirdNET top 3 restricted to the pack's species vs unaided, nearest recordings from vector search with spectrogram and player (reuses `demos/audio-demo`). Marked demo-only, non-commercial.
- FR-20 Image, document and table adapters follow the same contract. An adapter that is not enabled is not offered. Accuracy claims are shown only where measured (image-to-species vectors were 29%, so no accuracy language there).
- FR-21 Uploaded files are held only as long as the upload record says, are not logged, and are deleted on request.

### 3.5 Search
- FR-22 Vector and hybrid search over a pack's vector tables (for example `sounds.recording_embeddings`): audio to audio, text to audio, with SQL filters (licence, country) joined to metadata. Needs the pgvector extension in the schema the Server uses (`currentSchema`), or every vector query fails.
- FR-23 Text-to-vector needs an embedding service; where the Server has no such tool, Agency calls the adapter and says so in the evidence block.

### 3.6 Workflows and approvals
- FR-24 Rows carrying a workflow key (for example `payment_id`) show an action; starting a run needs the user's `canStartWorkflows` grant (commercial edition, Server v0.10.19+) or the Temporal demo in the free edition, both behind one contract.
- FR-25 A **queue** ("Waiting for me") and inline approval cards show facts, rules result, the AI recommendation (clamped to allowed actions) and the payload hash the approval is bound to.
- FR-26 Approve/reject sends the hash; a mismatch (409) tells the user the facts changed and reloads the card. Segregation of duties is enforced by the Server (initiator, AI and non-human identities cannot approve; dual approval over the limit). Agency shows the Server's refusal code in plain words and never hides a button's reason when disabled.
- FR-27 Dry-run is the default; a live write-back is a separate, labelled step and absent unless the deployment enables it.
- FR-28 The decision record is viewable and its hash chain verifiable in the page.

### 3.7 Claude as a front-end
- FR-29 Every operation above exists as a tool (ask, list packs, upload, search, list/start/approve workflow, read decisions) with the same inputs and the same access checks. Approving is never a tool a model can call on its own behalf: the human approval step stays in a human session.

### 3.8 Admin and status
- FR-30 A status page: Server reachable and version, edition, packs loaded, adapters enabled with their licence flags, workflow engine, thinking-layer version. Read-only.

## 4. Thinking-layer API (contract, first cut)

All calls carry the caller's credentials (cookie or bearer). JSON unless noted. Errors: `{ "error": { "code": "...", "message": "...", "detail": {} } }`, with the Server's own codes passed through where they exist.

| Call | Request | Response |
|---|---|---|
| `GET /packs` | | The catalogue entries plus `loaded`, `loadedReason` |
| `POST /ask` | `{ question, workspaceId, conversationId?, uploadIds?[] }` | `{ answer, columns, rows, chart?, sql?, evidence, conversationId }` (streams progress as server-sent events when `Accept: text/event-stream`) |
| `GET /adapters` | | `[{ id, accepts:[mime/ext], enabled, nonCommercial, notes }]` |
| `POST /uploads` | multipart file, `workspaceId` | upload record |
| `DELETE /uploads/{id}` | | `204` |
| `POST /search` | `{ workspaceId, mode: vector|hybrid, text? , uploadId?, filters?, limit }` | rows with distance and metadata |
| `GET /workflows/definitions` | | definitions the caller may start |
| `POST /workflows/start` | `{ definition, key, workspaceId }` | run |
| `GET /workflows/queue` | | runs awaiting the caller |
| `POST /workflows/{id}/approve` and `/reject` | `{ payloadHash, comment? }` | run, or refusal code |
| `GET /decisions` | `?runId=` | records plus `chainValid` |
| `GET /status` | | see FR-30 |

`evidence` = `{ workspace, scopeEnforcedBy: "server-backends"|"agency-hint"|"none", sources:[{id}], intendedSources, checks:[{id,status}], model, origin: "approved"|"generated", sql, steps, elapsedMs, warnings[] }`.

Adapter interface (each adapter its own container): `accepts(mime, ext)`, `ingest(file, context) -> { rows, vectors, notes, licence }`, `health()`.

## 5. Data held by the layer

Only: upload records and their expiry, per-user preferences, a cache of the pack catalogue. Answers, rows, conversations and decisions live in the Server (or, for workflow runs, the engine). No credentials are stored; no customer data is written to the layer's disk except uploads awaiting ingest, which are removed on expiry.

## 6. Security and edition

- Same-origin only with the Server through the layer's proxy or the ingress; no CORS opening on the Server.
- Content-Security-Policy and `frame-ancestors 'none'` like the Server; no inline credentials in URLs; `?pack=` carries an id only.
- Edition is read from the Server (not assumed): workflow API, adapters marked non-commercial and Qwen/BirdNET-style licence flags change what is offered.
- Cloud use: private ClusterIP by default, as the payment-workflow add-on; any public exposure is an opt-in setting with an allowed-addresses list.
- Threats to cover in review: prompt injection through uploaded documents and audio metadata (treated as data, never instructions), oversized or malformed uploads, SSRF through adapter URLs, approval replay (hash binding), role confusion between the AI identity and a human.

## 7. Non-functional

- Responsiveness: progress is visible within one second of sending; the layer adds no more than a small, measured overhead to a Server answer (to be measured; reference: Server answers took 12 to 87 s for the five supply-chain demo questions on the default AWS node).
- Accessibility: keyboard operable, labelled controls, contrast checked in light and dark.
- Footprint: the layer plus UI must fit beside the stack on the default node (the six-pack stack ran at 83% memory requests on the default AWS node, so the layer's own request is part of the acceptance test).
- Observability: request ids passed to the Server; the layer logs no question text or file content by default.

## 8. Acceptance tests

| Area | Test | Source of truth |
|---|---|---|
| Packs | catalogue matches `packs/catalogue.json`; unloaded packs disabled | `python3 scripts/packs.py check` plus a page test |
| Asking | all 24 approved Treasury questions word for word return the approved answer with `origin: approved` | reference SQL in the question files, as in earlier live checks |
| Scope | a Treasury-Workspace question cannot read `pg.bom.*` | needs Server#109; until then the evidence block must say `agency` |
| Workflows | the 27 checks of `demos/payment-workflow/tests/server-workflow-api.py` pass through Agency's API and hash-chain verification still validates | existing test, run via the layer |
| Free edition | workflow routes 404 become a clear "needs the commercial edition" message | v0.10.19 behaviour |
| Uploads | audio drop shows top 3 restricted vs unaided, nearest recordings; an unsupported type is refused before upload | `demos/audio-demo` fixtures |
| Security | approval with a stale hash gets 409 and the card reloads; the initiator's approve button is disabled with the reason | Server refusal codes |
| Claude | each tool returns what the page shows for the same input and the same user | tool contract tests |

## 9. Phases (each its own PR)

0. Licence file and terms for Agency (and the Docker repo), text from counsel.
1. Done: pack manifests, catalogue, Workspace config (Docker#197).
2. Layer skeleton: `/packs`, `/status`, `/ask` pass-through with the evidence block, `/decisions`, MCP tool list generated from the contract.
3. Agency UI slice 1 (React + Vite): pack cards, ask, evidence pane, conversations.
4. Adapters: audio moved behind the contract, then table, then document.
5. Workflows inline and queue; Docker compose service and cloud add-on chart entry (private).
6. Deploy-form pack multi-select on the four clouds; Server#109 to #111 adopted as they land.

## 10. Decisions (2026-11-17) and what is still open

Decided:
1. **UI stack: React + TypeScript + Vite**, the same toolchain as Ask (not Ask's code; see agency-design.md on licensing). The UI lives in the Docker repo under `agency/web`, is built in the layer's Dockerfile and served by the layer.
2. **Per-user store:** the Server has none that I could find: its per-user data is the session (login and chosen Workspace), `AppUserAccess` (three grants: see SQL, see sources, upload files), and conversations. No preference or settings route turned up in a code search (read, not run). So Agency keeps its own small preference table in the layer, keyed by Server username. A Server PR is optional later, if Kumar wants preferences shared by Ask and Agency.
3. **Own login:** Agency signs in to the Server itself (FR-1). Consequence: Ask and Agency do not share a Workspace unless both are reached on one origin through the ingress.
4. **Licence file:** Agency (and ideally the whole Docker repo) gets a LICENSE and a short terms note before any public release. The text is for counsel to choose; this spec does not pick it. Phase 0 below.
5. **Upload sharing within the Workspace's group**, controlled by an admin setting (FR-17a). Default `off`. Open: the default expiry of a shared record, and whether an admin can see all records or only shared ones.

Still open: the Server-side items filed as Server#109 to #111; counsel's answers on non-commercial adapters; whether the free edition limits the number of shared uploads.
