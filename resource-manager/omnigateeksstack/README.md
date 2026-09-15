# omnigateeksstack — AWS CloudFormation stack

Deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Amazon EKS
cluster (Graviton/arm64 worker nodes, matching the published image).

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
   automatically during deploy), optionally an Anthropic API key for NL2SQL.
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

## Prerequisites in your account

Confirmed live while building this stack — worth checking before you deploy:

- **EKS, VPC, and CodeBuild service quotas** in the target Region — this is a fresh VPC +
  EKS cluster + node group + one CodeBuild project, all standard default-quota resources for a
  new account.
- **IAM permissions** to create roles/policies, an EKS cluster, an ECR repo, and a CodeBuild
  project — the deploying principal needs broad-ish IAM, not just EKS access.

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
