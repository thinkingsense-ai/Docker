# IT-risk register vocabulary (schema `register`)

Step 8a of `docs/agency-risk-register-plan.md`. Three tables the screens and approved questions read:

- `taxonomy`: the category tree, L1 to L3 (34 rows), each with the nearest NIST CSF 2.0 category, ITIL 4 practice and CIS Controls v8 control. `status` says whether a category came from the meeting notes, from a public example, or is our proposal. **The framework mapping is ours, from general knowledge, not checked clause by clause.**
- `rating_scale`: Low, Medium, High, Critical. The one scale on every screen (`agency/web/src/rating.ts`; the Python port of the exposure rating uses the same four words).
- `definitions`: the words the screens use (event under review, problem record, loss event, inherent and residual risk, TRP, BRP, material) with where each comes from and whether it is given, ours, not confirmed or deferred.

Step 8b adds the register itself:

- `assessments`: **the risk register**. One row per approved rating, appended and never edited: item, category, rating, likelihood and impact bands with their inputs, control evidence, who set it (second line), when, the workflow run and the digest of the evidence approved. A trigger refuses UPDATE, DELETE and TRUNCATE (a superuser can still bypass triggers, so this is a guard, not a vault). `inherent` is always true: residual risk is never computed here; the second line judges it from the control evidence. The current rating of an item is its newest row.
- `register_writer`: the role the worker will use in step 8d. It may only INSERT. Attribution is meant to come from the Server's decision record for the approval, not from a field a service fills in. Until 8d nothing writes the register but the seed: the three rows are INVENTED examples (`source = 'seed-example'`, no run behind them) and a CHECK requires a run and a digest on every other row.
- `item_categories`: the category of each seeded incident and watched story, from the cause the operator stated (no stated cause: the category stops at the family). `claim_type_category`: a PROVISIONAL category for a feed story nobody has traced, from what it claims; it is replaced once a person traces it. Both are ours, to be confirmed.

