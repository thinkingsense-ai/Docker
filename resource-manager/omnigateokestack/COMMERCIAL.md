# Switching a running OKE stack to the commercial edition

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
scripts/set-licence.sh --token ts1.<...> --restart \
  --kubeconfig <your kubeconfig> \
  --url http://<your-load-balancer>:8080 --admin-token <your admin API token>
```

- The script reads the token first and refuses an expired one. Only the app can check the signature, so with `--url` and
  `--admin-token` it waits until the app reports the licence is valid and tells you if it was not accepted.
- **First activation: use `--restart`.** The data-source limit and clustering are decided when a pod starts, so the pods restart once
  (a rolling restart, about two minutes). **Renewals need no restart:** run the same command without `--restart` and the app
  picks the new licence up within a couple of minutes.
- To set it at deploy time instead, paste the token into **Commercial licence** (`omnigate_license`) in the stack. Leaving that
  field blank on a later apply keeps the licence already installed, so an unrelated apply never removes it. Use the script for
  renewals: applying the stack also restarts the OmniGate pod (every apply currently does, thinkingsense-ai/Docker#59), the script does not.
- `omnigate_license` / `set-licence.sh` work the same on the AWS, GCP and Azure stacks.

**Before a licence lapses.** Renew it. After the grace period the free limits apply: one question at a time at once, and on the next restart only 3 data sources and a single node. A deployment with more than 3 data sources or more than one replica should renew well before then; improving how that downgrade behaves is tracked in thinkingsense-ai/Server#21.

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
| Multiple replicas (clustering) | no | yes, see "Going multi-node" in `README.md` |

### What you need

- The stack's OCID (Resource Manager > Stacks, or `oci resource-manager stack list`).
- The **pull user and token** we gave you: an OCIR login (`<namespace>/<user>`) and an Auth Token for the private
  `omnigate-commercial` repository. These are your entitlement; we revoke them when a subscription ends.
- The `oci` CLI and `python3` on your machine.

### Switch

```bash
scripts/switch-edition-oke.sh --stack-id <stack ocid> --to commercial \
  --pull-user <namespace/user> --pull-token <auth token> \
  --url http://<your-load-balancer>:8080 --admin-token <your admin API token>
```

The script checks the credential and the image against the registry first, and changes nothing if either is refused. It
then updates the stack's image settings (keeping every other setting) and runs an apply. With `--url` and `--admin-token`
it finishes by reading the running edition back and prints `running edition: COMMERCIAL`. The admin API token is the
`omnigate_admin_api_token` you set at deploy time; without it, open the admin console and check the edition under
Configuration.

By hand instead: set `image_repository` to `ocir.us-phoenix-1.oci.oraclecloud.com/<our namespace>/omnigate-commercial`,
`image_pull_username` and `image_pull_auth_token`, then apply. Note that saving variables in Resource Manager replaces all of
them, so re-enter the others too.

### Go back to the free edition

```bash
scripts/switch-edition-oke.sh --stack-id <stack ocid> --to free --url ... --admin-token ...
```

Use this when a subscription lapses, or to compare. The extra data sources stay in your configuration but only the first
three are served until you return to commercial.

### When the credential is revoked

Pods already running keep working. The next restart (a node replacement, a re-apply) fails with `ImagePullBackOff` and the
service stays down. Run the command above with `--to free` to recover.

## Not covered here

- **Going multi-node.** More than one replica needs a shared configuration database. Do it as a second step after the switch,
  following "Going multi-node" in `README.md`. The move to a shared database does **not** carry over users or settings you created on
  the single-node setup, so create them after the move. Verified on OCI with two replicas on two nodes.
- **Other clouds.** This runbook is for OCI. The AWS, GCP and Azure stacks get the same switch later.

## Verified

On 2026-10-12, on a free OKE stack: the licence file is mounted empty (`licenseStatus: NONE`); installing a licence with `set-licence.sh`
was read by the running pod within about 70 seconds with no restart (a deliberately invalid test licence showed `INVALID` and the reason,
and the edition stayed free); an apply with the setting blank kept the installed licence; setting `omnigate_license` on the stack replaced
it; `--restart` rolled the pod. **Not yet verified:** a genuinely valid, signed licence lifting the limits (needs a licence from the vendor's private
key).

Image swap, earlier:

On 2026-10-11 a free OKE stack with the TPC-H demo turned on served 3 data sources (the cross-database TPC-H join was rejected as
outside the allowed backends). After the switch it served 5 and the same join returned its answer; switching back
returned it to 3. Each switch took under two minutes and replaced only the OmniGate pod.
