# Agency: a second front-end and a thinking layer (design note)

Status: proposal for review, nothing built yet. Written 2026-11-17.

## Why

The Ask app (React, `Server/web`, 2,813 lines in `pages/Ask.tsx`; back-end `com.omnigate.http.ask`, `AskRoute.java` alone is 8,265 lines) is
Kumar's and lives in the private Server repo. Every new kind of input (audio, images, documents) or screen (workflows, evidence, pack choice)
currently needs a Server change before it can be shown. We want to show what the platform can do with those inputs without waiting on a Server
release for each one, and without forking the part of Ask that is hard to get right.

## What we are not doing

- We do not copy `AskRoute` or the planning, join, ontology, question-bank or approval logic. That is the product; a fork would drift and would
  put private code in a public repo.
- We do not copy `Ask.tsx` into this repo. The Server repo has no licence file (see the licence register), so copying its code into a public
  repo is a question for counsel. Agency is written fresh; it borrows behaviour (what the product does), not source.

## Shape

```
Claude (MCP / chat) -+
Agency (new UI)     -+--> Thinking layer API --> OmniGate Server (/app/*, /api/query, /mcp)
Ask (existing)      -+         |
                               +-- modality adapters (audio, image, document, file)
                               +-- vector search (pgvector)
                               +-- workflow engine (Temporal, Server's gateway contract)
                               +-- decision and audit record
```

Three layers, each usable without the one above it:

1. **Server (unchanged).** Answers questions, enforces access, owns the data and the ontology. Agency is a client of the released image, the same way
   `demos/payment-workflow` is. Gaps become Server issues or PRs for Kumar, not local patches.
2. **Thinking layer (new, `Docker/addons/thinking-layer`).** One small HTTP service with a stable contract. It holds everything that is about
   *what to do with an input before or after Server answers*. It is the only thing that talks to Server on behalf of Agency and Claude.
3. **Front-ends.** Agency (browser), Ask (as is), and Claude through MCP tools generated from the same contract.

### Thinking layer contract (first cut)

| Call | Purpose |
|---|---|
| `GET /packs` | The pack catalogue (see "Pack selection" below) |
| `POST /ask` | Question + pack scope + optional attachments; returns answer, rows, SQL, sources, and an `evidence` block |
| `POST /uploads` | Accepts a file, picks an adapter by type, returns an `upload` record (id, kind, derived rows or vectors, licence note) |
| `POST /search` | Vector or hybrid search (text-to-vector and audio-to-vector through the adapters) |
| `POST /workflows/start`, `GET /workflows/queue`, `POST /workflows/{id}/approve` | Pass-through to Server's workflow API (v0.10.19, commercial) or to the local Temporal demo for the free edition |
| `GET /decisions` | The decision record, verifiable (hash chain) |

Auth: the caller's Server session or bearer token is forwarded; the layer stores no credentials of its own and never widens access.

### Modality adapters

An adapter turns an upload into something Server can already answer questions about: rows in a source and, where it helps, vectors in
pgvector. Interface: `accepts(mime, ext) -> bool`, `ingest(file, context) -> {rows, vectors, notes, licence}`.

| Adapter | Today | Notes |
|---|---|---|
| audio | `demos/audio-demo` (BirdNET top 3 restricted to the pack species vs unaided, CLAP nearest recordings) | Non-commercial models and data: demo only until counsel signs off |
| image | CLIP spectrogram embeddings (29% nearest-neighbour, no gain over audio) | Needs an image model suited to the data; do not present as accurate |
| document | not built | PDF/Office to text chunks + table extraction into a source |
| table | not built | CSV/XLSX into a scratch schema, read-only to everyone but the uploader |

Adapters run in their own containers (the heavy dependencies stay out of the layer) and are listed in the catalogue, so the UI only offers
an upload type that something can handle.

## Pack selection (a better design)

Today (as far as I read it): packs are not a first-class thing. The Ask picker only appears when the approved questions carry two or more
distinct `category` values, it is built from those categories, a click only changes which *starter questions* are shown, and the choice sits in
browser `localStorage`. Nothing tells the person what a pack contains, whether it is loaded, or what asking "in" a pack means for the answer.
At deploy time the choice is a flat five-way dropdown (`demoDataset`: supply-chain, it-risk, bom, treasury, all-packs).

