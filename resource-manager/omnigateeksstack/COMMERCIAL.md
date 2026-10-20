# Switching a running AWS (EKS) stack to the commercial edition

For customers with a commercial subscription. There are two ways, and the licence is the one to use:

| | Licence (recommended) | Image swap |
|---|---|---|
| What changes | A small licence file is added; the image stays the free one | The pods run the private commercial image |
| You need | The licence token we issue you | A registry user and token for our private repository |
| Rebuild | No | No |
| When it ends | After the 7-day grace period the app falls back to the free edition and keeps running | Pods fail to restart if the credential is revoked |

Either way the cluster, network, databases, your saved OmniGate configuration and your URL stay as they are.

## Install or renew a licence (recommended)

You receive a licence token (it starts with `ts1.`) valid for the term you bought, plus a 7-day grace period after it.

```bash
aws eks update-kubeconfig --name omnigate-eks --region <region>
scripts/set-licence.sh --token ts1.<...> --restart \
  --url https://<your-load-balancer> --admin-token <your admin API token>
```

- The script reads the token first and refuses an expired one. Only the app can check the signature, so with `--url` and
  `--admin-token` it waits until the app reports the licence is valid and tells you if it was not accepted.
- **First activation: use `--restart`.** The data-source limit and clustering are decided when a pod starts, so the pods restart once
  (about two minutes). **Renewals need no restart:** run the same command without `--restart` and the app picks the new licence up
  within a couple of minutes.
- To set it at deploy time instead, use the **Commercial licence** (`OmnigateLicense`) parameter. Leaving it blank on a later update keeps the licence already
  installed. Use the script for renewals: updating the stack also restarts the OmniGate pod (every update currently does,
  thinkingsense-ai/Docker#59), the script does not.

**Before a licence lapses.** Renew it. After the grace period the free limits apply: one question at a time at once, and on the next
restart only 3 data sources and a single node. A deployment with more than 3 data sources or more than one replica should renew well
before then; improving how that downgrade behaves is tracked in thinkingsense-ai/Server#21.

**Check it:** the admin console Overview page, or `GET /api/config`, shows `licenseStatus` (`VALID`, `EXPIRED`, `INVALID` or `NONE`),
the customer and the expiry date. An invalid or expired licence never stops the app; it stays on the free edition and says why.

## Image swap (alternative)

### What you get

| | Free | Commercial |
|---|---|---|
| Data sources | 3 | no cap |
| Questions answered at once | 1 | no cap (tuned to load) |
| Client connections | 100 | no cap |
| Parallel-join threads | 8 | no cap |
| Multiple replicas (clustering) | no | yes |

### What you need

- The stack name (default `omnigate-eks`) and region, and the `aws` CLI signed in to that account.
- The **pull user and token** we gave you: an OCIR login (`<namespace>/<user>`) and an Auth Token for the private
  `omnigate-commercial` repository. These are your entitlement; we revoke them when a subscription ends.

### Switch

```bash
scripts/switch-edition-eks.sh --stack-name omnigate-eks --region us-east-1 --to commercial \
  --pull-user <namespace/user> --pull-token <auth token> \
  --url https://<your-load-balancer> --admin-token <your admin API token>
```

The script checks the credential and the image against the registry first and changes nothing if either is refused. It then
updates the CloudFormation stack: the image repository, registry user and token change, and **every other parameter keeps its
current value**. The stack must be on template `eks-stack-v1.0.9` or later; the script moves it there (rebuilding the deploy helper
once, a few minutes), after which switching is a Helm upgrade of the OmniGate pod only. With `--url` and `--admin-token` it ends by
reading the running edition back.

### Go back to the free edition

```bash
scripts/switch-edition-eks.sh --stack-name omnigate-eks --region us-east-1 --to free
```

Use this when a subscription lapses, or to compare. The extra data sources stay in your configuration but only the first
three are served until you return to commercial.

### When the credential is revoked

Pods already running keep working. The next restart (a node replacement, a redeploy) fails with `ImagePullBackOff` and the
service stays down. Run the command above with `--to free` to recover.

## Not covered here

- **Going multi-node.** More than one replica needs a shared configuration database; do it as a second step after the switch.

### Verified (image swap)

On 2026-10-11 a free AWS stack switched to the commercial image (edition FREE to COMMERCIAL, data-source cap 3 to unlimited) and back,
each in a few minutes, replacing only the OmniGate pod. A registry token containing brackets and commas was handled correctly.
