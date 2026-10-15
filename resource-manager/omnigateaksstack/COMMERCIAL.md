# Switching a running Azure (AKS) stack to the commercial edition

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

- The resource group name, and `az`, `helm`, `kubectl` and `python3` (Azure Cloud Shell has them all).
- The **pull user and token** we gave you: an OCIR login (`<namespace>/<user>`) and an Auth Token for the private
  `omnigate-commercial` repository. These are your entitlement; we revoke them when a subscription ends.

## Switch

```bash
scripts/switch-edition-aks.sh --resource-group omnigate-aks-rg --to commercial \
  --pull-user <namespace/user> --pull-token <auth token> \
  --url http://<your-load-balancer>:8080 --admin-token <your admin API token>
```

The script checks the credential and the image against the registry first and changes nothing if either is refused. It then
fetches the cluster credentials and runs `helm upgrade --reuse-values` with the new image, so every other setting stays. Note that
re-running the original Azure deployment later resets the image to whatever that deployment is given: pass the same image settings
(`imageRepository`, `imagePullUsername`, `imagePullAuthToken`) again if you do.

## Go back to the free edition

```bash
scripts/switch-edition-aks.sh --resource-group omnigate-aks-rg --to free
```

Use this when a subscription lapses, or to compare. The extra data sources stay in your configuration but only the first
three are served until you return to commercial.

## When the credential is revoked

Pods already running keep working. The next restart (a node replacement, a redeploy) fails with `ImagePullBackOff` and the
service stays down. Run the command above with `--to free` to recover.

## Not covered here

- **Going multi-node.** More than one replica needs a shared configuration database; do it as a second step after the switch.

## Verified

On 2026-10-11 a free stack on this cloud switched to the commercial image (edition FREE to COMMERCIAL, data-source cap 3 to unlimited)
and back, each in a few minutes, replacing only the OmniGate pod.
