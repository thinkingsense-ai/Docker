# Agency cloud add-on (slice 1: the front end)

Installs Agency (the React UI and the thinking layer) beside the Ask app in the four stack charts. Off by default (`agency.enabled=false`); with it on, a stack gets one Deployment, two ConfigMaps and a Service.

- **No image to publish.** The layer is standard-library Python and runs on the stock `python:3.12-slim`; its code (`files/agency/*.py`, `contract.json`, `catalogue.json`) and the built UI (`files/agency/web.tgz`, unpacked by an init step) come from ConfigMaps. The same chart therefore works on AWS, OCI, GCP and Azure with no registry of our own.
- **Single source, four copies.** `agency/chart/agency.yaml` (template), `addons/thinking-layer` (code), `packs/catalogue.json` and `agency/chart/web.tgz` are copied into each chart by `scripts/sync-agency-addon.py`. Before a stack release run `scripts/sync-agency-addon.py --check`; it also fails when `web.tgz` was built from older UI sources (rebuild with `scripts/agency_bundle.py build`; needs node).
- **Public address.** Its own Service (`agency.service.type`, default LoadBalancer, port 8097) with the same cloud annotations as that cloud's Ask Service and the same `service.loadBalancerSourceRanges` (OKE: restrict in the load balancer subnet's security list, as for the Ask app). Plain HTTP unless you terminate TLS in front of it; the session cookie is HttpOnly and SameSite=Strict, with no `Secure` flag until it is served over HTTPS.
- **State.** Sessions, uploads and preferences are in memory, one replica: a restart signs everyone out.
- **Sign-in.** With the app's own business-user logins (`omnigate.appUsers`); the layer keeps no passwords. Single sign-on needs `agency.publicUrl` registered with the provider.

## Checked
- `helm template` of all four charts, five data sets each, Agency off: identical to `main` once random secrets are masked. Agency on renders on all four; `helm lint` passes.
- `agency/chart/tests/pod-smoke.sh`: the init step and the layer under the chart's security settings (uid 10001, read-only root, no capabilities) from the same files the ConfigMaps carry, beside a live stack: health, UI page, status, sign-in.

## Not done (later slices)
- The IT-risk data the screens need on a cloud stack: the `rca`, `estate` and `register` schemas, their approved questions, the Workspaces and grants (a bootstrap Job; the question bank skips questions it already holds by text, so a changed query needs the refresh step).
- Workflows: the Temporal pod and gateway with the Agency definitions (the payment-workflow sync's `RUNTIME` list predates them) and a commercial licence.
- The table, document and image adapters, upload sharing, the audit view's decision-file mount; the feed adapter (reuse terms unread) and the audio and vision adapters (non-commercial or experimental) stay out.
- Deploy-form switches (CloudFormation, OCI Resource Manager, Azure createUiDefinition, GCP variables), the docs pages, a stack release on app 0.10.22 or newer, a real cluster deploy and `verify-agency.sh`.
- The demo tour (`AGENCY_DEMO_TOUR`) is deliberately not wired: it signs in as named demo people and must never run on a real deployment.