Three more approved questions (current rating of each item, the rating history of the November case, the category of each November incident). The current-rating query uses a join to a MAX, not a window function (Server#139).

Everything is read-only for the app user.

## Run it

`agency/local/up.sh` adds it to the sandbox stack and merges `demo-questions-register.json` into the question seeder. Postgres runs init files only on a fresh volume. To add it to a running sandbox without wiping:

```bash
docker exec -i agency-risk-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q < demos/it-risk-register/seed-register-postgres.sql
docker exec -i agency-risk-postgres-1 psql -U postgres -d postgres -q < demos/it-risk-register/grant-register.sql
```

then tell the Server about the new schema. **Send `enabled: true` and the whole list**: a body without `enabled` turns schema discovery off (found by doing it):

```bash
curl -X PUT localhost:8080/api/config/schema-discovery -H "Authorization: Bearer $AGENCY_ADMIN_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"enabled":true,"include":"suppliers,inventory,procurement,risk,smithsonian,security,museums,bom,treasury,erp,rca,estate,register","exclude":""}'
```

Verified 2026-11-21 against the sandbox: a schema created while the Server was running was queryable through `/api/query` after that call, and the three reference queries return 33, 4 and 13 rows. Not in the cloud charts.

## Writing the register: the risk-assessment workflow (step 8d)

`demos/payment-workflow` has a fourth workflow definition, `risk-assessment` (run id `assess-<system_id>`), the only way a rating gets into `register.assessments`:

1. **Propose (first line).** Someone with the start grant sends one system from the Priorities screen. The run reads that system's estate row (the same SQL as the Priorities question, one system), the register's current rating for it and the exposure rating of the case, then proposes the rating the Priorities rules give (`priority_rules.py`, the same module the screen's port is tested against), a category (the finding that drives the likelihood; ours, to be confirmed) and the **control evidence** as plain text built from the row.
2. **Approve (second line).** A person with the approve grant records it or sends it back with a reason. The initiator and AI or service identities cannot approve; a stale hash is refused; **a Critical rating needs two different people** (a demo constant, as for the kill switch). The approval is bound to a digest of the exact row, exposure rating, rating, category and evidence.
3. **Record.** The worker adds ONE row as `register_writer` (INSERT only; the table refuses UPDATE, DELETE and TRUNCATE). `set_by` is the approvers the Server's workflow API delivered, `role` is `second`, `run_id` and `evidence_digest` point back at the run, and a unique index on `run_id` means a retried write adds nothing twice. Earlier ratings stay: the current one is the newest row. A hold or a send-back adds nothing. `REGISTER_WRITE=dry-run` records the exact row without adding it.
4. **Record of the decision.** The usual hash-chained decision record.

Roles on screen are inferred from the grants (start = first line, approve = second line, neither = read only, the third line); a read-only audit grant does not exist in the Server yet. The recommendation is from the rules alone (`rules-only`); no model drafts anything. Limits: one run per system ever (as with the other definitions), so a second assessment of the same system needs a new run id (not built); the treatment decision (accept, mitigate, transfer, avoid) is not part of this run; the cloud charts do not carry the register or this definition.

The worker needs `psql` (the image now installs `postgresql-client`) and `REGISTER_DB_HOST`, `REGISTER_DB_PASSWORD` (and optionally `_USER`, `_NAME`, `_PORT`); the local sandbox sets them in `agency/local/docker-compose.risk-gateway.yml`. After changing the manifest, restart the app. Existing stacks need the register schema reloaded (run `grant-register.sql` AFTER every reload) and the changed Priorities question replaced in the question bank (the seeder skips a question whose text is already there: delete the old entry with `POST /api/question-bank/delete`, then re-run the seed container).

## Notification clocks (step 8e)

What a regulator asks for after a **major** incident, and when. The clocks exist only once a **person has recorded the decision that an incident is major**; no rule infers it, and "material" (bad press) is not decided at all (Leo deferred its test). **Nothing is ever sent to any regulator.**

- `notification_rules`: DORA (initial notification within 4 hours of classification and no later than 24 hours after awareness, whichever comes first; intermediate report 72 hours after the initial one; final report one month, here 30 days, after the intermediate) and MAS (notify within 1 hour; root-cause report within 14 days). **Our reading of public summaries, checked in SECONDARY sources on 2026-11-21 and not against the regulations**; where a start event is unconfirmed (MAS) the row says so. Which MAS notice applies depends on the entity type.
- `firm_profile`: which regulators the firm declared. A person declares applicability; the product never works it out. Invented for the simulated firm (an EU and a Singapore entity).
- `firm_incidents`: three INVENTED incidents of the simulated firm (not the real November outages of real companies), each with when the firm became aware.
- `major_incident_decisions`: the recorded decision. Append-only like the register (trigger refuses UPDATE, DELETE, TRUNCATE), one per incident, written only by the worker as `register_writer` after an approval. A person who decides an incident is NOT major records nothing and no clock starts.

**Workflow `major-incident`** (run id `major-<incident_id>`, `demos/payment-workflow/major_*.py`): a first-line person proposes, a second-line person records it or says "not major". No recommendation step on purpose: approving IS the decision. The initiator and AI identities cannot approve; the approval is bound to a digest of the incident, the declared regulators and the rules in force. The card previews the clocks the decision would start. `classified_at` is when the approval completed, which is when the clocks start.

**Clock rules** (`clock_rules.py`, twin `agency/web/src/clockModel.ts`, shared hand-worked gold set `clocks_gold.json`, 9 cases): each rule counts hours from `classified`, `awareness` or `previous_report`; the later DORA stages are the **latest possible** times, assuming each earlier report goes at its own deadline (nothing is sent here, so the real send time is unknown); a rule's second limit makes the earlier of the two apply; a deadline already past when the decision was recorded is flagged; only declared regulators get clocks; no decision means no clock. Timestamps are UTC: the Server returns them without a zone, so they are read as UTC (true while the Postgres session is UTC).

Agency has a **Notifications** screen: two approved questions, the incidents with their status, the clocks with time left or overdue, a "Send for a major-incident decision" button and the run card. After reloading the schema run `grant-register.sql`, replace nothing (the two questions are new), restart the app after the manifest change, and rebuild the worker image.
