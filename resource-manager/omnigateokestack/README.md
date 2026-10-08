# omnigateokestack — OCI Resource Manager stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Oracle
Kubernetes Engine cluster, sized to fit inside the Always Free tier (1 node, VM.Standard.A1.Flex,
2 OCPU / 12GB).

The seeded demo is a real, small supply-chain scenario across four Postgres schemas
(`suppliers`, `inventory`, `procurement`, `logistics`, registered as three federated backends --
see `helm/omnigate/templates/secrets.yaml`), not a single flat table -- this genuinely exercises
cross-backend federation, not just NL2SQL against one table. Try asking: *"List each purchase
order whose shipment status is IN_TRANSIT and whose supplier country is Vietnam, including
po_id, sku, quantity ordered, carrier, eta_date, and current warehouse qty_on_hand for that
sku"* (see `fixtures/supply-chain/README.md` in this repo's root for the expected answer).

![OmniGate on OKE — network architecture](architecture.svg)

OKE is the only stack today with a real, working path to more than one `omnigate` replica: set
`omnigate_replica_count` above 1 and fill in the config-database fields (moves admin-set config
off the per-pod volume and into a shared Postgres every replica reads/writes — see
`helm/omnigate/values.yaml`'s `configDb` block). The AWS/GCP/Azure stacks all hardcode 1 replica.

Deployers don't need to build or push anything — `image_repository` defaults to this project's
own public OCIR repo, and `image_tag` to a specific pinned free-edition release (`v0.10.4`, not
`latest` -- see that variable's own description for why), so the stack pulls a pre-built image
the same way `docker compose up` pulls from a registry.

## Deploy via the OCI Console

1. **Developer Services → Resource Manager → Stacks → Create Stack**
2. Upload this directory as a zip (working directory: `omnigateokestack`), or use a hosted zip
   URL with the `?zipUrl=` "Deploy to Oracle Cloud" pattern.
3. Follow the wizard (driven by `schema.yaml`): compartment, region, an Ask-app login (see
   `omnigate_app_password` -- plain text, hashed automatically during Apply), and an Anthropic
   API key -- required, since a stack applied without one deploys fine but can't answer any
   question. Get a free key from [console.anthropic.com](https://console.anthropic.com) before
   you start. You can also change it later, live, in the app's Admin console under **Models** (`/admin/llm-settings`).
4. **Terraform Actions → Apply**. Takes ~12-15 minutes (cluster ~8 min, node pool ~3 min, Helm
   release the rest).
5. Once it succeeds, the stack's **Outputs** tab has `ask_app_url` and `kubeconfig_command`.

## Deploy via the CLI

```bash
oci resource-manager stack create \
  --compartment-id <tenancy-or-compartment-ocid> \
  --config-source resource-manager/omnigateokestack \
  --display-name omnigateokestack \
  --variables '{"compartment_ocid":"<ocid>","region":"<region>","omnigate_app_password":"<plain-text-password>","omnigate_llm_api_key":"<anthropic-api-key>"}'
```

Then `oci resource-manager job create-apply-job --stack-id <id> --execution-plan-strategy AUTO_APPROVED`.

## Signing in (admin console and API)

There are two separate logins:

- **Ask app** (the page business users open): the username and password you set in the wizard.
- **Admin console** (`/admin`, where you add Ask-app users and change settings): the **Admin console username**
  (default `admin`) and **Admin console password**. If you leave the password blank it is the same as the Ask-app
  password; set a different one if you will share the Ask-app login with other people, because otherwise it also opens the admin console.

The admin console, the admin API (`/api/query` and the rest) and the `/mcp` endpoint all require a login, so they are not open to
anyone who can reach the load balancer's address. (Earlier stack versions left them open; re-applying an older stack with this
version turns the requirement on.) Scripts that call the API need an **Admin API token** (`omnigate_admin_api_token`, any long
random string) sent as `Authorization: Bearer <token>`. Single sign-on, if you set it up, signs in the same admin console.

## Optional TPC-H demo dataset

Set **Load the TPC-H demo dataset** (`enable_tpch_demo`) to add a realistic-size dataset on top of the
supply-chain demo: LINEITEM as Parquet in an in-cluster S3-compatible store (SeaweedFS), and the other
seven TPC-H tables in a `tpch` database in the existing Postgres. Any question that joins them is a real
cross-backend federated join, and above `OMNIGATE_PARALLEL_JOIN_MIN_ROWS` (10,000 rows) it is eligible for
the parallel join, which on a clustered deployment can be shared across replicas.

- **Needs a commercial-edition image.** It adds two backends (five in total) and the free edition allows three.
- **First deploy is slower.** A one-shot Job generates the data (DuckDB's real `tpch` generator) and loads it;
  the OmniGate pods wait for it to finish. Scale factor 1 is about 1GB (6M lineitem rows, 1.5M orders) and takes
  several minutes; 0.1 is a quick smoke-test size. Re-running or upgrading is a no-op once the data is present.
- **Sizing.** The dimension tables are well under 1GB, so the default 5GB Postgres volume is enough at scale factor 1.
- **The S3 store has no authentication.** It is ClusterIP-only and holds generated data; do not reuse the pattern for real data.
- The store is SeaweedFS because MinIO no longer publishes free container images. The loader is the same one as
  `addons/tpch-demo/loader`, copied into `helm/omnigate/files/tpch/` (keep the two in sync).

## Publishing a release (maintainers)

Cut a GitHub release zip of this directory (tag `oke-stack-vX.Y.Z`), then update the
`oke-stack-vX.Y.Z` / `omnigateokestack-vX.Y.Z.zip` references in `deploy-oci.html` (the
`zipUrl=` Launch link, the "Download the zip" link, and the CLI snippet's `--config-source`) on
the docs site to match.

**Always pass `--latest=false` to `gh release create`/`gh release edit` for infra-stack tags**
(`eks-stack-v*`, `oke-stack-v*`) -- confirmed live: this repo's app releases (`vX.Y.Z`, e.g.
`v0.6.0`) and infra-stack releases share one GitHub Releases list, and `password-hash.tf`
resolves the app's `omnigate.jar` asset (used to hash `omnigate_app_password` during Apply) via
the GitHub API's `/releases/latest`, which is just whichever release was published most recently
(unless overridden). Publishing an infra-stack release without `--latest=false` silently makes
it "latest" instead of the real app release, breaking `/releases/latest` for every deploy until
fixed -- this broke a companion EKS-stack clean-room validation with "omnigate.jar asset not
found on latest GitHub release". If this happens again, the fix is `gh release edit vX.Y.Z
--repo thinkingsense-ai/Docker --latest` on the real app release to re-point `/releases/latest`
at it.

## Going multi-node (high availability / horizontal scale)

By default this stack deploys exactly ONE OmniGate pod (behind a real OCI Network Load Balancer
already, so the LB side of "multi-node" is already there — see `helm/omnigate/templates/
omnigate.yaml`'s own comment on why an NLB, not the classic L7 LB, is required for the Ask app's
streaming responses). Running more than one OmniGate replica for real HA/throughput needs ONE
more thing: OmniGate's own admin-editable config (data sources, groups, LLM settings — anything
an admin changes live from the console) has to move out of each pod's own local, single-attach
disk and into a real, shared Postgres database every replica reads from — otherwise a second
replica can't even start (it can't mount the first pod's own volume).

**Via the OCI Console wizard**: fill in the new **"High Availability (optional)"** group —
**OmniGate replicas** (2–4, matching the node-count cap this stack's Always-Free sizing allows),
and a real, separately-provisioned Postgres for **Shared config database URL/username/password**
(e.g. an OCI Autonomous Database or Base Database instance you've already created — NOT the
seeded demo Postgres this stack also creates, which stays a single, non-HA pod either way and is
only ever used for the supply-chain demo data, never for OmniGate's own config). Leave these
blank for the default single-replica behavior.

**Via the CLI**, add to the `--variables` JSON:

```json
{
  "omnigate_replica_count": 3,
  "omnigate_config_db_url": "jdbc:postgresql://<your-managed-postgres-host>:5432/omnigate_config",
  "omnigate_config_db_user": "<user>",
  "omnigate_config_db_password": "<password>"
}
```

Also raise `node_pool_size` (up to this stack's own cap of 4) so replicas actually spread across
real, separate worker nodes rather than all landing on the one default node — a single node's own
failure would otherwise still take every replica down with it.

**Real, honest limitation, not glossed over**: this makes the OmniGate APPLICATION layer
horizontally scalable and tolerant of a single pod (or node) failing. It does NOT, by itself,
make your own connected data sources (`OMNIGATE_BACKENDS`) or the shared config Postgres highly
available — that's a property of whatever real database you point those at, same as any other
application. For genuine end-to-end HA, use a real managed/HA Postgres for the shared config
database (and for any production data source), not a single self-hosted instance.

## Prerequisites in your tenancy

Confirmed live while building this stack — worth checking before you apply:

- **1 basic OKE cluster** of quota headroom (`oci ce cluster list` / Console → Governance →
  Limits, Quotas and Usage, service `container-engine`, limit `cluster-count`)
- **1 flexible Network Load Balancer** of quota headroom (service `lbaas`, limit
  `max-nlb-flexible-count`) — leave `expose_wire_protocols` off unless you actually need a second
  one for the DB wire ports, since this stack's default HTTP-only service already needs one
- **Always Free Ampere A1 (VM.Standard.A1.Flex)** allocation for the node pool's default sizing
  (2 OCPU / 12GB)
- **Block storage headroom** (Always Free caps at 200GB total per AD). A leftover 50GB Postgres
  volume from a past deploy that wasn't cleaned up (see below) eats into this same cap.

## If a stack destroy leaves orphaned block volumes behind

`terraform destroy` uninstalls the Helm release first, but `helm uninstall` deliberately leaves
the Postgres StatefulSet's PVC behind (standard Kubernetes data-safety behavior) — and once the
cluster/node pool are destroyed next, the CSI driver that would reclaim the backing block volume
is gone too. `helm-release.tf`'s `null_resource.cleanup_pvcs` handles this automatically (deletes
stray PVCs via `kubectl` while the cluster is still alive, right before node-pool teardown), but
if `kubectl` isn't available in whatever's running `terraform destroy`, or an older release
without this fix was used, the cleanup silently no-ops and the block volume is orphaned for good
— confirmed live: seven abandoned 50GB volumes (350GB) accumulated this way across past test
destroys, exceeding the 200GB Always Free cap and blocking every subsequent deploy's own volume
provisioning ("`vcn-count`"/storage-adjacent `LimitExceeded` errors, or a new Postgres pod stuck
`Pending` on an unschedulable PVC).

To check and clean up: `oci bv volume list --compartment-id <ocid> --availability-domain <ad>
--lifecycle-state AVAILABLE` — anything `AVAILABLE` (not `ATTACHED`) with no corresponding live
cluster is orphaned and safe to `oci bv volume delete --volume-id <id> --force`.

## What's here

- `oke.tf` — VCN, OKE cluster, node pool
- `network.tf` — VCN, subnets, security lists (the LB subnet has its **own** dedicated security
  list — deliberately not sharing `oci_core_security_list.nodes`, which has
  `lifecycle { ignore_changes = [ingress_security_rules] }` to avoid fighting OKE's own
  cloud-controller-manager; sharing it meant Terraform silently never applied new rules there)
- `helm-release.tf` — installs the `helm/omnigate` chart via the `helm` Terraform provider,
  authenticating against the cluster this same apply just created
- `helm/omnigate/` — the Helm chart itself (OmniGate deployment + Service, seeded Postgres
  StatefulSet, ConfigMap, Secret)
- `variables.tf` / `schema.yaml` — Terraform variables and the Resource Manager wizard schema
- `outputs.tf` — `ask_app_url`, `kubeconfig_command`
