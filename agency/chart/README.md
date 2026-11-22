# Agency cloud add-on (slices 1 and 2: the front end and the IT-risk data)

Installs Agency (the React UI and the thinking layer) beside the Ask app in the four stack charts. Off by default (`agency.enabled=false`); with it on, a stack gets one Deployment, two ConfigMaps and a Service.

- **No image to publish.** The layer is standard-library Python and runs on the stock `python:3.12-slim`; its code (`files/agency/*.py`, `contract.json`, `catalogue.json`) and the built UI (`files/agency/web.tgz`, unpacked by an init step) come from ConfigMaps. The same chart therefore works on AWS, OCI, GCP and Azure with no registry of our own.
- **Single source, four copies.** `agency/chart/agency.yaml` (template), `addons/thinking-layer` (code), `packs/catalogue.json` and `agency/chart/web.tgz` are copied into each chart by `scripts/sync-agency-addon.py`. Before a stack release run `scripts/sync-agency-addon.py --check`; it also fails when `web.tgz` was built from older UI sources (rebuild with `scripts/agency_bundle.py build`; needs node).
- **Public address.** Its own Service (`agency.service.type`, default LoadBalancer, port 8097) with the same cloud annotations as that cloud's Ask Service and the same `service.loadBalancerSourceRanges` (OKE: restrict in the load balancer subnet's security list, as for the Ask app). Plain HTTP unless you terminate TLS in front of it; the session cookie is HttpOnly and SameSite=Strict, with no `Secure` flag until it is served over HTTPS.
- **State.** Sessions, uploads and preferences are in memory, one replica: a restart signs everyone out.
- **Sign-in.** With the app's own business-user logins (`omnigate.appUsers`); the layer keeps no passwords. Single sign-on needs `agency.publicUrl` registered with the provider.

## Checked
- `helm template` of all four charts, five data sets each, Agency off: identical to `main` once random secrets are masked. Agency on renders on all four; `helm lint` passes.
- `agency/chart/tests/pod-smoke.sh`: the init step and the layer under the chart's security settings (uid 10001, read-only root, no capabilities) from the same files the ConfigMaps carry, beside a live stack: health, UI page, status, sign-in.

## Slice 2: the IT-risk data (`agency-risk`, a chart-only pack)
`demoDatasets: [agency-risk]` (it brings `it-risk` in; it mixes with the other packs and with all six; `all-packs` and a single `it-risk` do not gain it) deploys the all-packs way (connectors `pg` and `mdb`, tables addressed `pg.rca.events`) and adds:
- the Postgres schemas `rca` (incident cases and the link grades), `estate` (a simulated estate: systems, patches, changes, recovery tests, SharePoint and Slack landing tables) and `register` (risk taxonomy, rating scale, definitions, notification rules, the append-only register tables), seeded as files 05 to 07 of the packs seed ConfigMap on a fresh volume (nothing reseeds an existing release);
- those schemas in the federation list, 27 more approved questions (39 in all with the 12 IT-risk ones; the Watch, Exposure, Priorities, Notifications and Incident-brief screens ask them), and the embedding model, because an approved question is only answered from the bank with it (about 512 Mi more than IT risk alone);
- the app's SELECT-only account already gets SELECT on every schema at each start, so there are no grant files here.
Single sources stay in `demos/it-risk-rca`, `demos/it-risk-estate` and `demos/it-risk-register`; `scripts/sync-agency-addon.py` copies them into each chart's `files/`. `packs/test_agency_risk.py` locks the composition.

Checked: the seed files load clean in order on Postgres 16 beside the IT-risk seed; all 25 approved questions that read only Postgres run (two return no rows by design: the feed list needs the feed adapter and the register-runs list needs a workflow run); the older selections and all five single data sets render identically to `main`.
NOT checked: the seven questions that join MariaDB (they ran through the real app in the Docker sandbox, not from these charts); a cluster deploy; answer quality on a mix; the node size the extra memory needs (a default AWS node was already at 83% with Ask alone).

## Not done (later slices)
- Workspaces and grants: nothing loads the `it-risk` and `all-data` Workspaces or sets what each login may do (the Docker sandbox does this with `agency/local/bootstrap.py`). Without Workspaces Agency uses the default scope. The workflow slice needs the `it-risk` Workspace.
- Workflows: the Temporal pod and gateway with the Agency definitions (the payment-workflow sync's `RUNTIME` list predates them), the writer roles the register needs, the decision-file mount, and a commercial licence.
- The table, document and image adapters, upload sharing; the feed adapter (reuse terms unread) and the audio and vision adapters (non-commercial or experimental) stay out.
- Deploy-form switches (CloudFormation, OCI Resource Manager, Azure createUiDefinition, GCP variables), the docs pages, a stack release on app 0.10.22 or newer, a real cluster deploy and `verify-agency.sh`.
- The demo tour (`AGENCY_DEMO_TOUR`) is deliberately not wired: it signs in as named demo people and must never run on a real deployment.
