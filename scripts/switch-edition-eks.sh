#!/bin/bash
# Switch a running AWS (EKS) stack between the free and commercial OmniGate image without rebuilding the cluster.
#
#   switch-edition-eks.sh --stack-name omnigate-eks --to commercial --pull-user <ns/user> --pull-token <auth token> \
#                         [--region us-east-1] [--image-tag v0.10.4] [--url http://<lb>:8080 --admin-token <token>]
#   switch-edition-eks.sh --stack-name omnigate-eks --to free
#
# Only the image changes; the cluster, network, database volumes and OmniGate's saved configuration stay, and the OmniGate pod restarts.
# The stack must be on template eks-stack-v1.0.9 or later (the first with the commercial-image parameters); this script updates the
# template for you (--template-version, default 1.0.9), which also rebuilds the deploy helper once (a few minutes).
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/lib/ocir-check.sh"
STACK= TO= USER_= TOKEN= TAG= URL= ATOK= REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}} TV=1.0.9 TEMPLATE=
while [ $# -gt 0 ]; do case $1 in
  --stack-name) STACK=$2; shift 2;; --to) TO=$2; shift 2;; --pull-user) USER_=$2; shift 2;; --pull-token) TOKEN=$2; shift 2;;
  --image-tag) TAG=$2; shift 2;; --url) URL=$2; shift 2;; --admin-token) ATOK=$2; shift 2;; --region) REGION=$2; shift 2;;
  --template-version) TV=$2; shift 2;; --template) TEMPLATE=$2; shift 2;; --source-version) SV=$2; shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$STACK" ] && { [ "$TO" = commercial ] || [ "$TO" = free ]; } || { sed -n 2,11p "$0"; exit 2; }
if [ "$TO" = commercial ]; then
  { [ -n "$USER_" ] && [ -n "$TOKEN" ]; } || { echo "--to commercial needs --pull-user and --pull-token" >&2; exit 2; }
  CUR_TAG=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].Parameters[?ParameterKey==`ImageTag`].ParameterValue' --output text)
  check_commercial_pull "$USER_" "$TOKEN" "${TAG:-${CUR_TAG:-$(latest_app_tag)}}"
fi
SV=${SV:-eks-stack-v$TV}
[ -n "$TEMPLATE" ] || TEMPLATE="https://thinkingsense-cfn-templates.s3.amazonaws.com/eks-stack-v$TV/template.yaml"
case $TEMPLATE in http*) TSRC=(--template-url "$TEMPLATE");; *) TSRC=(--template-body "file://$TEMPLATE");; esac
NAMES=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].Parameters[].ParameterKey' --output text)
NEW=$(aws cloudformation get-template-summary "${TSRC[@]}" --region "$REGION" --query 'Parameters[].ParameterKey' --output text)
PARAMS=()
for k in $NEW; do
  case $k in
    ImageRepository) [ "$TO" = commercial ] && PARAMS+=("ParameterKey=$k,ParameterValue=$COMMERCIAL_REPO") || PARAMS+=("ParameterKey=$k,ParameterValue=$FREE_REPO");;
    ImagePullUsername) PARAMS+=("ParameterKey=$k,ParameterValue=${USER_}");;
    ImagePullAuthToken) PARAMS+=("ParameterKey=$k,ParameterValue=${TOKEN}");;
    SourceVersion) PARAMS+=("ParameterKey=$k,ParameterValue=$SV");;
    ImageTag) [ -n "$TAG" ] && PARAMS+=("ParameterKey=$k,ParameterValue=$TAG") || PARAMS+=("ParameterKey=$k,UsePreviousValue=true");;
    *) case " $NAMES " in *" $k "*) PARAMS+=("ParameterKey=$k,UsePreviousValue=true");; esac;;
  esac
done
aws cloudformation update-stack --region "$REGION" --stack-name "$STACK" "${TSRC[@]}" --capabilities CAPABILITY_NAMED_IAM --parameters "${PARAMS[@]}" --query StackId --output text >/dev/null
echo "updating $STACK (to $TO) ..."
aws cloudformation wait stack-update-complete --region "$REGION" --stack-name "$STACK"
echo "update: $(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text)"
[ -z "$URL" ] || [ -z "$ATOK" ] || wait_for_edition "$URL" "$ATOK"
