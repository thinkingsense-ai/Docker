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
own public OCIR repo, and `image_tag` to a specific pinned free-edition release (`v0.10.5`, not
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
   `ask_app_url` polls for the LoadBalancer's public IP for up to 3 minutes during Apply, so it's
   usually already correct -- but OCI's LB IP assignment is asynchronous, so on a slow provision
   it can still come back as `<pending-lb-ip>`. If so, run this in **Cloud Shell** (which already
   has `oci`, `kubectl`, and `jq`) using the `cluster_id` and `region` from the same Outputs tab:
   ```bash
   oci ce cluster create-kubeconfig --cluster-id <cluster_id> --region <region> --file $HOME/.kube/config --token-version 2.0.0 && \
   for i in $(seq 1 30); do
     IP=$(kubectl get svc omnigate-omnigate-http -n default -o json 2>/dev/null | jq -r '.status.loadBalancer.ingress[]?.ip' | grep -Ev '^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)' | head -1)
     [ -n "$IP" ] && echo "Ask app URL: http://$IP:8080/" && break
     sleep 10
   done
   ```
   The `grep -Ev` matters: the Service's `status.loadBalancer.ingress` list can carry both a
   private and a public IP, and picking the wrong one silently gives an unreachable URL.

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

## Maintainer notes: two Terraform gotchas

- **Chart edits are detected by a content hash.** `helm-release.tf` passes `chartContentHash` (a SHA-1 of every file under
  `helm/omnigate/`), so editing a template or `values.yaml` makes `terraform apply` upgrade the release even when
  `Chart.yaml`'s `version` stays `0.1.0`. You no longer need to bump the chart version for that.
- **`oci_core_security_list.nodes` ignores rule changes.** It has `lifecycle { ignore_changes = [ingress_security_rules] }`
  because OKE's cloud-controller-manager adds and removes its own per-NodePort rules on that list. The consequence is that
  an edit to its `ingress_security_rules` in Terraform is never applied by a later `apply`. Put any rule you manage in the
  dedicated load-balancer security list in `network.tf` (it has no such block), or change the node list by hand.
- **The helm provider is capped below 2.17** (see `versions.tf`) because 2.17.x crashed intermittently.

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

**What to expect (verified on OCI, commercial image v0.10.4 and v0.10.5, 2 replicas on 2 nodes, Oracle Autonomous Database as the shared config
store, with `omnigate_config_db_adb_ocid` set so the stack opens the database to the worker nodes):**

- **Multi-node needs the commercial image.** On the free image the extra replica logs a warning and runs single-node. Switch first
  (see `COMMERCIAL.md`), then add replicas.
- **Your existing configuration does not move to the shared database.** The single-node setup keeps users and admin-edited settings
  on the pod's local volume; with a shared database the replicas read whatever that database already holds. Business users you added
  before the move are not carried over (verified). Set the shared database up first, then create users and edit settings, or re-enter them.
  Data sources defined by the stack itself (the demo and TPC-H backends) are unaffected.
- **Business users added on one replica work on all of them.** On v0.10.4 they did not (added through pod 0, unknown to pod 1 until a
  restart). On v0.10.5 a user created through one replica signs in on the other without a restart. One gap remains (Server#20): the
  admin console's user list on the other replica can stay stale, so an admin whose request lands there may not see a user they just added.
- The replicas form one cluster (the log shows "Topology snapshot ... servers=2", `/api/config` reports `clusterNodes: 2`), one pod per node.
  Answers are identical to a single replica (the correctness harness passes on 2).
- A cross-database join can run part of its work on the other replica: 11-18% of the CPU landed on the second replica for a
  join-and-aggregate (`scripts/commercial-harness/measure-distribution.py`), and v0.10.5 runs that join about twice as fast as v0.10.4. Do not size on the assumption that two replicas halve a query.
- Availability: deleting one pod while queries ran returned HTTP 200 for every query through the load balancer, and the pod rejoined
  the cluster in about a minute.

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

## Commercial edition

Customers with a commercial subscription switch a running stack to the commercial image in place, without rebuilding anything:
see `COMMERCIAL.md` and `scripts/switch-edition-oke.sh`.

## Restricting who can connect

Set **Restrict access to these addresses** (`allowed_client_cidrs`, e.g. `203.0.113.7/32,198.51.100.0/24`) to limit who can reach the
load balancers. Blank = open to the internet, which suits a first try-out; it is one more layer on top of the logins once real data is connected.
(On app v0.10.4 and earlier the agent endpoint `/mcp/agent` answered without a login, so the restriction mattered more there; v0.10.5 closes it.)
The stack enforces it in the load balancer subnet's security list; limiting the
node ports or attaching a network security group to the Network Load Balancer does **not** narrow access (both tried, verified live).
Check a deployment with `scripts/verify-secure-deploy.sh <url> <token>`.