Proposal: a pack is a described, scoped, versioned thing.

### 1. A pack manifest

Each pack ships `pack.json` next to its seed (the numbers below are illustrative, not measured; phase 1 fills them from the real seeds):

```json
{
  "id": "treasury",
  "title": "Treasury",
  "summary": "Cash, payables, hedges, debt and an agent action log.",
  "version": "2026-11-13",
  "sources": [{"id": "pg", "schemas": ["treasury"]}, {"id": "mdb", "schemas": ["erp"]}],
  "tables": 31,
  "questions": {"approved": 24, "crossSource": 4},
  "modalities": ["table"],
  "needs": {"embeddingModel": true, "memoryMi": 600},
  "capabilities": ["workflow:payment-exceptions"],
  "licence": {"data": "synthetic", "commercialUse": true},
  "editions": ["free", "commercial"]
}
```

The catalogue is the union of installed manifests. It is the single source for the deploy form, the UI picker and the Claude tool list, so
the three can no longer disagree.

### 2. A pack is a Workspace

Server already has the right construct: a **Workspace** (`Namespace`, `OMNIGATE_NAMESPACE_CONFIG`). Every question is asked in exactly one Workspace
(`AskRoute` refuses a question without one), and a Workspace carries a name, a set of backends, an access rule (roles, attributes, members), its own
LLM settings and an MCP-server allowlist. The Ask app has a Workspace dropdown, but today it is barely used: a stack has only the computed
`default` Workspace, so the dropdown offers nothing, while the *pack* picker is a separate control that only reorders starter questions. Two
controls, one of them inert.

Proposal: **one concept, the Workspace, is the pack.** Each pack manifest generates a Workspace entry (id = pack id, name = title, the pack's
backends, access from the manifest) and the picker is the Workspace selector. Choosing "Treasury" then really tells Server the domain of the
question: which data the planner may see, who may use it, and which model settings apply. `All data` is the computed default Workspace.
Agency sends the Workspace id with every `POST /ask` and shows it in the evidence block ("answered in: Treasury").

What Server does and does not do today (read from `Namespace`, `NamespaceStore`, `NamespaceConfig`; not yet exercised with packs):

