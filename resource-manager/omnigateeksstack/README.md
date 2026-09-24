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
this project's own public OCIR `:latest` image, pulled the same way `docker compose up` pulls
from a registry. The one thing AWS *does* need built locally to your account is the small
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
   [console.anthropic.com](https://console.anthropic.com) before you start.
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

## Publishing a release (maintainers)

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
