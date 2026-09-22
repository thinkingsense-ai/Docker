# omnigateaksstack — Azure Bicep/ARM stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new AKS cluster.
Same seeded demo as the AWS, OCI, and GCP stacks: a real supply-chain scenario across
`suppliers`, `inventory`, `procurement` Postgres schemas, registered as three federated
backends — see `helm/omnigate/templates/secrets.yaml`. Try asking: *"List each purchase order
whose shipment status is IN_TRANSIT and whose supplier country is Vietnam, including po_id, sku,
quantity ordered, carrier, eta_date, and current warehouse qty_on_hand for that sku"* (see
`fixtures/supply-chain/README.md` in this repo's root for the expected answer).

Deployers don't need to build or push the OmniGate app image themselves — `imageRepository`
defaults to the publisher's GCP Artifact Registry mirror (`us-docker.pkg.dev/thinkingsense/omnigate/omnigate`),
**not** OCI's own OCIR registry the AWS stack's README documents pulling directly: confirmed live
that OCIR now rejects external pulls from a Free Tier tenancy (`403 Forbidden: "Free tier account
is not supported"`), so that path does not actually work cross-cloud from Azure. This is likely
the real reason the GCP stack mirrors the image into its own Artifact Registry rather than pulling
OCIR directly too (previously assumed to be a performance choice) — see "Known unknowns" below.

> **This stack has not had a full end-to-end deploy on a real Azure subscription yet** (an AKS
> cluster is billable and takes ~15-20 minutes, so this was deferred pending the maintainer's
> go-ahead — see below for what running it would look like). What *has* been confirmed live
> against a real subscription so far:
> - `az bicep build` compiles `main.bicep` cleanly — this caught and fixed one real bug: a
>   `roleAssignments` `scope` needs an actual resource symbol, not a `resourceId()` string, which
>   the Bicep compiler rejects with `BCP036`.
> - `createUiDefinition.json`'s output parameter names match `main.bicep`'s parameters 1:1
>   (scripted diff, zero mismatches either direction).
> - `az deployment group validate` and `az deployment group what-if` both succeed against a real
>   resource group in `westus2` — ARM accepts the template and the planned 5-resource create list
>   (VNet, AKS cluster, managed identity, role assignment, deployment script) matches what's
>   expected, with secrets properly redacted in the `what-if` output.
> - Bicep's `string(bool)` produces capitalized `"True"`/`"False"`, which flows through to
>   `helm --set omnigate.exposeWireProtocols=...` — confirmed via `helm template` that both values
>   parse correctly as YAML booleans (1 Service rendered for `False`, 2 for `True`), not the
>   literal string `"False"`.
> - **Ampere Altra (`Standard_D2ps_v5`) regional availability, confirmed live via `az vm
>   list-skus`**: unavailable in `eastus`, `eastus2`, and `westeurope`; present but
>   subscription-restricted on some zones in `centralus`/`southcentralus`; cleanly available (all
>   zones, no restrictions) in **`westus2`** — this is a real, sharper version of the "narrower
>   than Graviton/A1" caveat than could be said before actually checking.
>
> What's still unconfirmed: whether the deploymentScript's `tdnf`/`apt-get`/`apk` JRE-install
> branch actually picks the right one on Azure's current AzureCLI container image, whether AKS's
> default StorageClass really is `managed-csi`, and the containerd short-name/PGDATA `lost+found`
> assumptions — all of which only a real `az deployment group create` will surface. See "Known
> unknowns" below.

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
az group create --name omnigate-aks-rg --location <region-with-ampere-altra>

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

Most of the items below are a reasoned port of a pattern already confirmed live on the AWS/OCI/GCP
stacks, not (yet) hit live on Azure — flagging explicitly rather than claiming confidence that
isn't real. The Ampere Altra item below, unlike the others, **is** now confirmed live.

- **Ampere Altra regional availability — confirmed live.** Unlike AWS Graviton (broadly available
  in nearly every region) or OCI's Always Free A1 (available in every Always Free region), Azure's
  Ampere Altra `Dps`/`Eps` v5-family VMs are genuinely narrower in regional availability.
  `az vm list-skus --size Standard_D2ps_v5 --location <region>` returned, against a real
  subscription: **unavailable** in `eastus`, `eastus2`, and `westeurope`; present but
  subscription-restricted on some zones in `centralus` and `southcentralus`; **cleanly available
  (all 3 zones, no restrictions) in `westus2`**. `nodeVmSize` defaults to `Standard_D2ps_v5` and
  `location` has no hardcoded default (falls back to the resource group's own location) — pick
  `westus2`, or re-run that `az vm list-skus` check for whichever region you actually want, before
  deploying. The bigger-lift alternative (out of scope for this stack) is getting a multi-arch
  amd64+arm64 manifest published for the omnigate image and switching to a universally-available
  `Dsv5`/`Dsv4` SKU instead.
- **The `deploymentScripts` JRE-install step.** `modules/deploymentScript.bicep`'s script
  installs a JRE via `tdnf`/`apt-get`/`apk` (whichever the AzureCLI container's base image
  actually has) to run the password-hash utility — this exact package-manager/package-name
  combination has not been confirmed against a real `deploymentScripts` execution. If it fails,
  check the deployment script's execution logs (`az deployment-scripts show` /
  the Portal's deployment script resource) for which package manager is actually present and fix
  the script accordingly.
- **AKS's default StorageClass name.** `values.yaml` assumes `managed-csi` exists by default on a
  fresh AKS cluster (true as of recent AKS versions, per Azure's own docs, but not independently
  reverified here) — if PVCs don't bind, `kubectl get storageclass` and adjust.
- **containerd short-name image resolution.** The OCI stack had to fully-qualify
  `docker.io/library/postgres:16-alpine` because OKE enforces Docker's "short-name mode." This
  chart keeps that fully-qualified reference defensively for AKS too, but whether AKS's
  containerd actually enforces the same policy hasn't been checked.
- **Azure Disk `lost+found` at the PVC mount root.** The OCI/AWS stacks both had to set
  `PGDATA=/var/lib/postgresql/data/pgdata` because their block-storage provisioners auto-create a
  `lost+found` directory that fails initdb's "directory must be empty" check. Kept defensively
  here on the assumption Azure Disk (ext4-formatted) behaves the same way — not independently
  confirmed.

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
