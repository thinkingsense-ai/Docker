# Agency web (phase 3, slice 1)

React 19 + TypeScript + Vite, written fresh (not copied from Ask). It talks only to the thinking layer ([addons/thinking-layer](../../addons/thinking-layer/README.md)), which serves the built files on the same origin, so there is no CORS and the Server's cookie never reaches the browser.

What it does: sign in with the Server's business-user login; pack cards from the catalogue (All data first, with an accuracy warning; a pack the layer knows is not loaded is disabled with the reason; "load state unknown" when the Server cannot say); choice remembered per user (`?pack=`, then the layer's preference, then `localStorage`); starter questions marked approved or suggested; ask with the Server's progress steps and a cancel button; answer text, a result table (thousands separators, readable dates, numeric columns right-aligned); an **evidence pane** on every answer (Workspace, who enforced the scope, approved or generated, sources, checks, time, SQL when the user may see it, warnings); follow-up questions in the same conversation; the user's conversations (list, reopen).

Not in this slice: feedback, report export, dashboards, a status page, uploads, workflows, charts (see docs/agency-spec.md phases 4 to 6). A reopened conversation shows saved text and rows only; the Server keeps no evidence for it. The Server lists conversations per user, so they are not filtered by domain.

```bash
cd agency/web && npm ci
npm run dev        # http://localhost:5173, proxies the layer routes to LAYER_URL (default http://localhost:8097)
npm test           # formatting and badge helpers (vitest)
npm run build      # type check and build to dist/
```

Whole thing in Docker (UI built in the layer image), beside a pack stack, from the repository root:

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...
docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f addons/thinking-layer/docker-compose.layer.yml up --build
```

Then open http://localhost:8097 and sign in with the pack's demo account.
