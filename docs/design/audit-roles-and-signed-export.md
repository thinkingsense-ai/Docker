# Audit roles and a signed decision-record export

The design note lives with the Server, where it is reviewed: **thinkingsense-ai/Server#140**, `docs/design/audit-roles-and-signed-export.md` (draft for Kumar, docs only, verified against the Server at `1ddcfa1`).

In one paragraph: reading a run's decision record through the Server (`GET /app/workflows/runs/{id}/decisions`) needs `canStartWorkflows` or `canApprove`, so an auditor would have to hold the power to act; the decision log is hash-chained but unsigned and the running Server has no signing key. The note proposes a read-only `canAudit` grant (S1) and a Server-signed JSON-lines export that covers both the Server's chain and an add-on engine's (S2), asks about history for ServiceNow and Datadog (S3), and links Server#139 (S4, also linked from #138).

What this repository does meanwhile (step 8g, Docker#261): the thinking layer serves the engine's chain read-only, with filters, to the users on its own `AGENCY_AUDIT_USERS` list, which is **not** a Server-enforced role, and an UNSIGNED export. See `addons/thinking-layer/README.md`, "Audit view".
