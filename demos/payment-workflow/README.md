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
- Stop and wipe: `... down -v`. Tests (no Docker): `python3 -m unittest discover -s demos/payment-workflow/tests`. Check the record: `python3 demos/payment-workflow/decisions.py verify` (with `DECISIONS_FILE` set).

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
