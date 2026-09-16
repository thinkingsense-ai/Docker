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

Deployers don't need to build or push anything — `image_repository` defaults to this project's
own public OCIR repo, so the stack pulls a pre-built image the same way `docker compose up`
pulls from a registry.

## Deploy via the OCI Console

1. **Developer Services → Resource Manager → Stacks → Create Stack**
2. Upload this directory as a zip (working directory: `omnigateokestack`), or use a hosted zip
   URL with the `?zipUrl=` "Deploy to Oracle Cloud" pattern.
3. Follow the wizard (driven by `schema.yaml`): compartment, region, an Ask-app login (see
   `omnigate_app_password` -- plain text, hashed automatically during Apply), and an Anthropic
   API key. The key is technically optional -- the stack deploys fine without one -- but the Ask
   app can't answer any question until it's set, so get a free key from
   [console.anthropic.com](https://console.anthropic.com) before you start.
4. **Terraform Actions → Apply**. Takes ~12-15 minutes (cluster ~8 min, node pool ~3 min, Helm
   release the rest).
5. Once it succeeds, the stack's **Outputs** tab has `ask_app_url` and `kubeconfig_command`.

## Deploy via the CLI

```bash
oci resource-manager stack create \
  --compartment-id <tenancy-or-compartment-ocid> \
  --config-source resource-manager/omnigateokestack \
  --display-name omnigateokestack \
  --variables '{"compartment_ocid":"<ocid>","region":"<region>","omnigate_app_password":"<plain-text-password>"}'
```

Then `oci resource-manager job create-apply-job --stack-id <id> --execution-plan-strategy AUTO_APPROVED`.

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

## Prerequisites in your tenancy

Confirmed live while building this stack — worth checking before you apply:

- **1 basic OKE cluster** of quota headroom (`oci ce cluster list` / Console → Governance →
  Limits, Quotas and Usage, service `container-engine`, limit `cluster-count`)
- **1 flexible Network Load Balancer** of quota headroom (service `lbaas`, limit
  `max-nlb-flexible-count`) — leave `expose_wire_protocols` off unless you actually need a second
  one for the DB wire ports, since this stack's default HTTP-only service already needs one
- **Always Free Ampere A1 (VM.Standard.A1.Flex)** allocation for the node pool's default sizing
  (2 OCPU / 12GB)

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
