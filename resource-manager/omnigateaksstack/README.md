# omnigateaksstack — Azure Bicep/ARM stack

ThinkingSense is a governed ontology platform for the enterprise. This stack deploys OmniGate —
ThinkingSense's federated query engine — along with the Ask App and a seeded three-schema
supply-chain demo, onto a new AKS cluster. Same seeded demo as the AWS, OCI, and GCP stacks: a
real supply-chain scenario across `suppliers`, `inventory`, `procurement` Postgres schemas,
registered as three federated backends — see `helm/omnigate/templates/secrets.yaml`. Try asking:
*"List each purchase order whose shipment status is IN_TRANSIT and whose supplier country is
Vietnam, including po_id, sku, quantity ordered, carrier, eta_date, and current warehouse
qty_on_hand for that sku"* (see `fixtures/supply-chain/README.md` in this repo's root for the
expected answer).

![OmniGate on AKS — network architecture](architecture.svg)

Deployers don't need to build or push the OmniGate app image themselves — `imageRepository`
defaults to the publisher's GCP Artifact Registry mirror (`us-docker.pkg.dev/thinkingsense/omnigate/omnigate`).

## Clean-room validated on a real Azure subscription

Deployed successfully end to end against a real subscription (`westus2`) — VNet, AKS cluster,
managed identity, role assignment, deployment script, Postgres, and the OmniGate app itself all
came up clean and the Ask app served real HTTP traffic through its public LoadBalancer IP.
Getting there took eight iterations and surfaced eight real, live-confirmed bugs — all already
fixed in this stack, not hypothetical caveats:

- **AKS's Azure CNI defaults its Service CIDR to `10.0.0.0/16`**, which fully overlapped this
  stack's own VNet (also `10.0.0.0/16`) — cluster creation failed outright with
  `ServiceCidrOverlapExistingSubnetsCidr`. Fixed by pinning `serviceCidr`/`dnsServiceIP` to
  `10.1.0.0/16` in `modules/aks.bicep`, outside the VNet's address space.
- **The `deploymentScripts` AzureCLI container is Alpine-based (`apk`), not Azure Linux
  (`tdnf`)** as first assumed — and ships with neither `curl`, `openssl`, nor a JRE by default.
  The very first `curl` call failed with `curl: command not found`; after adding curl+JRE, Helm's
  own install script then failed needing `openssl` for checksum verification. Fixed by installing
  all three together (`apk` first, `tdnf`/`apt-get` as defensive fallbacks) before anything else
  needs them.
- **OCI's OCIR registry rejects external pulls from a Free Tier tenancy.** A pod hit
  `ImagePullBackOff` / `403 Forbidden: "unknown: Free tier account is not supported."` pulling
  `ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk/omnigate:latest` — the path the AWS stack's
  README documents pulling directly. This is likely the real reason the GCP stack mirrors the
  image into its own Artifact Registry rather than pulling OCIR directly too (previously assumed
  to be a performance choice, not a workaround for this). Fixed by switching `imageRepository`'s
  default to that GCP mirror.
- **`OMNIGATE_APP_USERS` silently failed to enable login.** The app's own
  `AppAuthConfig.parse` requires exactly 5 colon-separated fields
  (`username:salt:hash:roles:attrs`) and silently *skips* any entry that doesn't split into 5 — no
  error, no crash, just `web UI business-user login disabled` and an unusable login page. The
  script built `username:hash` (3 fields), missing the trailing `::` for the empty roles/
  attributes fields that OCI's `password-hash.tf` and AWS's `handler.py` both already append.
  Fixed in `modules/deploymentScript.bicep`.
- **Hand-escaped JSON in a Bicep triple-quoted string doesn't round-trip.** The script's final
  `askAppUrl` output write used shell-escaped quotes (`\\"..\\"`) inside `'''...'''`, producing
  malformed JSON — ARM rejected the *entire* deployment with `DeploymentScriptInvalidOutputs` even
  though the Helm install had already succeeded. Fixed by building the output with Python's
  `json.dumps` instead of shell escaping.
