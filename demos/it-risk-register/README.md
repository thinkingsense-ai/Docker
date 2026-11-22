# IT-risk register vocabulary (schema `register`)

Step 8a of `docs/agency-risk-register-plan.md`. Three tables the screens and approved questions read:

- `taxonomy`: the category tree, L1 to L3 (34 rows), each with the nearest NIST CSF 2.0 category, ITIL 4 practice and CIS Controls v8 control. `status` says whether a category came from the meeting notes, from a public example, or is our proposal. **The framework mapping is ours, from general knowledge, not checked clause by clause.**
- `rating_scale`: Low, Medium, High, Critical. The one scale on every screen (`agency/web/src/rating.ts`; the Python port of the exposure rating uses the same four words).
- `definitions`: the words the screens use (event under review, problem record, loss event, inherent and residual risk, TRP, BRP, material) with where each comes from and whether it is given, ours, not confirmed or deferred.

Later steps add `assessments` here (8b). Everything is read-only for the app user.

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
