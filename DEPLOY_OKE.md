# Deploying OmniGate to OCI OKE (Always Free) via Resource Manager

This is the path from "nothing" to a working OKE deployment driven by an Oracle Resource
Manager Stack (a configurable form, not raw `kubectl apply`), and from there to an OCI
Marketplace listing.

## Phase A — OCI account bootstrap

You need local API credentials so `oci` (CLI) and Terraform can talk to your tenancy.

1. OCI Console → top-right profile icon → your username → **API Keys** → **Add API Key** →
   "Generate API Key Pair" → **Download Private Key** → click **Add**.
2. Oracle shows a ready-made `[DEFAULT]` config block (tenancy OCID, user OCID, fingerprint,
   region, key file path). Save the private key file, then create `~/.oci/config` from that
   block (or hand the block to your assistant to write it for you).
3. Also generate an **Auth Token**: profile → **Auth Tokens** → **Generate Token**. This is
   separate from the API key and is what `docker login` to OCIR uses.
4. Verify: `oci iam region list` should return a list, not an auth error.

## Phase B — Push the image to OCIR

```bash
export OCI_COMPARTMENT_OCID=ocid1.compartment.oc1..xxxx
./scripts/build-and-push.sh --region-key <iad-for-us-ashburn-1-etc> --repo omnigate --username <your-oci-username>
```

This creates an OCIR repository if needed, builds the image (compiles `llama-server` from
source — several minutes), and pushes it. Note the printed `image_repository` value; put it in
`terraform/variables.tf`'s `image_repository` default so Marketplace deployers never need to
build anything themselves.

**For a Marketplace listing specifically**: also push into an OCIR repo in **US East
(Ashburn)** — that's a hard requirement for any custom image referenced by a Marketplace
listing, independent of where your OKE cluster itself runs.

## Phase C — Helm chart

`terraform/helm/omnigate/` — translates the local `docker-compose.yml` stack: a Deployment for
omnigate, a StatefulSet+PVC for Postgres (seeded from `files/init-scott.sql`), a PVC for
OmniGate's own ConfigStore (`/var/lib/omnigate/data` — this is what makes admin-set config, like
an API key entered live in the UI, survive a pod restart; running this under plain `docker
compose` without a real volume is exactly what broke locally). Validate anytime with:

```bash
cd terraform/helm/omnigate && helm lint . --set image.repository=x --set omnigate.appUsers=demo:x:y::
```

The DB wire ports (Oracle/Postgres/MySQL/gRPC) are ClusterIP-only by default — only the HTTP
port (Ask app + admin console) gets a public LoadBalancer unless `expose_wire_protocols=true`.
The chart also **refuses to deploy** without `omnigate.appUsers` set (no default) — this repo's
`demo`/`demo` login is public knowledge (it's in the README), and shipping it on an
internet-facing LoadBalancer by default would be a real exposure now that this is headed toward
public distribution.

Generate a real login before deploying:
```bash
docker run --rm --entrypoint java <image> -cp omnigate.jar com.omnigate.http.auth.PasswordHash <password>
```

## Phase D — Terraform + the Resource Manager Stack

`terraform/` — VCN, an OKE cluster (`BASIC_CLUSTER`, the free-control-plane tier) + a node pool
on `VM.Standard.A1.Flex` (Always Free-eligible), and a `helm_release` that deploys the Phase C
chart onto the cluster this same apply creates. `terraform/schema.yaml` is what turns the raw
variables into the actual "choices" form in the Resource Manager UI — grouped into *Application*
(API key, login, model), *Compute Sizing*, *Storage*, and *Advanced*.

```bash
cd terraform && terraform init && terraform validate   # already passing locally
```

Package for Resource Manager:
```bash
./scripts/package-stack.sh   # writes omnigate-oke-stack.zip
```

## Phase E — Test the Stack for real

1. `terraform plan` locally against your real tenancy first (fast feedback, no ORM round-trip):
   ```bash
   cd terraform && terraform plan \
     -var compartment_ocid=ocid1.compartment.oc1..xxxx \
     -var region=us-ashburn-1 \
     -var image_repository=iad.ocir.io/<namespace>/omnigate \
     -var omnigate_app_users='demo:...:...::' \
     -var omnigate_llm_api_key=sk-ant-...
   ```
2. Upload `omnigate-oke-stack.zip` via **Console → Resource Manager → Stacks → Create Stack →
   My Configuration**, run a real Plan/Apply through the ORM UI — this is exactly what a
   Marketplace user's experience would be, so it's the real pre-Marketplace check.
3. Verify: pods `Running` (`kubectl get pods` using the Terraform-output kubeconfig command),
   the Ask app reachable on the LB's public IP at `:8080`, the same test question we validated
   locally ("list all rows in the emp table") returns correct results, and — the actual bug this
   whole PVC design fixes — the admin-set API key survives deleting and recreating the omnigate
   pod.

## Phase F — OCI Marketplace listing (manual, Oracle's portal)

This part is Oracle partner/portal work under your business identity — I can't click through it
for you, but here's exactly what it involves once Phases A–E are proven out:

1. **OPN membership** + accept the **OCMA** (Oracle Cloud Marketplace Agreement) — required for
   every publisher, paid or free.
2. Since this is a free/BYOL listing (not a paid package), you can **skip** the US-entity /
   USD-bank-account / iSupplier requirements — those only apply to paid package listings.
3. Ensure your OCI tenancy is subscribed to **US East (Ashburn)**, and that the Phase B image is
   pushed there specifically.
4. Register as a **Marketplace Publisher** in the OCI Console.
5. **Partner/Publisher Portal → Create Listing → type "Stack"** → upload
   `omnigate-oke-stack.zip` → fill in listing metadata (description, Ask-app screenshots, support
   contact, pricing = Free/BYOL) → submit for Oracle's review (turnaround is on their side, not
   something to script around).

## What's still open

- `terraform/variables.tf`'s `image_repository` has no default yet — set it once Phase B's push
  is done, so a Marketplace deployer never has to type a registry path themselves.
- Phase A/B/E all need your real OCI credentials and console access — nothing past this point
  can be verified further without them.
