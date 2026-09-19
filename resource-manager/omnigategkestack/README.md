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
  in a way AWS/OCI's Console-form-driven wizards didn't. Also installs `terraform` itself if
  needed: confirmed live, Cloud Shell can have a `terraform` on PATH that's actually just Debian's
  "here's how to apt install this" advisory stub (exits 0, so a naive `command -v` check misses
  it entirely) — `setup.sh` checks the real output of `terraform version`, not just PATH
  presence, and installs the real thing via apt when running in Cloud Shell (`CLOUD_SHELL=true`).
- `destroy.sh` — guided teardown, the reverse of `setup.sh`: `terraform destroy` when this
  directory has real state, a confirm-gated fallback to deleting the known resources directly by
  name (see "Cleanup" below) when it doesn't.
- `tutorial.md` — the Cloud Shell walkthrough that runs `setup.sh`; this stack's stand-in for the
  OCI stack's `schema.yaml`-driven Console form (see above).

## Image

`us-docker.pkg.dev/thinkingsense/omnigate/omnigate:latest` is live and public
(`roles/artifactregistry.reader` granted to `allUsers`). It's **arm64-only** (no amd64 manifest —
confirmed with `docker manifest inspect`), same as the AWS stack's own Graviton/arm64 image — see
the node-sizing note below for why that's not incidental.

## Clean-room validated on a real GCP project

Deployed successfully end to end, both from a local macOS terminal and from Cloud Shell, against
the `thinkingsense` project — VPC, firewall rules, zonal GKE cluster, node pool, and the
`helm_release` all came up clean. Several real, live-confirmed findings along the way, all already
fixed in this stack (not hypothetical caveats — actually hit):

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
- **Cloud Shell can have a `terraform` on `PATH` that isn't actually installed** — running it just
  prints Debian's "here's how to apt install this" advisory and exits `0`, so a naive
  `command -v terraform` check misses it entirely and every terraform command downstream silently
  no-ops while `setup.sh` sails on to a misleading "== Done ==" with nothing actually deployed.
  `setup.sh` now checks the real output of `terraform version` and auto-installs the real thing
  via apt when running in Cloud Shell.
- **Terraform needs its own separate credentials in Cloud Shell.** `gcloud` commands (billing
  check, enabling APIs) all work off the regular `gcloud auth login` session, but Terraform's
  `google` provider needs Application Default Credentials (ADC) — a different credential store
  that Cloud Shell, unlike a real Compute Engine VM, does not provision automatically. Without it,
  the very first resource fails with `oauth2/google: invalid token JSON from metadata: EOF`.
  `setup.sh` now checks for this and runs `gcloud auth application-default login` itself if needed.

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

## Reconnecting to an existing deployment (Cloud Shell)

If you come back later to check on or change a deployment you made via Cloud Shell, **don't click
the "Open in Google Cloud Shell" button again** — it clones fresh every time
(`cloudshell_open --force_new_clone`), landing you in a brand new `~/cloudshell_open/Docker-N`
directory with no `terraform.tfvars` and no `terraform.tfstate` (both are gitignored, never part
of the repo), even though your actual deployment and its state are sitting untouched in the
earlier clone you ran `setup.sh` from.

This isn't state actually being lost — Cloud Shell's home directory persists across sessions (only
the underlying VM is ephemeral; `$HOME` is on a small persistent disk tied to your account). Find
your way back to it instead:

```bash
# From a fresh Cloud Shell session (console.cloud.google.com, click the >_ icon):
ls ~/cloudshell_open/
```

Each `Docker-N` there is a separate clone from a separate deploy attempt. Open each one's
`resource-manager/omnigategkestack/terraform.tfstate` (or just try `terraform show` in each) until
you find the one with real resources in it — that's the clone with your actual deployment's state.
`cd` into it and `terraform plan`/`apply`/`destroy`/`output` all work again immediately from there,
same as if you'd never left.

If you can't find it at all (deleted the clone, reset your Cloud Shell disk, moved machines), state
is genuinely gone — fall back to the manual `gcloud` cleanup commands in "Cleanup" below, which
don't need Terraform state at all.

## Verifying the deployment

Unlike a CloudFormation stack (which has an Outputs tab) or an OCI Resource Manager stack (which
has an Outputs group), there's no single GCP object representing "this deployment" you can check
in one place — verification means checking the actual cluster/pods/LoadBalancer directly. Works
from any authenticated `gcloud`/`kubectl` session, Cloud Shell or your own terminal alike:

```bash
# Does the cluster exist and is it healthy?
gcloud container clusters list --project=<your-project-id>

# Point kubectl at it
gcloud container clusters get-credentials omnigate-gke --zone us-central1-a --project=<your-project-id>

# Are the pods actually running, and does the LoadBalancer have a public IP yet?
kubectl get pods -n default
kubectl get svc omnigate-omnigate-http -n default
```

If `kubectl get svc`'s `EXTERNAL-IP` column isn't `<pending>`, that IP on port 8080 is the Ask app
— `curl -o /dev/null -w '%{http_code}\n' http://<that-ip>:8080/` should print `200`.

## Cleanup

**There's no "delete stack" button or single delete command here, unlike the AWS/OCI stacks.**
CloudFormation and OCI Resource Manager each track their stack as one resource, so deleting it
tears down everything the stack created in one action. This stack is plain Terraform: the closest
equivalent is `terraform destroy`, and it only works if you run it from the exact same working
directory/clone that still has the matching `terraform.tfstate` — Terraform's local state file is
what actually tells it what exists to destroy.

```bash
./destroy.sh
```

Mirrors `setup.sh`: if this directory has real Terraform state, it runs `terraform destroy`
directly (same terraform-install and Application Default Credentials handling as `setup.sh`, so
it works standalone even if you're tearing down from a different Cloud Shell session than the one
that deployed). If there's no usable state here — see "Reconnecting to an existing deployment"
above before assuming it's really gone — it offers to fall back to deleting the known resources
directly by name instead, with an explicit `destroy` confirmation prompt before touching anything.
That fallback deletes, in this order (cluster before network — its nodes live inside the subnet;
firewall rules and subnet before the network itself, since a VPC can't be deleted while anything
still references it):

```bash
gcloud container clusters delete omnigate-gke --zone <region>-a --project=<your-project-id> --quiet
gcloud compute firewall-rules delete omnigate-gke-allow-internal omnigate-gke-allow-health-check omnigate-gke-allow-client-ingress --project=<your-project-id> --quiet
gcloud compute networks subnets delete omnigate-gke-nodes --region=<region> --project=<your-project-id> --quiet
gcloud compute networks delete omnigate-gke --project=<your-project-id> --quiet
```

Either path leaves the Artifact Registry repo and image alone — those aren't part of this
Terraform config (see "Image" above), so neither `terraform destroy` nor `destroy.sh`'s fallback
touch them. Delete that separately if you actually want it gone:

```bash
gcloud artifacts repositories delete omnigate --location=us --project=<your-project-id> --quiet
```
