# Payment-exception workflow (AI recommends, a person approves)

A runnable example of the "AI decision workflow" in Server#75's design brief (`docs/design/ai-decision-workflows.md` in the Server repo), on the Treasury demo pack. **All data is invented.**
It is a spike to see how the flow reads and what it needs, not a product: the engine here is **Temporal**, running beside the stack and touching no Server code.

A payment waiting for approval is an exception when the invoice behind it is already Paid or On hold, the amounts differ, or it is above the dual-approval limit. For each one:

```
trigger (a payment is waiting for approval)
 -> governed facts       payment, policy, balance, invoice, PO, vendor history, agent notes: all read through thinking sense (POST /api/query), Postgres and the ERP
 -> rules gate           hard limits that hold whatever the AI says (rules.py)
 -> AI recommendation    release | hold | escalate, with reasons and a confidence; clamped to what the rules allow (recommend.py)
 -> human approval       one or two named people, each approving the hash of the exact action (workflows.py)
 -> write-back           dry-run by default: records the exact ERP call, sends nothing. WRITE_BACK=live sends it to the mock ERP, with an idempotency key
 -> decision record      append-only, hash-chained: inputs, rules, recommendation, approvers, action, outcome (decisions.py)
```

## Run it

From the repository root (the Treasury pack plus this add-on; tested with app release v0.10.18, set `OMNIGATE_RELEASE_TAG` to choose another):

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...      # the recommendation step uses it; without it a rule-based fallback answers, labelled "rules-only"
docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f demos/payment-workflow/docker-compose.workflow.yml up --build
```

- Approval inbox: http://localhost:8085 (type your name, e.g. `m.okafor`). Temporal UI: http://localhost:8233. Ask: http://localhost:8080 (`demo` / `demo`). Mock ERP calls: http://localhost:8086/calls
- `WRITE_BACK=live` sends approved actions to the mock ERP; the default `dry-run` shows the call it would send. `APPROVAL_TIMEOUT_MINUTES` (default 2880) is how long an approval may wait before the workflow escalates.
- Stop and wipe: `... down -v`. Tests: `python3 -m unittest discover -s demos/payment-workflow/tests` (26; the SAP write-back test runs only where the Temporal library is installed, e.g. `docker run --rm -v "$PWD/demos/payment-workflow":/app -w /app treasury-pack-worker python -m unittest discover -s tests`). Check the record: `python3 demos/payment-workflow/decisions.py verify` (with `DECISIONS_FILE` set).

## Behind the app's own workflow API (the gateway)

The app (v0.10.19 and later, **commercial edition only**) has a workflow API of its own: Ask and Agency start, approve and reject runs through it, and it talks to an engine over a small HTTP contract (`OMNIGATE_WORKFLOW_ENGINE=http://...`, documented in the Server repo's `docs/workflows-api.md`, "Engine gateway contract"). `gateway.py` is that engine in front of this Temporal workflow, so the same runs show up in Ask, in Agency and in the approval inbox (the Temporal workflow id is `payment-<id>` in all three: one payment, one run).

```bash
export WORKFLOW_GATEWAY_TOKEN=$(openssl rand -hex 24)      # shared secret between the app and the gateway; the gateway refuses to start without one
export OMNIGATE_RELEASE_TAG=v0.10.19
docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f demos/payment-workflow/docker-compose.workflow.yml \
               -f demos/payment-workflow/docker-compose.gateway.yml up --build
```

Then an admin grants `canStartWorkflows` to the people who may start runs and `canApprove` to those who approve (Admin > users). The app's manifest is `manifest.gateway.json` (one definition, `payment-exception`, key `payment_id`). The free edition ignores the setting and the routes do not exist.

