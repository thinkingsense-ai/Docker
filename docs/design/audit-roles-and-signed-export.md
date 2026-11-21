# Audit roles and a signed decision-record export: design note for the Server (draft)

Status: draft for Kumar, written 2026-11-21 with step 8g of `docs/agency-risk-register-plan.md`. **Nothing here is built in the Server.** I did not read the Server code for this note beyond `docs/workflows-api.md` (decision file, hash chain, audit-log mirror) and what Agency already uses (`/app/whoami`, the grants `canStartWorkflows`, `canApprove`, `canUploadFiles`, `GET /app/workflows/runs/{id}/decisions`). Treat every statement about the Server as unchecked and correct it.

## What exists on the Agency side now (step 8g)

- The worker keeps its own hash-chained decision record, one JSON line per finished run, `{"prev", "body", "hash"}` with `hash = sha256(prev + json(body, sorted keys))` (`demos/payment-workflow/decisions.py`). The body holds the facts the run read, the rules result, the recommendation, who approved, the action and its write-back.
- The thinking layer reads that file **read-only** and serves it to the people on `AGENCY_AUDIT_USERS` only: `GET /audit/records` (filters: workflow, person, outcome, control, run, from, to; the verdict on the whole chain; the head hash) and `GET /audit/export` (JSON lines). Every read is logged (user, route, filters) to the layer's output. It is **not** an MCP tool.
- The Agency Audit screen shows the list, the chain verdict, and a check of the decision record against the risk register (each run that says it wrote a row must find that row, with the same run and evidence digest, and each workflow-written row must have an entry).
- An export is a header line (filters, entry count, the chain verdict at export time, the chain head, whether the selection is contiguous, `signature: null`) and the entries exactly as stored.

## What is missing, and why it cannot be fixed in Agency

1. **There is no read-only audit grant.** The layer's list is a convenience. A person on it is trusted by the layer, not by the Server; anyone who can edit the layer's environment can add themselves. The third line of defence (audit) cannot be a role the Server enforces today.
2. **An export is not signed.** The chain proves that a line was not changed, deleted or reordered *relative to the file*. It does not prove that the file is the one the operator held: whoever can write the file can rebuild a consistent chain. Only a key the layer does not hold (the Server's) can make a statement an auditor can check against something outside the file.
3. **The worker's record and the Server's record are two chains.** The Server keeps its own (`GET /app/workflows/runs/{id}/decisions`, mirrored to its audit log). The worker's holds the facts and the rules; the Server's holds who did what through its API. An auditor wants both and wants to know they agree.

## Proposal

### S1: a read-only audit grant
A fourth grant, `canAudit` (name open), that lets a signed-in person read the decision records and the registers and **nothing else**: no start, no approve, no upload, no admin console. It should show in `/app/whoami` next to the others, so Agency can show the third line from the Server's own answer instead of inferring "read only" from having neither of the others. If the Server prefers roles to grants, the three lines (first: start, second: approve, third: audit) as named roles would do the same.

### S2: a signed export
`GET /app/audit/export?control=&run=&actor=&from=&to=&definition=&outcome=` returning JSON lines:

1. a **manifest** line: the filters, the entry count, the chain head of the whole record, the verdict on the whole chain, the Server's key id and the time;
2. the **entries** as stored, with their sequence numbers;
3. a **detached signature** over the manifest line and the entry hashes (Ed25519 or the deployment's existing signing key), in a trailer line or a second file.

The signature should cover the chain head, so a selection (not the whole record) still proves it belongs to a chain the Server vouched for. A verifier needs only the entries, the manifest and the Server's public key. The Server should be the one place that combines its own chain and the worker's (the worker can post its record to the Server on completion, or the Server can read the shared file), so an export carries both and says whether they agree.
Agency would then stop describing its own export as "not signed" and would offer the Server's.

### S3: history from ServiceNow and Datadog (a question, not a request)
A Server connector reads current state and keeps no history. The estate fields in `demos/it-risk-estate` are stored as of a date. If a real tenant is connected, a small snapshot job (hourly) into Postgres, read as SQL like the feed, would give the register something to compare against. Is there a plan for history in the connectors?

### S4: Server#139
Window functions with `PARTITION BY` fail on some Postgres tables (`AssertionError ... LogicalWindow ... does not implement JdbcRel`). Ranking queries ("latest rating per item", "top N per group") are the case it blocks for the register and Priorities; Agency avoids them with joins to a `MAX` and ranks in code. Link it from Server#138.

## Questions for Kumar
1. Is a fourth grant (or the three named roles) acceptable, and should it also cover the admin console's read-only views?
2. Where should the signing key live, and is a detached Ed25519 signature acceptable to a bank's audit team, or does it want X.509 or an HSM?
3. Should the worker post its record to the Server, or should the Server read the shared file?
4. Should an export be limited by the same Workspace scope as the question that created the run (Server#109 makes that coarse today)?
5. Retention: how long does the Server keep the record, and can an operator export and archive it?

## Not in this note
A full audit programme (sampling, evidence retention policy, segregation of the person who runs the export), a real key management design, and any change to how the worker writes its record.
