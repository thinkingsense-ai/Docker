# omnigateokestack — OCI Resource Manager stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Oracle
Kubernetes Engine cluster, sized to fit inside the Always Free tier (1 node, VM.Standard.A1.Flex,
2 OCPU / 12GB).

Deployers don't need to build or push anything — `image_repository` defaults to this project's
own public OCIR repo, so the stack pulls a pre-built image the same way `docker compose up`
pulls from a registry.

## Deploy via the OCI Console

1. **Developer Services → Resource Manager → Stacks → Create Stack**
2. Upload this directory as a zip (working directory: `omnigateokestack`), or use a hosted zip
   URL with the `?zipUrl=` "Deploy to Oracle Cloud" pattern.
3. Follow the wizard (driven by `schema.yaml`): compartment, region, an Ask-app login (see
   `variables.tf` for the `PasswordHash` command to generate one), optionally an Anthropic API
   key for NL2SQL.
4. **Terraform Actions → Apply**. Takes ~12-15 minutes (cluster ~8 min, node pool ~3 min, Helm
   release the rest).
5. Once it succeeds, the stack's **Outputs** tab has `ask_app_url` and `kubeconfig_command`.

## Deploy via the CLI

```bash
oci resource-manager stack create \
  --compartment-id <tenancy-or-compartment-ocid> \
  --config-source resource-manager/omnigateokestack \
  --display-name omnigateokestack \
  --variables '{"compartment_ocid":"<ocid>","region":"<region>","omnigate_app_users":"<user:salt:hash::>"}'
```

Then `oci resource-manager job create-apply-job --stack-id <id> --execution-plan-strategy AUTO_APPROVED`.

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
