# omnigateaksstack — Azure Bicep/ARM stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new AKS cluster.
Same seeded demo as the AWS, OCI, and GCP stacks: a real supply-chain scenario across
`suppliers`, `inventory`, `procurement` Postgres schemas, registered as three federated
backends — see `helm/omnigate/templates/secrets.yaml`. Try asking: *"List each purchase order
whose shipment status is IN_TRANSIT and whose supplier country is Vietnam, including po_id, sku,
quantity ordered, carrier, eta_date, and current warehouse qty_on_hand for that sku"* (see
`fixtures/supply-chain/README.md` in this repo's root for the expected answer).

Deployers don't need to build or push the OmniGate app image themselves — `imageRepository`
defaults to the publisher's GCP Artifact Registry mirror (`us-docker.pkg.dev/thinkingsense/omnigate/omnigate`).

## Clean-room validated on a real Azure subscription

Deployed successfully end to end against a real subscription (`westus2`) — VNet, AKS cluster,
managed identity, role assignment, deployment script, Postgres, and the OmniGate app itself all
came up clean and the Ask app served real HTTP traffic through its public LoadBalancer IP.
Getting there took eight iterations and surfaced seven real, live-confirmed bugs — all already
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

1. Go to `https://portal.azure.com/#create/Microsoft.Template/uri/<raw-URL-of-azuredeploy.json-for-this-release>`
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
- `azuredeploy.json` — **not committed to this repo.** It's the compiled output of `main.bicep`
  (`az bicep build --file main.bicep --outfile azuredeploy.json`), regenerated and attached fresh
  to each tagged release (see "Publishing a release") — same reasoning as why the AWS stack
  publishes `template.yaml` to S3 per-release rather than pointing the Launch-Stack link at a
  GitHub raw URL on `main`: a committed compiled artifact would drift from `main.bicep` and go
  stale between releases.

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

1. `az bicep build --file main.bicep --outfile azuredeploy.json` (do not commit the output to
   `main` — it's a release-time build artifact, see "What's here" above).
2. Cut a GitHub release (tag `aks-stack-vX.Y.Z`, `--latest=false`) with `azuredeploy.json`
   attached as a release asset, and a zip of this whole `omnigateaksstack/` directory (the
   `deploymentScripts` resource's `chartSourceUrl` defaults to a GitHub tarball, so `main.bicep`'s
   `chartSourceUrl` default should be updated to point at this tag's tarball, not `main`, once a
   release exists).
3. Update the `aks-stack-vX.Y.Z` reference and the "Deploy to Azure" button's `templateUri` on the
   docs site's `deploy-azure.html` to match.

## Verifying the deployment

```bash
az aks get-credentials --resource-group <your-rg> --name omnigate-aks
kubectl get pods -n default
kubectl get svc omnigate-omnigate-http -n default
```

If `kubectl get svc`'s `EXTERNAL-IP` column isn't `<pending>`, that IP on port 8080 is the Ask
app — `curl -o /dev/null -w '%{http_code}\n' http://<that-ip>:8080/` should print `200`.

## Cleanup

Unlike the GCP stack (plain Terraform, no single deletable unit), an ARM deployment — like a
CloudFormation stack or an OCI Resource Manager stack — tracks everything it created as one
resource group, so deleting the resource group tears down everything in one action:

```bash
az group delete --name <your-rg> --yes --no-wait
```

This is a genuine advantage over the GCP stack's manual-fallback Cleanup section — no separate
by-name deletion list to keep in sync with what the template actually creates.