- **`az aks get-credentials` does not install `kubectl`** — it only writes a kubeconfig file. The
  script's own LB-IP-polling loop called `kubectl get svc`, which silently failed `kubectl: not
  found` every iteration for the full 300s (masked by that loop's `2>/dev/null || true`, which was
  meant to tolerate "no IP yet," not "no kubectl"), always falling through to a "pending" output
  even once the LoadBalancer had a real IP. Fixed by running `az aks install-cli` right after
  fetching credentials.
- **Ampere Altra (`Standard_D2ps_v5`) regional availability is genuinely narrow.** Unlike AWS
  Graviton (broadly available) or OCI's Always Free A1 (available in every Always Free region),
  `az vm list-skus --size Standard_D2ps_v5 --location <region>` returned: **unavailable** in
  `eastus`, `eastus2`, and `westeurope`; present but subscription-restricted on some zones in
  `centralus`/`southcentralus`; cleanly available (all 3 zones, no restrictions) in **`westus2`**.
  Not a bug to fix — a real regional constraint to document (see "Known unknowns" below).
- **The Portal's "Deploy to Azure" button failed with a CORS error on the very first real
  click.** `v1.0.0` pointed both the template and `createUIDefinitionUri` at GitHub
  release-asset URLs (`.../releases/download/...`), which redirect through
  `release-assets.githubusercontent.com` and send no `Access-Control-Allow-Origin` header at all —
  the Portal's client-side `fetch()` failed with "There was an error downloading the template ...
  enabled CORS policy on the endpoint" for both files. `raw.githubusercontent.com` does send
  `Access-Control-Allow-Origin: *`, but only for files actually committed to the repo at a given
  ref. Fixed in `v1.0.1` by committing `azuredeploy.json` (previously release-asset-only, see
  "What's here") and repointing the docs site's Deploy button and `createUIDefinitionUri` at
  `raw.githubusercontent.com` pinned to the release tag. The CLI path was never affected — CORS is
  enforced by browsers, not `az` — so it still works fine against either release's assets.

Also confirmed working as designed, no fixes needed: `managed-csi` is AKS's real default
StorageClass (PVCs for both Postgres and OmniGate's data volume bound with no issues); the
fully-qualified `docker.io/library/postgres:16-alpine` image pulled fine; the
`PGDATA=/var/lib/postgresql/data/pgdata` workaround wasn't strictly needed on Azure Disk but was
harmless to keep; Bicep's `string(bool)` (`"True"`/`"False"`) parses correctly as YAML booleans
through `helm --set`; and `az bicep build`/`az deployment group validate`/`what-if` all still pass
cleanly on the final version.

## Why Azure *can* mirror AWS/OCI's one-click pattern (unlike the GCP stack)

Azure has a direct CloudFormation/Resource-Manager equivalent: ARM templates (authored here as
Bicep, which compiles to ARM JSON) deployed via Azure Resource Manager, with a native "Deploy to
Azure" Portal button that renders a real form from `createUiDefinition.json` — the same role
`schema.yaml` plays for the OCI stack, and `AWS::CloudFormation::Interface` metadata plays inline
for the AWS stack. So this stack follows the AWS/OCI form-driven one-click pattern, not the GCP
stack's Cloud-Shell/plain-Terraform fallback (GCP has no native product that renders a Console
form ahead of a plain Terraform config without a Marketplace-publishing process).

The one primitive Azure lacks that OCI's Terraform has natively is a "run Helm as part of this
deployment" resource. This stack's answer is a `Microsoft.Resources/deploymentScripts` resource
(`modules/deploymentScript.bicep`) — the more direct mirror of AWS's Lambda-backed custom
resource (imperative script, full control) than of OCI's declarative `helm_release` provider, but
notably simpler than AWS's own version: Azure's deploymentScripts container runtime is provided
natively, so there's no ECR-repo-plus-CodeBuild-project bootstrap step the way AWS's own Lambda
container image requires.

## Deploy via the Azure Portal (recommended)

Use the "Deploy to Azure" button on the docs site, or manually:

1. Use the "Deploy to Azure" button (points at `raw.githubusercontent.com` for this release's
   tag — see "What's here" for why it must be that host, not a GitHub release-asset URL).
2. Pick a **resource group** and a **region with Ampere Altra (arm64) VM availability** — see
   "Known unknowns" below, this is the one hard regional constraint.
3. Follow the wizard (driven by `createUiDefinition.json`): an Ask-app login (plain text, hashed
   automatically during deployment) and an Anthropic API key — required, since a deployment
   without one comes up fine but can't answer any question. Get a free key from
   [console.anthropic.com](https://console.anthropic.com) before you start.
4. Review + create. Takes roughly 15-20 minutes (AKS cluster creation dominates, plus the
   deployment script's Helm install).
5. Once it succeeds, the deployment's **Outputs** tab has `askAppUrl` and `kubeconfigCommand`.

## Deploy via the CLI

```bash
az login
az group create --name omnigate-aks-rg --location westus2  # confirmed live Ampere Altra availability, see below

az deployment group create \
  --resource-group omnigate-aks-rg \
  --template-file main.bicep \
  --parameters appPassword='<plain-text-password>' llmApiKey='<anthropic-api-key>'
