#!/usr/bin/env bash
# Publishes an EKS stack release's CloudFormation template to the S3 bucket the AWS deploy page launches from, then checks it
# can be read anonymously (a missing object and a private one both answer 403, which is how v1.0.20-22 went unnoticed).
#   scripts/upload-eks-template.sh v1.0.23
set -euo pipefail
v=${1:?usage: $0 vX.Y.Z}
bucket=${BUCKET:-thinkingsense-cfn-templates}
tag="eks-stack-$v"
dir=$(mktemp -d /tmp/eks-template.XXXXXX)
gh release download "$tag" --repo thinkingsense-ai/Docker --pattern template.yaml --dir "$dir"
aws s3 cp "$dir/template.yaml" "s3://$bucket/$tag/template.yaml" --content-type application/x-yaml
url="https://$bucket.s3.amazonaws.com/$tag/template.yaml"
if curl -sfI "$url" >/dev/null; then
  echo "ok: $url is publicly readable"
else
  echo "uploaded, but $url is not readable anonymously: check the bucket policy allows public GetObject on '*/template.yaml'" >&2
  exit 1
fi
