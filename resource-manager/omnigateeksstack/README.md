# omnigateeksstack — AWS CloudFormation stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Amazon EKS
cluster (Graviton/arm64 worker nodes, matching the published image).

The seeded demo is a real, small supply-chain scenario across four Postgres schemas
(`suppliers`, `inventory`, `procurement`, `logistics`, registered as three federated backends --
see `helm-deployer-lambda/omnigate-chart/templates/secrets.yaml`), not a single flat table --
this genuinely exercises cross-backend federation, not just NL2SQL against one table. Try asking:
*"List each purchase order whose shipment status is IN_TRANSIT and whose supplier country is
Vietnam, including po_id, sku, quantity ordered, carrier, eta_date, and current warehouse
qty_on_hand for that sku"* (see `fixtures/supply-chain/README.md` in this repo's root for the
expected answer).

![OmniGate on EKS — network architecture](architecture.svg)

Deployers don't need to build or push the OmniGate app image itself — `ImageTag` defaults to
a specific pinned free-edition release (`v0.10.5`, not `:latest` -- see the parameter's own
description for why) hosted in this project's own public OCIR repo, pulled the same way
`docker compose up` pulls from a registry. The one thing AWS *does* need built locally to your
account is the small
Lambda that runs `helm install` against the new cluster — Lambda container images must live in
an ECR repo in the same account and Region as the function, so this stack includes a CodeBuild
project that builds and pushes that image automatically as part of the same one-click deploy.
Nothing to build or push by hand.

## Deploy via the AWS Console

1. **CloudFormation → Stacks → Create stack → With new resources**, either upload
   `template.yaml` directly, or use the "Deploy to AWS" button on the docs site for a
   pre-filled link (see note below on why that link points at S3, not GitHub).
