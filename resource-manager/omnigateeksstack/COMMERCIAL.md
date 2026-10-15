# Switching a running AWS (EKS) stack to the commercial edition

For customers with a commercial subscription. The free and commercial editions are two images of the same application; the
switch changes which image your existing stack runs. **Nothing is rebuilt:** the cluster, network, database, your saved
OmniGate configuration and your URL stay as they are. The OmniGate pod restarts once on the new image.

## What you get

| | Free | Commercial |
|---|---|---|
| Data sources | 3 | no cap |
| Questions answered at once | 1 | no cap (tuned to load) |
| Client connections | 100 | no cap |
| Parallel-join threads | 8 | no cap |
| Multiple replicas (clustering) | no | yes |

## What you need

- The stack name (default `omnigate-eks`) and region, and the `aws` CLI signed in to that account.
- The **pull user and token** we gave you: an OCIR login (`<namespace>/<user>`) and an Auth Token for the private
  `omnigate-commercial` repository. These are your entitlement; we revoke them when a subscription ends.

## Switch

```bash
scripts/switch-edition-eks.sh --stack-name omnigate-eks --region us-east-1 --to commercial \
  --pull-user <namespace/user> --pull-token <auth token> \
  --url http://<your-load-balancer>:8080 --admin-token <your admin API token>
```

The script checks the credential and the image against the registry first and changes nothing if either is refused. It then
updates the CloudFormation stack: the image repository, registry user and token change, and **every other parameter keeps its
current value**. The stack must be on template `eks-stack-v1.0.9` or later; the script moves it there (rebuilding the deploy helper
once, a few minutes), after which switching is a Helm upgrade of the OmniGate pod only. With `--url` and `--admin-token` it ends by
reading the running edition back.

## Go back to the free edition

```bash
scripts/switch-edition-eks.sh --stack-name omnigate-eks --region us-east-1 --to free
```

Use this when a subscription lapses, or to compare. The extra data sources stay in your configuration but only the first
three are served until you return to commercial.

## When the credential is revoked

Pods already running keep working. The next restart (a node replacement, a redeploy) fails with `ImagePullBackOff` and the
service stays down. Run the command above with `--to free` to recover.

## Not covered here

- **Going multi-node.** More than one replica needs a shared configuration database; do it as a second step after the switch.

## Verified

On 2026-10-11 a free AWS stack switched to the commercial image (edition FREE to COMMERCIAL, data-source cap 3 to unlimited) and back,
each in a few minutes, replacing only the OmniGate pod. A registry token containing brackets and commas was handled correctly.