| Need | Today | Gap |
|---|---|---|
| Limit the planner to a pack's data | Workspace scopes by **backend** (data source) only | Packs share one connector (`pg`) with auto-discovered schemas, so a backend list cannot separate supply chain from Treasury. Needs `backend.schema` entries in a Workspace (Server PR), or one backend per pack, which the free edition's three data sources forbids |
| Pick the pack's approved questions | Starter questions already follow the session's Workspace (`AppQuestionBankRoutes.starterQuestions` shows an approved question only when its SQL names a table in the Workspace's catalogue), so they inherit the Workspace's granularity: backend only. The pack picker's grouping is by `category`. Whether answer-time retrieval is filtered the same way was not traced | Schema-level Workspaces (Server#109) fix the granularity; retrieval to be confirmed with Kumar (Server#110) |
| Pack-specific description for the planner | Not in Workspace | Domain text per Workspace (Server PR; today only database comments reach the SQL prompt) |
| Access per pack | Workspace `access` (roles, attributes, members) | Already there |
| MCP tools per pack | `mcpServerIds` recorded, **not enforced** in Ask | Enforcement (Server) |

Until the Server changes land, Agency narrows the question itself (adds the pack's schemas and domain text to the request and says "scope applied by
Agency, not enforced by Server" in the evidence block), so the design works as a demo and tightens when Server enforces it.

### 3. A picker that explains itself

- Always shown when two or more packs are installed (not only when categories happen to differ), as cards with title, one line, size
  ("24 approved questions, 2 sources"), badges (free / commercial, non-commercial data, needs embedding model), and a "loaded / not loaded" state.
- Selecting a card selects the Workspace and changes the starter questions, the upload targets and the workflow list together, and says so in one line.
- A first-class **All data** card, with a visible warning about accuracy across packs (measured: free-form answers across six packs were not
  benchmarked).
- The choice is remembered per user on the server (thinking-layer preference), with `localStorage` only as a fallback; deep links carry
  `?pack=treasury`.

### 4. Deploy-time selection

On the four cloud forms, replace the single dropdown with a **multi-select of packs** driven by the manifests: each option shows size,
memory need and edition badge; incompatible combinations are blocked with the reason (free edition: 3 data sources; memory tight at six packs on
a default node, 83% of requests measured); the form's `demoDataset` value becomes a list. Back-compat: a single value still works and
`all-packs` expands to the list. A later step lets an operator add or remove a pack on a running stack (re-seed that pack only), which
is not possible today because the choice is "fresh install only".

## Serving Ask and Agency together

Server serves one web app: `SpaResourceHandler` serves the folder named by `OMNIGATE_WEB_DIST_DIR` at `/`, and any path it does not recognise falls
back to Ask's `index.html`. Paths starting `/api/`, `/app/`, `/auth/`, `/scim/`, `/mcp`, `/metrics`, `/console`, `/logout` and `/admin/login` are left to
Server's own routes. There is no setting for a second app at a prefix, so Server alone cannot serve Agency today.

| Option | How | Server change | Workspace shared between the apps |
|---|---|---|---|
| 1. Sibling container with its own proxy (start here) | The Agency service serves its UI and forwards `/app/*` and `/api/*` to Server; one extra compose service and port | None | No: Agency signs in on its own, so each app keeps its own Workspace |
| 2. One URL through the ingress or load balancer | Ask on `/`, Agency on `/agency`; Server's own paths go to Server | None | Yes, when both reach Server on the same origin (one login cookie; the Workspace lives in the session) |
| 3. Server serves both | A second dist folder and mount prefix, for example `OMNIGATE_EXTRA_WEB=/agency=/opt/agency` | Yes (PR for Kumar) | Yes |

Plan: option 1 for the demo and the compose files, option 2 as a path rule on the four cloud load balancers if wanted, and a Server issue for option 3
so customers get one container and one port later. Because packs are generated Workspaces (above), Ask's existing Workspace dropdown shows them
with no Ask change, so Ask users benefit as soon as the manifests generate the config.

## Agency UI, first slice

A single front-end, no build step to start (as the audio demo), served by the layer:

1. Ask-style question box with the pack cards above and an evidence pane (SQL, sources, scope, decision record).
2. Drop zone: audio or image or document, routed by the catalogue to an adapter, then "ask about this" buttons.
3. Inline workflow card and approvals queue (replaces the separate inbox page).

Decision on stack (plain HTML + small JS vs React + Vite) is open; the contract above does not depend on it.

## Open points and risks

- **Licensing.** Agency code is ours. Demo data and models in the audio and image adapters are non-commercial; those adapters stay Docker-only
  and badged until counsel answers the register's questions. The workflow part (Temporal MIT, invented data) is the low-risk candidate for cloud.
- **Server gaps this will expose** (to file for Kumar as they appear): governed SQL against REST sources (Server#102), a text-to-vector tool
  (Server#95), `backend.schema` entries and domain text in a Workspace, question-bank retrieval that follows the Workspace, enforcement of `mcpServerIds`, and an accepted upload type for adapter output.
- **Edition.** The workflow API is commercial only; in the free edition Agency uses the Temporal demo behind the same contract.
- **Not measured.** Accuracy of free-form questions under pack scope versus all data; the scope narrowing is expected to help, not shown.

## Proposed phases (each its own PR)

1. Pack manifests for the five existing packs + catalogue endpoint + generated Workspace config (no behaviour change; byte-identical charts) and a Server issue/PR for schema-level Workspaces.
2. Thinking layer skeleton: `/packs`, `/ask` (pass-through with scope), `/decisions`; MCP tool list generated from the contract.
3. Agency UI first slice (questions, pack cards, evidence).
4. Upload adapters: audio (existing demo moved behind the contract), then table and document.
5. Workflows inline; deploy-form multi-select for packs on the four clouds (docs-site and stack releases follow the normal release procedure).
