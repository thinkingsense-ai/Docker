# omnigategkestack — GCP Terraform + Cloud Shell stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new GKE cluster. Same
seeded demo as the AWS and OCI stacks: a real supply-chain scenario across `suppliers`,
`inventory`, `procurement` Postgres schemas, registered as three federated backends — see
`helm/omnigate/templates/secrets.yaml`. Try asking: *"List each purchase order whose shipment
status is IN_TRANSIT and whose supplier country is Vietnam, including po_id, sku, quantity
ordered, carrier, eta_date, and current warehouse qty_on_hand for that sku"* (see
`fixtures/supply-chain/README.md` in this repo's root for the expected answer).

Deployers don't need to build or push the OmniGate app image itself — `image_tag` defaults to this
project's own public image, pulled the same way `docker compose up` pulls from a registry.

## Why no schema.yaml, and why Cloud Shell instead of a Console form

The OCI stack gets an actual Console form (dropdowns, password fields, inline validation) for
free from `schema.yaml`, because OCI Resource Manager renders it before running anything. GCP has
no equivalent product that hosts a plain Terraform config behind a native Console form without
first publishing it to GCP Marketplace (a separate producer-onboarding/review process, not
something this repo's release process currently does for the other two clouds either). Google
Cloud's Infrastructure Manager is the closer analog in spirit (hosted state, managed
plan/apply) but doesn't render a comparable form and would add a second thing to keep in sync on
every release — deferred for now, plain Terraform run from Cloud Shell gets a working one-click
deploy shipped without that extra surface area. `tutorial.md` is this stack's stand-in for
`schema.yaml`: an "Open in Cloud Shell" walkthrough that pre-clones this repo and prompts through
`terraform.tfvars` field by field, same required fields as the OCI wizard, just editor-and-terminal
shaped instead of a form.

## Deploy via Cloud Shell (recommended)

Use the "Open in Cloud Shell" button on the docs site, or manually:

```sh
gcloud auth login
git clone https://github.com/thinkingsense-ai/Docker.git
cd Docker/resource-manager/omnigategkestack
cloudshell_open --repo_url "https://github.com/thinkingsense-ai/Docker" \
  --page "shell" --tutorial "resource-manager/omnigategkestack/tutorial.md"
```

Then just run `./setup.sh` and follow its prompts — it collapses `gcloud config set project`,
enabling APIs, filling in `terraform.tfvars`, and `terraform init && apply` into one guided
script, so this isn't several manual copy-paste steps the way an earlier version of this stack's
tutorial was. See `tutorial.md` for the walkthrough as GCP's Cloud Shell renders it.

## Deploy via the CLI (any machine with Terraform, gcloud, curl, python3, and a JRE)

```bash
gcloud auth login
gcloud auth application-default login
./setup.sh
```

Or drive Terraform directly instead of the guided script:

```bash
cp terraform.tfvars.example terraform.tfvars
# fill in gcp_project_id, omnigate_app_password, omnigate_llm_api_key
terraform init
terraform plan
terraform apply
```

First apply takes 10-15 minutes (GKE cluster creation dominates that).

## Prerequisites in your project

- `container.googleapis.com` and `compute.googleapis.com` enabled (`tutorial.md` step 1 does this
  for you; the CLI path needs it done manually — see the `gcloud services enable` command there).
- A billing account linked to the project.
- IAM permissions to create a VPC, GKE cluster, node pool, and firewall rules — the deploying
  principal needs broad-ish project access, not just GKE access.
- curl, a JRE, and python3 on whatever machine runs `terraform apply` (for `password-hash.tf`) —
  Cloud Shell has all three preinstalled already. On macOS via Homebrew, `brew install openjdk`
  is not enough on its own — it's keg-only and won't be on `PATH` — but `password-hash.tf` already
  falls back to Homebrew's install prefix directly, confirmed live, so no manual PATH/symlink step
  is actually required.

## What's here

- `network.tf` — a single VPC-native subnet + firewall rules (health-check ranges, NodePort-range
  client ingress). No NAT/private nodes — same "simplest thing that works for a getting-started
  demo" posture as the OCI stack, not a production-hardened network.
