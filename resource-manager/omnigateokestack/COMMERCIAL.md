# Switching a running OKE stack to the commercial edition

For customers with a commercial subscription. The free and commercial editions are two images of the same application; the
switch changes which image your existing stack runs. **Nothing is rebuilt:** the cluster, network, databases, your saved
OmniGate configuration and your URL stay as they are. The OmniGate pod restarts once on the new image (about two minutes).

## What you get

| | Free | Commercial |
|---|---|---|
| Data sources | 3 | no cap |
| Questions answered at once | 1 | no cap (tuned to load) |
| Client connections | 100 | no cap |
| Parallel-join threads | 8 | no cap |
| Multiple replicas (clustering) | no | yes, see "Going multi-node" in `README.md` |

## What you need

- The stack's OCID (Resource Manager > Stacks, or `oci resource-manager stack list`).
- The **pull user and token** we gave you: an OCIR login (`<namespace>/<user>`) and an Auth Token for the private
  `omnigate-commercial` repository. These are your entitlement; we revoke them when a subscription ends.
- The `oci` CLI and `python3` on your machine.

## Switch

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

## Go back to the free edition

```bash
scripts/switch-edition-oke.sh --stack-id <stack ocid> --to free --url ... --admin-token ...
```

Use this when a subscription lapses, or to compare. The extra data sources stay in your configuration but only the first
three are served until you return to commercial.

## When the credential is revoked

Pods already running keep working. The next restart (a node replacement, a re-apply) fails with `ImagePullBackOff` and the
service stays down. Run the command above with `--to free` to recover.

## Not covered here

- **Going multi-node.** More than one replica needs a shared configuration database. Do it as a second step after the switch,
  following "Going multi-node" in `README.md`.
- **Other clouds.** This runbook is for OCI. The AWS, GCP and Azure stacks get the same switch later.

## Verified

On 2026-10-11 a free OKE stack with the TPC-H demo turned on served 3 data sources (the cross-database TPC-H join was rejected as
outside the allowed backends). After the switch it served 5 and the same join returned its answer; switching back
returned it to 3. Each switch took under two minutes and replaced only the OmniGate pod.
