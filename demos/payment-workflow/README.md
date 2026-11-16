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

## Ask and the workflow in one page (the demo bridge)

The inbox page has an **Ask** box. A question goes to the app's real Ask API (the inbox backend signs in as the pack's demo user, `ASK_USER` / `ASK_PASSWORD`), and the answer comes back with its rows. When the rows have a `payment_id` column, each row gets a
**Workflow** cell: an "Analyse with AI" button, or the workflow's state, and the workflow's card (recommendation, rules, Approve / Reject) appears under the table. Each question also links to the same conversation in Ask (`ASK_PUBLIC_URL`, default http://localhost:8080).
Try: "Which waiting payments are on an invoice that is already paid?", then click Analyse on a row and approve from the card.

This is a bridge, not the product: Ask itself knows nothing about workflows (its own page has no action button or card, and it cannot be framed or called from a browser page of another origin, so the inbox backend makes the call). Building it into Ask needs a Server change: a workflow API, a result-row action and an inline card in the Ask web app.

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