```

## Prerequisites in your subscription

- **Ampere Altra (arm64) VM quota** in your target region — check with
  `az vm list-skus --size Standard_D2ps --location <region> -o table`; if that's empty, pick a
  different region before deploying (see "Known unknowns").
- IAM permissions to create a VNet, AKS cluster, managed identity, role assignment, and
  deployment script in the target resource group.
- No local build tooling needed — `main.bicep`'s `deploymentScripts` resource runs entirely
  inside Azure; the only thing you need locally is the Azure CLI (or just the Portal).

## What's here

- `main.bicep` — top-level template wiring the three modules below; the parameters here map
  1:1 onto `createUiDefinition.json`'s form fields.
- `modules/network.bicep` — a single VNet + subnet for the AKS node pool. No NAT/private
  cluster — same "simplest thing that works for a getting-started demo" posture as the OCI/GCP
  stacks, not a production-hardened network.
- `modules/aks.bicep` — a single-node-pool AKS cluster, Standard-SKU LoadBalancer (L4 TCP
  passthrough — needed for the Ask app's SSE streaming, same reason the AWS/OCI stacks avoid
  their clouds' classic/L7 LB defaults), arm64 (Ampere Altra) node pool to match the arm64-only
  omnigate image.
- `modules/deploymentScript.bicep` — the `Microsoft.Resources/deploymentScripts` resource that
  computes `OMNIGATE_APP_USERS` (same algorithm as the AWS Lambda / OCI `password-hash.tf`: fetch
  the release jar matching the image tag, run its own bundled `PasswordHash` utility) and then
  runs `helm upgrade --install` against the cluster this same deployment created.
- `createUiDefinition.json` — the Portal form definition, direct analog of the OCI stack's
  `schema.yaml`.
- `helm/omnigate/` — this stack's own copy of the Helm chart, adapted from the OCI chart: AKS's
  default `managed-csi` StorageClass instead of `oci-bv`, `service.beta.kubernetes.io/azure-load-balancer-internal:
  "false"` instead of OCI's NLB annotation, same seeded three-schema demo, same required
  app-login/API-key pattern.
- `azuredeploy.json` — the compiled output of `main.bicep` (`az bicep build --file main.bicep
  --outfile azuredeploy.json`). **Committed at each release tag**, despite that being exactly the
  kind of generated-artifact drift this repo normally avoids (see `.gitignore`-style reasoning on
  the AWS/OCI stacks) — confirmed live this is not optional for Azure specifically: the Portal's
  "Deploy to Azure" wizard fetches this file (and `createUiDefinition.json`) via a client-side
  browser `fetch()`, which needs a CORS-enabled response. GitHub's release-asset download URLs
  (`.../releases/download/...`, which redirect through `release-assets.githubusercontent.com`)
  send **no** `Access-Control-Allow-Origin` header and fail in the Portal with "There was an error
  downloading the template from URI ... Ensure that ... the publisher has enabled CORS policy on
  the endpoint" — confirmed live, this is exactly the error hit on the first real user's first
  click. `raw.githubusercontent.com` **does** send `Access-Control-Allow-Origin: *`, but only
  serves files that actually exist in the repo tree at a given ref — hence committing this file
  and referencing it via `raw.githubusercontent.com/thinkingsense-ai/Docker/<tag>/resource-manager/omnigateaksstack/azuredeploy.json`
  instead of a release asset. The CLI path (`az deployment group create --template-uri`) has no
  such constraint — CORS is a browser thing, not a CLI thing — so the release-asset URL is still
  fine there, and is what `azuredeploy.json` is also still attached to each release for.
- `verify.sh` — guided post-deploy check: fetches cluster credentials, checks pods/Services, waits
  for the LoadBalancer's public IP, and actually `curl`s the Ask app to confirm it's serving (not
  just that Kubernetes reports the pod as `Running`) — see "Verifying the deployment" below.
- `destroy.sh` — guided teardown: confirms, then deletes the resource group. Much simpler than the
  GCP stack's `destroy.sh` — see "Cleanup" below for why.

## Image

`us-docker.pkg.dev/thinkingsense/omnigate/omnigate:latest` — the GCP stack's own Artifact
Registry mirror, **not** OCIR directly. Confirmed live: a fresh AKS pod hit
`ImagePullBackOff` / `403 Forbidden: "unknown: Free tier account is not supported."` pulling
`ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk/omnigate:latest` (the path both the AWS
stack's README and this stack's own first draft assumed was directly cross-cloud-pullable) — OCI
now appears to reject external/anonymous pulls against a Free Tier tenancy's registry. Switching
to the GCP mirror fixed it. It's **arm64-only** (no amd64 manifest), same as the AWS and GCP
stacks' own image dependency.

## Known unknowns (read before your first real deploy)

Everything that was genuinely unconfirmed before the clean-room pass above is now either fixed or
confirmed working (see that section). One real, unfixable-by-this-stack constraint remains:

- **Ampere Altra regional availability.** Unlike AWS Graviton (broadly available in nearly every
  region) or OCI's Always Free A1 (available in every Always Free region), Azure's Ampere Altra
  `Dps`/`Eps` v5-family VMs are genuinely narrower in regional availability — confirmed
  unavailable in `eastus`, `eastus2`, and `westeurope`; cleanly available in `westus2` (see above).
  `nodeVmSize` defaults to `Standard_D2ps_v5` and `location` has no hardcoded default (falls back
  to the resource group's own location) — pick `westus2`, or run `az vm list-skus --size
  Standard_D2ps_v5 --location <region>` for whichever region you actually want, before deploying.
  The bigger-lift alternative (out of scope for this stack) is getting a multi-arch amd64+arm64
  manifest published for the omnigate image and switching to a universally-available `Dsv5`/`Dsv4`
  SKU instead.

## Publishing a release (maintainers)

Follow the same infra-stack release process as the AWS/OCI/GCP stacks (see this repo root's
`CLAUDE.md`): tag as `aks-stack-vX.Y.Z`, and **always pass `--latest=false`** to `gh release
create`/`gh release edit` for this tag — this repo's app releases (`vX.Y.Z`) and infra-stack
releases (`eks-stack-v*`, `oke-stack-v*`, `gke-stack-v*`, and now `aks-stack-v*`) share one GitHub
Releases list, and `modules/deploymentScript.bicep`'s script resolves the app's `omnigate.jar`
asset via `/releases/latest`, exactly like the OCI stack's `password-hash.tf` and the AWS stack's
`handler.py` do. Forgetting this silently breaks every fresh deploy on **all four** clouds until
fixed via `gh release edit <app-tag> --repo thinkingsense-ai/Docker --latest`.

Before tagging:

1. Update `main.bicep`'s `chartSourceUrl` default to point at the tag about to be cut (e.g.
   `.../archive/refs/tags/aks-stack-vX.Y.Z.tar.gz`), not `main` — see "What's here" above.
2. `az bicep build --file main.bicep --outfile azuredeploy.json` and **commit the output** (see
   "What's here" above for why this file is committed here, unlike the AWS/OCI stacks' equivalent
   build artifacts — it's a hard CORS requirement for the Portal's "Deploy to Azure" button, not a
   style choice).
3. Tag (`aks-stack-vX.Y.Z`) and push the tag.
4. Cut a GitHub release from that tag, **`--latest=false`**, with `azuredeploy.json` also attached
   as a release asset (used by the CLI path, which has no CORS constraint) and a zip of this whole
   `omnigateaksstack/` directory.
5. Update `deploy-azure.html` on the docs site: the "Deploy to Azure" button and
   `createUIDefinitionUri` must both point at
   `raw.githubusercontent.com/thinkingsense-ai/Docker/<tag>/resource-manager/omnigateaksstack/{azuredeploy.json,createUiDefinition.json}`
   — **not** a `releases/download/...` URL, which fails in the Portal with a CORS error (confirmed
   live — see "What's here"). The CLI snippet can keep using the release-asset URL.

## Verifying the deployment

```bash
./verify.sh <your-rg>
```

Guided, mirrors the exact steps run by hand during this stack's own clean-room validation: fetches
cluster credentials (installing `kubectl` via `az aks install-cli` first if it's missing —
confirmed live that `az aks get-credentials` alone does **not** install it), checks `kubectl get
pods`/`get svc`, waits up to 5 minutes for the LoadBalancer's public IP, then actually `curl`s the
Ask app and checks for a `200` — not just that Kubernetes reports the pod as `Running`, which
doesn't by itself prove the app is answering requests (this distinction mattered for real: a
deployment-script bug once reported a "successful" deploy with the Ask app's login silently
broken — see "Clean-room validated" above).

Or by hand:

```bash
az aks get-credentials --resource-group <your-rg> --name omnigate-aks
kubectl get pods -n default
kubectl get svc omnigate-omnigate-http -n default
```

If `kubectl get svc`'s `EXTERNAL-IP` column isn't `<pending>`, that IP on port 8080 is the Ask
app — `curl -o /dev/null -w '%{http_code}\n' http://<that-ip>:8080/` should print `200`.

## Cleanup

```bash
./destroy.sh <your-rg>
```

Lists what's in the resource group, asks you to type `destroy` to confirm, then deletes it.

Unlike the GCP stack (plain Terraform, no single deletable unit — its `destroy.sh` needs a
local-state-reconnect story and a manual per-resource fallback), an ARM deployment — like a
CloudFormation stack or an OCI Resource Manager stack — tracks everything it created as one
resource group, so deleting the resource group tears down everything in one action. That's the
entire teardown story here; `destroy.sh` is a thin confirmation wrapper around:

```bash
az group delete --name <your-rg> --yes --no-wait
```