- **What it does.** `POST /runs` starts the workflow (idempotent: the same payment returns the same run), `GET /runs/{id}` and `GET /runs?stage=awaiting_approval` read its state, `POST /runs/{id}/signal` delivers an approval or rejection. The app has already checked grants, the initiator, repeat approvals and the payload hash; the gateway re-checks them (a Temporal signal is fire-and-forget, so a bad one would be silently ignored) and answers with the app's own refusal codes. `gateway_map.py` holds the mapping and is unit-tested without Temporal.
- **Real recommendation, real facts.** The run's facts come through the app's governed query path, the rules gate and the recommendation (the model, or the rule-based fallback labelled `rules-only`) are this workflow's own; nothing is canned.
- **Stages.** The app's stages are facts, rules, recommendation, awaiting approval, approved, written back and rejected. The workflow can also end as `escalated` (the model chose "escalate": nothing is written) or `expired` (no decision before the deadline). The app has no stage for those, so the gateway reports them as `rejected` by the user `engine` with the reason spelled out. It reads a little oddly in the UI; a proper stage needs an app change.
- **Required approvals** come from this workflow's rules (one, or two above the dual-approval limit), not from the manifest's `requiredApprovals`, which is only informational.
- **Two decision records.** The app keeps its own hash-chained record of starts, approvals and refusals; this workflow keeps its own (`decisions.py`) of the decision's inputs and outcome. They are not merged.
- **A run started in the inbox** has no starter the app knows, so it shows "(started in the approval inbox)" and nobody is barred as initiator at the app level (the workflow still bars whoever initiated the payment itself, and the AI).
- **Security.** Bearer token on every route but `/health`, constant-time compare; no published port, so only the app reaches it. It can decide the fate of payments for anyone who reaches it: keep it on a private network. It does not hold admin rights itself, but the worker still reads the data with the app's admin token (the Server#102 limit above).
- **Not covered.** Only Treasury payments (not the SAP tab), dry-run write-back (live goes to the mock ERP), no sign-in on the inbox, not on the cloud charts yet. Tests: `python3 -m unittest discover -s demos/payment-workflow/tests` (47, no Temporal needed for the gateway's 21).

## On a cloud stack (an opt-in add-on, first slice)

The four stack charts can run this workflow as one extra pod beside the app. **Not yet on the deploy forms**: today it is a chart value, `paymentWorkflow.enabled=true` (with `demoDataset=treasury`), so it is for people who deploy the chart themselves or for the next step that adds the form switch.

- **What runs.** One pod with four containers: a Temporal dev server, the workflow worker, the approval inbox and the mock ERP, sharing a 1 Gi volume (Temporal's database and the decision record). Memory requests total about 450 Mi. The code is not in an image: it comes from a ConfigMap and runs on the stock `python:3.12-slim` image, and the Temporal SDK (`temporalio` 1.30.0) is installed from PyPI when the pod starts, so the cluster needs outbound access to PyPI.
- **Private.** The inbox has no sign-in (you type a name), so it is a ClusterIP Service and nothing outside the cluster reaches it. Open it with `kubectl port-forward svc/<release>-payment-workflow 8085:8085` and browse to http://localhost:8085. A network policy blocks all other inbound traffic to the pod (where the cluster enforces policies; `port-forward` is unaffected).
- **Free edition only, Treasury data only** (unless you use gateway mode below). A deployment that holds a signed licence renders nothing; any other data set than `treasury` stops the install with a clear message (all-packs is not supported yet).
- **Holds admin rights.** It reads the Treasury pack through the app's internal address with the admin API token, because the app has no narrower credential for reads yet (Server#102). That is the main reason it is private. The recommendation step uses the stack's model key; without one it falls back to the rule-based answer.
- **The Ask box and the SAP tab are off.** They need the Ask password, which the chart never holds. Nothing is written to a real ERP: an approved action shows the call it would send, or goes to the mock ERP in the pod.
- **Hardened like the app.** Non-root (uid 10001), read-only root filesystem, no capabilities, no privilege escalation, seccomp default.

**Keeping the four charts in step.** The charts hold copies. Edit the source in this folder, then run `scripts/sync-payment-workflow-addon.py` (it copies the Python files, the inbox page and `chart/payment-workflow.yaml` into each chart and adds the `paymentWorkflow` values); `--check` fails if any chart is out of date.

**Tested.** All 20 renders (4 charts x 5 data sets) are byte-identical to `main` with the add-on off, with the random passwords pinned; the add-on renders on all four charts; `helm lint` passes; and `tests/pod-smoke.sh` runs the four containers under the same security settings against a Treasury stack (SDK install, Temporal, worker, the inbox reading 7 payments through the app, a workflow started and approved, the decision chain intact). That script found one real failure: Temporal stops under uid 10001 unless `$USER` is set (the chart now sets it).
**Not tested.** A real cluster: probes, volume binding, the network policy, scheduling and the licence gate through the cluster's own licence Secret. The deploy-form switch and any public, signed-in access are not built.

### Gateway mode on a cloud stack (commercial edition)

For a deployment that holds a signed licence, the same pod can sit behind the app's own workflow API (see "Behind the app's own workflow API" above) instead of the inbox:

```bash
helm upgrade --install omnigate ./helm/omnigate --reuse-values \
  --set demoDataset=treasury --set paymentWorkflow.enabled=true --set paymentWorkflow.gateway.enabled=true
# then, once: restart the app so it picks the engine up  (kubectl rollout restart deployment/<release>-omnigate; the chart rolls it anyway when its settings change)
```

- **Needs** a signed licence (`omnigate.license`, or one installed with `scripts/set-licence.sh`) and `omnigate.adminApiToken`; the chart stops with a clear message without them, and without `paymentWorkflow.enabled`. The app decides its edition **when it starts**, so after a first licence activation the app must be restarted once.
- **What changes.** The pod runs Temporal, the worker, a **gateway** (port 8094) and the mock ERP; **there is no inbox** (it has no sign-in and the app's own sign-in replaces it). The app gets `OMNIGATE_WORKFLOW_ENGINE`, the token and a manifest ConfigMap (one definition, `payment-exception`). People then start, approve and reject runs in Ask or Agency, with their own grants.
- **Private by construction.** The gateway Service is a ClusterIP; the network policy (where the cluster enforces it) lets only the app's pods reach port 8094; every call needs a bearer token. The token is derived from `omnigate.adminApiToken` (stable across upgrades, different per deployment) unless you set `paymentWorkflow.gateway.token` (16+ characters). The gateway container does not get the admin token; the worker still does (Server#102).
- **Decision record.** The app keeps its own record in memory and mirrors every event to its audit log (`WORKFLOW_DECISION`); no decision file is set on the cloud stacks. The workflow's own record is on the pod's volume. They are not merged.
- **Several app replicas (OKE cluster mode)** share one Temporal, so runs are shared; each replica keeps its own in-memory decision record.
- **Changing the manifest** (a ConfigMap the app reads at start) needs an app restart.

**Tested.** The pod's containers (Temporal, worker, gateway, ERP mock) run under the chart's exact security settings beside a live app with `tests/pod-smoke-gateway.sh` (16 checks: token refused or short, start through the app, real facts, `missing_grant`, stale hash, an approval, a dry run, the decision record). `helm template` and `helm lint` pass on all four charts in gateway mode, every failure case gives its message, and all 20 default renders are unchanged. **Not tested:** a real cluster (probes, volume binding, the network policy, the Secret and ConfigMap wiring, pod scheduling), and the licence-to-commercial path: the only test licence on hand expired on 2026-10-17 and a new one cannot be signed here, so the tests emulated the edition with the app's own `OMNIGATE_EDITION` variable (which the chart does not set).

## Ask and the workflow in one page (the demo bridge)

The inbox page has an **Ask** box. A question goes to the app's real Ask API (the inbox backend signs in as the pack's demo user, `ASK_USER` / `ASK_PASSWORD`), and the answer comes back with its rows. When the rows have a `payment_id` column, each row gets a
**Workflow** cell: an "Analyse with AI" button, or the workflow's state, and the workflow's card (recommendation, rules, Approve / Reject) appears under the table. Each question also links to the same conversation in Ask (`ASK_PUBLIC_URL`, default http://localhost:8080).
Try: "Which waiting payments are on an invoice that is already paid?", then click Analyse on a row and approve from the card.

This is a bridge, not the product: Ask itself knows nothing about workflows (its own page has no action button or card, and it cannot be framed or called from a browser page of another origin, so the inbox backend makes the call). Building it into Ask needs a Server change: a workflow API, a result-row action and an inline card in the Ask web app.

## The Server's own workflow API (app v0.10.19 and later)

Since v0.10.19 the Server has a workflow API of its own (`docs/workflows-api.md` in the Server repository): approvals as the signed-in user, grants (`canStartWorkflows`, `canApprove`), refusals made by the Server before it signals an engine, a hash-chained decision record, and a Workflow column, approval card and "Waiting for me" queue in Ask. It is **off by default and commercial edition only** (on the free edition the routes answer 404), and today it runs on a built-in simulator whose recommendation and rules are canned text from a manifest. This folder's Temporal demo is a different thing: it runs real facts and a real model, but outside the Server. The Server documents a gateway contract (`OMNIGATE_WORKFLOW_ENGINE=https://gateway`) where an engine like this one could sit behind its API; that is not built.

`tests/server-workflow-api.py` is a black-box test of that API against a running stack (27 checks: access, start and idempotence, the stages, every approval refusal, rejection, write-back as a dry run, and the decision record, whose hash chain it recomputes from the file itself instead of trusting the Server's own verifier). To run it you need a commercial-edition stack with the local engine and the payment-exception manifest, and users alice (starts), bob and carol (approve), dave (no grants) and treasury-agent with the password `pw`; set `OMNIGATE_WORKFLOW_NONHUMAN_USERS=treasury-agent` or its non-human check fails, because the Server only knows a short list of reserved names (`ai`, `agent`, `bot`, `service`, `system`, `recommender`, `machine`) by default. `OMNIGATE_APP_USERS` separates users with `;`, not `,`.

## The same workflow on SAP data

The inbox has a **Source** switch: **SAP blocked invoices** runs the same flow on the supplier invoices that carry a payment block in SAP's public API sandbox (S/4HANA Cloud sample data, read-only; see `../sap-spike`). It needs the SAP spike app running (`demos/sap-spike/run.sh`, Ask on :8087, with the Server REST-source changes) and your sandbox key:

```bash
export SAP_API_KEY=$(sed -n 's/^SAP_API_KEY=//p' demos/sap-spike/.env)      # then start the stack as above; SAP_ASK_URL defaults to the spike app on the host
```

What it does: the inbox lists the 46 blocked invoices (SAP applies the filter, so the list is complete). "Analyse with AI" gathers the invoice header (including SAP's own payment and approval status), a server-side check for **other invoices from the same supplier with the same gross amount**, and the supplier's blocked and fiscal-year counts; a rules gate (`sap_rules.py`) removes "release" when the invoice looks like a duplicate, is reversed, or SAP already shows it Cleared; the model recommends **release** (the block), **hold** (keep it) or **escalate**; people approve with the same hash-bound, two-approver rules; the decision record gets a `source` of `sap`.
The Ask box on that tab asks the SAP spike app, and rows with a `SupplierInvoice` column get the same Workflow cell and inline card.

What it found on the real data (tried 2026-11-16, Claude Sonnet 4.5):
- 11 of the 46 blocked invoices have a same-supplier, same-amount twin (5100044197 and 5100044226 are both 197,208.00). Both the rule and the model said hold.
- 45 of the 46 are from one supplier (USSU-VSF12): the model recommended hold on the large ones, citing a common cause to find first.
- Invoice 5100043603 shows payment status **Cleared** while the block is still set: the model escalated it as a contradiction, which became a hard rule.
- A model reason was loose: it read SAP's own approval-workflow status ("Workflow not yet started") as if it were this workflow.

Limits, stated plainly:
- **The facts are not governed.** They are read from SAP's API directly, because the app's `/api/query` cannot run against a REST source (only Ask's own path can); there is no access policy or audit log on these reads (noted for Server#102).
- **Nothing is written.** SAP's invoice service has `Post`, `Release` and `Cancel` actions and no "hold"; "hold" writes nothing, and "release" only shows the call (`Release?SupplierInvoice=...&FiscalYear=...`, which would also need a CSRF token and a user allowed to release blocks). The public sandbox is read-only, so SAP actions are never sent, whatever `WRITE_BACK` says.
- The invoice header has **no creator**, so the initiator cannot be excluded as an approver as the Treasury payment's is; the thresholds (50,000 and 250,000 USD) and the GBP and EUR rates are demo constants, not SAP data.
- No purchase-order match (the link sits on the invoice items), no real tenant, no OAuth or basic auth.

## Try this (the pack's seven pending payments)

| Payment | What is wrong | What to expect |
|---|---|---|
| 29 | nothing; above the auto-release limit | AI: release. One approver. |
| 34 | invoice already **Paid** | Rules remove "release" (duplicate payment). AI: hold. |
| 30 | invoice **Paid** and above the dual-approval limit | AI: hold. Needs two different approvers. |
| 35 | invoice **On hold**, USD 520,000 | AI: hold. Needs two approvers; reject it to see a rejection recorded. |
| 31, 33 | above the dual-approval limit, otherwise clean | Release needs two approvers. |
| 32 | agent-initiated, just under the dual limit | One approver. |

Click "Analyse with AI", then approve as one name. Then try to break it (the inbox ignores these and says why): approve with the initiator's name, with `treasury-agent`, twice as the same person, or a stale hash (POST `/api/decide` with a wrong `hash`).
Restart the worker (`docker compose restart worker`) while payments wait: the workflows carry on, which is what the durable engine is for.

## What it implements from the brief's controls

| Control | Here |
|---|---|
| 3 approval bound to the payload hash | Yes. A signal with another hash is ignored and logged. |
| 4 segregation of duties | Yes. The initiator and the AI/automation names cannot approve; the same person counts once. |
| 5 rules before AI | Yes. The model's choice is clamped to the rules' allowed actions; a blocked choice becomes "escalate". |
| 6 untrusted input is data | Partly: invoice and agent text goes to the model inside a marked data block with an instruction not to follow it. Not tested against a real injection attempt. |
| 7 idempotency | Yes for retries: the workflow id is the idempotency key and the mock ERP replays a repeated key. No defined reversal yet. |
| 8 dry run | Yes, and it is the default. |
| 10 audit record | Yes: hash-chained file; a real deployment exports it to the customer's log store. |
| 1 identity, 2 least privilege, 9 kill switch, 11-13 | Not built. The inbox takes a typed name; the ERP call uses no credential. |

## What we learned

- **Facts through thinking sense work, with one catch.** A single statement that joins Postgres and the ERP comes back **without its `AS` aliases and with duplicate column names** (`status`, `amount` twice); the same statement on one source keeps them. This example reads each system separately and merges in code. Worth a Server issue.
- **The rules matter more than the model.** Rule-based and model recommendations agreed on the four payments compared (29, 30, 34, 35); what the model added is the reasons and the "to check" list. Some of its reasons are loose (a "days past due" claim that does not follow from the dates, an "only 1 approval pathway" remark), which is why a person approves and why the rules, not the model, decide what is possible.
- **Temporal footprint:** one dev-server container, a Python worker and the inbox. The workflow file reads close to the brief's diagram. Not measured: the Flowable side of the comparison, a production Temporal deployment (the dev server here keeps a single SQLite file), memory per SMB.
- Not covered: credit holds, ServiceNow/SAP/Fusion connectors (the mock ERP stands in), AppDynamics, multi-tenant, and the partner's security questionnaire.
