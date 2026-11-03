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

## IT & operational risk demo data (draft)

An alternative demo data set for customer conversations about technology and operational risk at a financial firm: business services with recovery objectives, applications, outages, a risk register against the board's appetite, controls and their tests, key risk indicators, audit issues, third-party vendors and vulnerabilities. Everything in it is invented. It is not on the deploy form; choose it with the chart value `demoDataset=it-risk` (default `supply-chain`) on a **fresh install**.

- **Two data sources, two databases.** The Postgres half is one schema, `risk`; a MariaDB container (`<release>-mariadb`, official `mariadb:11` image, its own volume) holds the `security` database. Questions that join the two are answered by federation. The free edition allows three data sources and the supply-chain set already uses all three, so this set **replaces** the supply-chain, manufacturing and TPC-H data rather than adding to it; see thinkingsense-ai/Server#45.
- **Twelve trusted questions** are approved in place of the supply-chain ones (`files/demo-questions-it-risk.json`; same source as `fixtures/it-risk/`).
- **Accounts.** The app reads Postgres and MariaDB through SELECT-only accounts. MariaDB passwords are generated on first install and kept on upgrade (`<release>-mariadb-secret`, kept on uninstall like the Postgres one); the NetworkPolicy lets only the app's pods connect.
- **Not reseeded.** The data is loaded when the database volume is empty. Setting `demoDataset` on an existing release does not switch it; install a new one.
- **Accuracy.** Not yet measured through the Ask app. On the current app version multi-table questions often fail (thinkingsense-ai/Server#43), so treat this as a draft until that is fixed.

## All demo packs at once (draft)

Setting the **Demo data** parameter to `all-packs` on the CloudFormation form (Advanced; `supply-chain` is the default) loads every pack together: supply chain, manufacturing, IT & operational risk and the Smithsonian Open Access sample. The Ask app shows them as a pack picker (5 + 6 + 12 + 5 = 28 trusted questions, `files/demo-questions-all-packs.json`, the same set as `demos/all-packs/`).

- **Three data sources.** The free edition allows three, so each kind is one source with its schemas discovered inside it (`OMNIGATE_FEDERATION_AUTO_DISCOVER_SCHEMAS`): `pg` (Postgres: `suppliers`, `inventory`, `procurement`, `risk`, `smithsonian`), `mdb` (MariaDB: `security`) and `files` (the museum directory, a CSV in an in-cluster SeaweedFS bucket). Tables are addressed `connector.schema.table`; the CSV is `files.museums`. There are no schema routing rules in this mode (they would rewrite the schema part to the source name).
- **What is added.** A SeaweedFS Deployment with a small volume, a one-off Job that loads the Smithsonian sample and the CSV, and an embedding Deployment (below). The MariaDB StatefulSet is the one `it-risk` uses.
- **Smithsonian data is downloaded.** The 5.4 MB sample is too large for a ConfigMap, so the loader fetches it from a pinned commit of this public repository and refuses a file whose SHA-256 differs (`packs.smithsonianDataUrl` / `smithsonianDataSha256`, changed together). The cluster therefore needs outbound access to `raw.githubusercontent.com`. The app's pods wait for the loader before starting.
- **An embedding model runs next to the app.** The app image carries none, and without one the question bank cannot match a new question to an approved one by meaning (so the approved questions would not be served, and two of the Smithsonian ones would be refused as "I don't have data about..."). `<release>-packs-embed` runs the official llama.cpp server (build b10795, pinned by digest) with nomic-embed-text-v1.5 (Apache-2.0, 84 MB), downloaded from Hugging Face on every start and checked against its SHA-256, so the cluster also needs outbound access to `huggingface.co`. Newer llama.cpp server builds answer "does not support embeddings" for this model, and the server needs `-b 2048 -ub 2048` or it rejects the longer schema descriptions.
- **Questions were checked on GKE, not yet here.** The 28 questions and this chart configuration were checked against a live GKE deployment (all 28 return rows from the question bank). The EKS stack shares the same templates, but it has not been deployed with this option yet; treat it as a draft until it has. The rules the questions follow are in `demos/all-packs/README.md` (for example, across two sources write `CURRENT_DATE - INTERVAL '365' DAY`, not `CURRENT_DATE - 365`).
- **Size.** It adds about 0.35 vCPU and 0.75 GiB of requests (the embedding model and MariaDB) on top of the default demo. On GKE's 2 vCPU / 8 GB node the whole stack ran at about 80% CPU: check the node size (the default `NodeInstanceType`).
- **No row filters.** The compose demo hides non-CC0 Smithsonian records from a "public" login with an access policy. The cloud stacks have one generated login, and every record in this sample is CC0, so no policy is installed.
- **Not reseeded.** Choose it on a fresh install; changing it on an existing deployment does not switch the data. Free-form questions are a different matter: see thinkingsense-ai/Server#43.

## Trusted demo questions

After install the stack approves five trusted questions for the seeded supply-chain data (and six about the parts and quotes data below) (`helm/omnigate/files/demo-questions.json`; in the EKS stack under `helm-deployer-lambda/omnigate-chart/files/`), so the Ask app's first screen shows questions that data can answer. Without them the app shows generic examples (sales by region, top products by revenue) that the supply-chain schema cannot answer. A post-install Helm hook Job does it through the admin API using the admin login; it skips questions already present and never fails the deploy.

## Network policy

The chart adds a `NetworkPolicy` that lets only the app's pods open a connection to the demo Postgres (port 5432), so another workload in the cluster
cannot try the database logins. The app's own port is left open, because the load balancer and its clients come from any address (use "allowed client
addresses" to narrow that), and there is no egress rule. Set `networkPolicy.enabled=false` in the chart values to leave it out; add your own
`NetworkPolicy` if something else (a BI tool in another pod, say) must reach the database, since policies add up.

**Kubernetes accepts these objects on every cluster, but only enforces them where the network plugin does.** This stack turns enforcement on: the
template installs the Amazon VPC CNI as a managed `vpc-cni` add-on with `enableNetworkPolicy` set to `true` (the stock `aws-node` ships with its network
policy agent off), and the Helm release waits for it, so the policy exists only once something enforces it. It needs a node kernel of 5.10 or newer (the
Graviton AL2023 nodes run 6.1). Updating an existing stack adds the add-on in place: the cluster and nodes are not replaced, and the app's pod restarts once.

Tested live on EKS (Kubernetes 1.36, VPC CNI v1.22.4): on a stack created from `eks-stack-v1.0.19` a policy applied by hand was ignored (a pod
without the app's labels still connected to Postgres); after updating that stack in place to this template, the same kind of pod, and a pod in another
namespace wearing the app's labels, were refused, a pod with the app's labels was allowed, and the app kept answering queries (as `omnigate_ro`, including
the three-schema join) through its load balancer. The database pod was not restarted. Enforcement on the other clouds is still a cluster setting those
stacks do not turn on.

## Stored settings are encrypted

The app keeps the settings you enter in its console (source passwords, tokens, the model key) in a configuration store on its data volume. The chart sets
`OMNIGATE_CONFIG_ENCRYPTION_KEY`, so these are encrypted at rest with AES-GCM; without it the app's deployment check reports a critical problem and does not
call the installation production ready. The key is generated on the first install and kept on every upgrade, in its own Secret (`<release>-config-key`), which
`helm uninstall` leaves in place. Set `configEncryption.key` (base64, 16, 24 or 32 bytes) to choose your own, or `configEncryption.enabled=false` to leave it off.

**Do not delete that Secret while the data volume remains**: settings encrypted under a key that is lost cannot be read back. Back it up with the data
volume. An app image older than 0.10.12 cannot read encrypted settings, so do not roll back to one once this has run.

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