- `gke.tf` — a zonal GKE cluster (waives the standard cluster management fee, the closest GCP gets
  to OKE's Always-Free-tier `BASIC_CLUSTER`) + a single node pool.
- `password-hash.tf` — computes `OMNIGATE_APP_USERS` server-side during apply, identical approach
  to the OCI stack's file of the same name.
- `helm-release.tf` — installs `helm/omnigate` (OmniGate Deployment + LoadBalancer Services,
  seeded Postgres StatefulSet, ConfigMap, Secret) against the cluster this same apply creates.
- `helm/omnigate/` — this stack's own copy of the Helm chart, adapted from the OCI chart: GKE's
  default `standard-rwo` StorageClass instead of `oci-bv`, no cloud-specific LoadBalancer
  annotation (GKE's default `type: LoadBalancer` is already an L4 passthrough NLB, unlike OCI's
  classic-LB default), same seeded three-schema demo, same required app-login/API-key pattern.
- `setup.sh` — guided setup: prompts for project/region/login/API key, enables APIs, writes
  `terraform.tfvars`, runs `terraform init && apply`. Collapses what used to be five separate
  manual tutorial steps into one script — see "Why no schema.yaml" above for why GCP needed this
  in a way AWS/OCI's Console-form-driven wizards didn't.
- `tutorial.md` — the Cloud Shell walkthrough that runs `setup.sh`; this stack's stand-in for the
  OCI stack's `schema.yaml`-driven Console form (see above).

## Image

`us-docker.pkg.dev/thinkingsense/omnigate/omnigate:latest` is live and public
(`roles/artifactregistry.reader` granted to `allUsers`). It's **arm64-only** (no amd64 manifest —
confirmed with `docker manifest inspect`), same as the AWS stack's own Graviton/arm64 image — see
the node-sizing note below for why that's not incidental.

## Clean-room validated on a real GCP project

Deployed successfully end to end against the `thinkingsense` project — VPC, firewall rules, zonal
GKE cluster, node pool, and the `helm_release` all came up clean. Two real, live-confirmed findings
along the way, both already fixed in this stack (not hypothetical caveats — actually hit):

- **Node architecture must match the image's.** The first apply used an `e2-standard-2` (amd64)
  node pool against the arm64-only published image and every pod failed
  `ErrImagePull: no match for platform in manifest`. Fixed by defaulting `node_machine_type` to
  `t2a-standard-2` (Ampere/arm64) — the same reason the AWS stack deliberately runs Graviton
  nodes instead of a default x86 node group (see `omnigateeksstack/README.md`). If you ever swap
  in an amd64 image, swap the machine type back to an `e2-*`/`n2-*` shape too.
- **`gke-gcloud-auth-plugin` isn't on `PATH` after a Homebrew `gcloud` install**, even after
  `gcloud components install gke-gcloud-auth-plugin` — the binary lands in
  `/opt/homebrew/share/google-cloud-sdk/bin`, which Homebrew's cask doesn't add to `PATH` itself.
  `kubectl` fails with "executable gke-gcloud-auth-plugin not found" until that directory is
  added. Worth calling out here since it isn't a `terraform apply` failure — it only bites you
  once you go to actually use the cluster afterward.

The zonal-cluster-fee-waiver claim and the `standard-rwo` StorageClass both worked as expected
(PVCs for both the `omnigate` data volume and Postgres bound and mounted with no issues).

## Publishing a release (maintainers)

Follow the same infra-stack release process as the AWS/OCI stacks (see this repo root's
`CLAUDE.md`): tag as `gke-stack-vX.Y.Z`, and **always pass `--latest=false`** to
`gh release create`/`gh release edit` for this tag — this repo's app releases (`vX.Y.Z`) and
infra-stack releases (`eks-stack-v*`, `oke-stack-v*`, and now `gke-stack-v*`) share one GitHub
Releases list, and `password-hash.tf` resolves the app's `omnigate.jar` asset via
`/releases/latest`, exactly like the OCI stack's `password-hash.tf` does. Then update the
`gke-stack-vX.Y.Z` reference and the "Open in Cloud Shell" button on the docs site's (planned)
`deploy-gcp.html` to match.

## Cleanup

```bash
terraform destroy
```