2. Fill in the Ask-app login (`OmnigateAppUsername` / `OmnigateAppPassword` — plain text, hashed
   automatically during deploy) and an Anthropic API key -- required, since a stack created
   without one deploys fine but can't answer any question. Get a free key from
   [console.anthropic.com](https://console.anthropic.com) before you start. You can also change it later, live, in the app's Admin console under **Models** (`/admin/llm-settings`).
3. Acknowledge the IAM capability checkbox (the stack creates IAM roles) and create the stack.
   Takes ~15-20 minutes (cluster ~10 min, node group ~3 min, the CodeBuild image build ~2-3 min,
   the Helm release the rest).
4. Once `CREATE_COMPLETE`, the stack's **Outputs** tab has `AskAppUrl` and `KubeconfigCommand`.

## Deploy via the CLI

```bash
aws cloudformation create-stack \
  --stack-name omnigate-eks \
  --template-body file://template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=OmnigateAppPassword,ParameterValue=<plain-text-password> \
               ParameterKey=OmnigateLlmApiKey,ParameterValue=<anthropic-api-key>
```

Then poll with `aws cloudformation describe-stacks --stack-name omnigate-eks` until
`StackStatus` is `CREATE_COMPLETE`.

## Commercial edition

Customers with a commercial subscription switch a running stack to the commercial image in place, without rebuilding anything:
see `COMMERCIAL.md`.

## HTTPS (on by default)

The app serves HTTPS itself (the load balancer is a plain TCP pass-through, so the certificate is the app's own), and plain HTTP on port 8080 is
closed on the load balancer. Your address is `https://<load-balancer>/`.

- **No certificate supplied (the default):** the pod makes a self-signed certificate the first time it starts. It names the load balancer's address
  (the app rejects an HTTPS request whose `Host` the certificate does not name), is kept on the data volume so it survives restarts, and is made
  again if the address changes. Traffic is encrypted, but browsers show a "not trusted" warning until you supply your own certificate.
- **Your own certificate:** give a PKCS12 file (certificate and private key, base64-encoded) and its password in the deploy form. It replaces the
  automatic one; changing it restarts the app. It must name the address people browse to (a hostname you point at the load balancer is the usual
  choice; with a certificate for a name, browse by that name).
- **A certificate too big for the form (AWS):** CloudFormation limits a parameter to 4096 characters, which a certificate chain can exceed. Put it in
  AWS Secrets Manager instead (the default AWS-managed key; a customer-managed key needs `kms:Decrypt` added to the deployer role by hand) as a JSON
  secret and give its ARN in **Your certificate in Secrets Manager** (`TlsKeystoreSecretArn`, from `eks-stack-v1.0.17`):
  ```bash
  aws secretsmanager create-secret --name omnigate-certificate --secret-string \
    "$(python3 -c 'import json,base64,sys; print(json.dumps({"keystore": base64.b64encode(open(sys.argv[1],"rb").read()).decode(), "password": sys.argv[2]}))' keystore.p12 'the-password')"
  ```
  The secret takes precedence over the two form fields. The stack is given permission to read only that one secret. A wrong ARN or a secret in the
  wrong format makes the update fail with a message saying which, and the stack rolls back with the app untouched. The certificate must name the
  address people browse to, so create it after the first deploy (when the load balancer's name is known) and update the stack with the ARN.
- **Switches:** **Serve HTTPS** (on) and **HTTPS only** (on, closes 8080). Turn HTTPS off only if something in front of OmniGate already provides it;
  turn HTTPS only off to also allow plain HTTP on 8080.
- **Scripts:** `verify-secure-deploy.sh` and the switch scripts accept the self-signed certificate (`curl -k`); `VERIFY_CA=<ca.pem>` verifies against a CA.
- **Not covered yet:** certificate renewal (a supplied certificate needs replacing before it expires) and automatic certificates for a hostname (Let's Encrypt).

**Upgrading or rolling back a running deployment:** see [UPGRADING.md](https://github.com/thinkingsense-ai/Docker/blob/main/UPGRADING.md) (how to upgrade the stack and the app, what to back up first, and what to do if an upgrade fails).

**Backing up and restoring:** see [BACKUP-AND-RESTORE.md](https://github.com/thinkingsense-ai/Docker/blob/main/BACKUP-AND-RESTORE.md) (two scripts, tested end to end on OCI, AWS and Azure).

## Parts and quotes demo data

Besides the supply-chain tables, the demo database holds a small, invented robotics-hardware data set, so questions about *sourcing* have something
to answer: two assemblies (a robot joint module `JM-200` and a gripper `GR-50`) with their bills of materials, 15 parts (custom and catalog), seven
standard catalog items and how closely each part matches one, supplier capabilities and certifications, and nine requests for quote with 18 quotes.

| Schema | New tables |
| --- | --- |
| `suppliers` | `supplier_capabilities`, `supplier_certifications` (and four more suppliers, ids 5 to 8) |
| `inventory` | `parts`, `assemblies`, `bom_lines`, `catalog_items`, `part_equivalences` |
| `procurement` | `rfqs`, `quotes` |

- **Why not a fourth schema.** Each schema is one data source, and the free edition allows three, so the new tables live in the existing schemas and
  questions still join across all three.
- **How it gets there.** An init container, `ensure-manufacturing-demo`, runs on every pod start and creates the tables only when `inventory.parts` does
  not exist yet, in one transaction. A new install and an upgraded stack end up the same, and a restart never touches the rows. It does nothing if the
  three original demo tables are missing (a replaced demo database).
- **Six more trusted questions** about it are approved with the five above (single-source parts, quotes that miss the need date, a supplier that cannot
  hold a tolerance, custom parts a catalog item could replace, certification expiry, custom against catalog parts in a bill of materials).
- **Turning it off.** Set `manufacturingDemo.enabled=false` in the chart values. That stops it being added and the extra questions being approved; tables
  already created stay until you drop them.

## Trusted demo questions

After install the stack approves five trusted questions for the seeded supply-chain data (and six about the parts and quotes data below) (`helm/omnigate/files/demo-questions.json`; in the EKS stack under `helm-deployer-lambda/omnigate-chart/files/`), so the Ask app's first screen shows questions that data can answer. Without them the app shows generic examples (sales by region, top products by revenue) that the supply-chain schema cannot answer. A post-install Helm hook Job does it through the admin API using the admin login; it skips questions already present and never fails the deploy.

## Network policy

The chart adds a `NetworkPolicy` that lets only the app's pods open a connection to the demo Postgres (port 5432), so another workload in the cluster
cannot try the database logins. The app's own port is left open, because the load balancer and its clients come from any address (use "allowed client
addresses" to narrow that), and there is no egress rule. Set `networkPolicy.enabled=false` in the chart values to leave it out; add your own
`NetworkPolicy` if something else (a BI tool in another pod, say) must reach the database, since policies add up.

**Kubernetes accepts these objects on every cluster, but only enforces them where the network plugin does.** This stack's EKS cluster uses the Amazon VPC CNI with its network policy agent left off, which does not enforce `NetworkPolicy`. It is an opt-in setting of the `vpc-cni` add-on (`enableNetworkPolicy`); the stack does not turn it on.
So today the policy is in place but does nothing on a stack created from this template. Enforcement is a cluster setting, not something the chart can turn on.

Tested on a local k3s cluster (which enforces policies) with the real chart: the app's init containers and pod reached Postgres; a pod without the app's
labels, and a pod in another namespace wearing the app's labels, could not; with the policy deleted the unlabelled pod could. A newly started pod can be
refused for a few seconds before the plugin learns its labels, which the app's retrying init containers ride out. Not tested on EKS.

## The demo database account

The app reads the demo data as a **SELECT-only** database account, `omnigate_ro`, not as the `postgres` superuser. Questions are answered by SQL the
model writes, so the account that runs it should not be able to change data or read files off the database server (thinkingsense-ai/Server#39 shows
what a superuser account allows).

- **Where it comes from.** An init container, `ensure-readonly-role`, creates the account on every pod start and grants it `SELECT` on every schema of the
  demo database (and on tables added to those schemas later). It also works on a stack that was installed before this existed.
- **Its password** is generated on first install, kept in the `<release>-postgres-ro-secret` Secret and kept on every upgrade. Set `postgres.readOnlyPassword`
  in the chart values to choose your own.
- **What it cannot do.** Every write is refused ("permission denied"), whatever SQL the model produces. Anything that needs to write to the demo
  database (the admin training-data generator, rollups, the optional staging-table speed-up for very large federated joins, which falls back to the normal
  path) is refused too. To let the app write somewhere, register that database as a data source with its own account.
- **A schema an admin creates later** is readable after the next pod restart (new tables in existing schemas are readable at once).
- **The superuser.** The init container, backups and the TPC-H loader use `postgres`. Its password is generated on first install and kept in the
  `<release>-postgres-secret` Secret; the app's own container never receives it. `helm uninstall` leaves that Secret behind on purpose, so a reinstall
  onto the database volume the old release left works (delete the Secret together with the volume to start clean). A stack installed before this keeps
  the password it has, which was `postgres`; to change it, run `ALTER ROLE postgres PASSWORD '<new>'` in the database pod and patch `POSTGRES_PASSWORD` in
  that Secret to match (upgrades read the stored value back, they do not replace it).

## Signing in, and who can reach it

There are two logins. The **Ask app** (business users) uses the username and password you set at deploy time. The **admin
console** (`/admin`), the admin API (`/api/query` and the rest) and the `/mcp` endpoint need the **admin login** (`OmnigateAdminUsername / OmnigateAdminPassword / OmnigateAdminApiToken`;
default user `admin`, and a blank password means the Ask-app password). Earlier versions left these open to anyone who
could reach the load balancer; redeploying an older stack with this version turns the requirement on. Scripts send the admin API
token as `Authorization: Bearer <token>`.

Since app v0.10.5 the Ask app's agent endpoint (`/mcp/agent`) needs the admin API token like the rest of the admin surface. On v0.10.4 and earlier it answered without a login, so keep the address restriction below set on any stack still running those. To limit who can connect, set `AllowedClientCidrs` to your address or network. Blank = open to the internet, which suits a first try-out.

## Publishing a release (maintainers)

> **Update (v0.10.8, Docker #72):** the stacks no longer download the app's `omnigate.jar` to hash the login passwords (the hash is
> now computed in the stack itself with a salt that stays the same between applies), so a stack release that becomes "latest" no longer
> breaks a deploy. Keep passing `--latest=false` for stack tags anyway: the app release should stay the repository's Latest.

CloudFormation's `TemplateURL` (both the Console's quick-create deep link and the
`create-stack --template-url` CLI flag) only accepts a template hosted in an S3 bucket or an
SSM document -- confirmed live: a GitHub raw-content URL is rejected outright ("Template URL
must be supported URL"). So alongside cutting a GitHub release zip of this directory, also
upload `template.yaml` to the public S3 bucket the docs site's Launch Stack button points at:

```bash
aws s3 cp template.yaml \
  s3://thinkingsense-cfn-templates/eks-stack-vX.Y.Z/template.yaml \
  --content-type text/yaml
```

Then update the `eks-stack-vX.Y.Z` references in `deploy-aws.html` (both the Launch Stack link
and the CLI snippet's `--template-url`) on the docs site to match.

**Always pass `--latest=false` to `gh release create`/`gh release edit` for infra-stack tags**
(`eks-stack-v*`, `oke-stack-v*`) -- confirmed live: this repo's app releases (`vX.Y.Z`, e.g.
`v0.6.0`) and infra-stack releases share one GitHub Releases list, and
`helm-deployer-lambda/handler.py` resolves the app's `omnigate.jar` asset via the GitHub API's
`/releases/latest`, which is just whichever release was published most recently (unless
overridden). Publishing an infra-stack release without `--latest=false` silently makes it
"latest" instead of the real app release, breaking `/releases/latest` for every deploy until
fixed -- this broke a v1.0.4 clean-room validation stack with "omnigate.jar asset not found on
latest GitHub release" (`OmnigateHelmRelease CREATE_FAILED`). If this happens again, the fix is
`gh release edit vX.Y.Z --repo thinkingsense-ai/Docker --latest` on the real app release to
re-point `/releases/latest` at it.

## Prerequisites in your account

Confirmed live while building this stack — worth checking before you deploy:

- **EKS, VPC, and CodeBuild service quotas** in the target Region — this is a fresh VPC +
  EKS cluster + node group + one CodeBuild project, all standard default-quota resources for a
  new account.
- **IAM permissions** to create roles/policies, an EKS cluster, an ECR repo, and a CodeBuild
  project — the deploying principal needs broad-ish IAM, not just EKS access.

## If a stack delete leaves an orphaned EBS volume behind

The Lambda's Delete handler uninstalls the Helm release first, but `helm uninstall` deliberately
leaves the Postgres StatefulSet's PVC behind (standard Kubernetes data-safety behavior) — and
once the node group/cluster are destroyed next, the EBS CSI driver that would reclaim the backing
volume is gone too. `handler.py`'s Delete path now runs `kubectl delete pvc --all` right after
the uninstall (while the cluster is still alive) specifically to avoid this, mirroring a fix made
after the OCI sibling stack (`omnigateokestack`) accumulated seven orphaned 50GB block volumes
this same way across past test deploys, eventually exceeding its tenancy's storage quota. If an
older release without this fix orphaned an EBS volume anyway, find it via `aws ec2
describe-volumes --filters Name=status,Values=available` (an `available`, unattached volume with
no corresponding live cluster) and delete it with `aws ec2 delete-volume --volume-id <id>`.

## What's here

- `template.yaml` — the whole stack: VPC/subnets, EKS cluster + Graviton node group, OIDC
  provider + IRSA roles for the EBS CSI driver and the AWS Load Balancer Controller, an ECR repo
  + CodeBuild project that builds the helm-deployer Lambda image into your own account, and the
  Lambda-backed `OmnigateHelmRelease` custom resource that actually installs the Helm chart.
- `helm-deployer-lambda/` — source for the Lambda's container image: `Dockerfile` (kubectl +
  Helm + a headless JRE, for the password-hash step), `handler.py` (the custom-resource
  Create/Update/Delete logic — installs the AWS Load Balancer Controller, a gp3 StorageClass,
  then the chart itself), `buildspec.yml` (what CodeBuild runs), `omnigate-chart/` (the Helm
  chart — OmniGate Deployment + NLB Services, seeded Postgres StatefulSet, ConfigMap, Secret),
  `storageclass.yaml`.

## Notes on the NLB

The chart's Services carry `service.beta.kubernetes.io/aws-load-balancer-*` annotations
requesting a real Network Load Balancer, not AWS's deprecated in-tree Classic ELB provisioner —
confirmed live that a Classic ELB buffers the Ask app's Server-Sent Events streaming responses
(a request returns 200 with only the first event, then hangs), while the same request against
an NLB streams correctly. The AWS Load Balancer Controller (installed by the Lambda on every
deploy) is what makes the annotations take effect.
