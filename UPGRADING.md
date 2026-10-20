# Upgrading and rolling back a deployment

How to move a running ThinkingSense deployment to a new release, and what to do when it goes wrong. Every step and timing below was run on a real
OCI deployment (a previous stack release with a database row, an admin-console entry and a commercial licence in place, then upgraded and rolled
back). The AWS, Azure and Google Cloud steps use the same Helm chart and behave the same way once the chart is updating, but their *own* update
commands (marked **not yet run**) have not been tried end to end.

## Two things you can upgrade

| | What changes | How | Time |
|---|---|---|---|
| **The stack** (`oke-stack-vX`, `eks-stack-vX`, `aks-stack-vX`, GCP `main`) | the cloud resources and the Helm chart | point the deployment at the new release and apply | about 1.5 minutes |
| **The app** (`v0.10.x`, the image tag) | only the OmniGate image | change the image tag and apply | about 1.5 minutes |

Both restart the OmniGate pod once. The database pod is not restarted. Your data, the admin console's settings (trusted questions, users and so on)
and an installed licence all stay.

## Before you upgrade

1. **Read the release notes** for anything that changes an address or a setting. Example: `oke-stack-v1.1.13` turned HTTPS on and closed plain HTTP, so
   `http://<address>:8080` stops working and `https://<address>/` is the new address. Bookmarks and scripts need the new URL.
2. **Take a backup.** Nothing backs your data up for you today.
   ```bash
   # the demo database (and any data you added to it)
   kubectl exec omnigate-postgres-0 -- pg_dump -U postgres postgres > omnigate-db.sql
   # the admin console's settings (trusted questions, users, saved settings)
   kubectl exec deploy/omnigate-omnigate -- tar czf - -C /var/lib/omnigate data > omnigate-config.tgz
   ```
   Both commands were run and produce a file. The settings copy is taken while the app runs, so a very recent change may not be in it. Restoring
   from either has **not** been tested yet, so treat them as a safety net and not a proven recovery.
3. **Check what will change** before applying. On OCI use a *plan* first (Resource Manager: stack, then **Plan**). A normal upgrade shows `0 to add,
   0 to destroy` and only an in-place update of the Helm release (and, for a stack upgrade that touches the network, the load balancer's security
   list). If it wants to replace the cluster or the database, stop.
4. **If you change the image tag, check that it exists** (a mistyped tag is the most common way an upgrade fails, see below).

## Upgrading the stack

- **OCI:** in the Resource Manager stack choose **Edit**, point it at the new release zip, then **Plan**, then **Apply**. From the command line:
  `oci resource-manager stack update --stack-id <id> --config-source <new zip> --working-directory omnigateokestack --force`, then
  `oci resource-manager job create-plan-job ...` and `create-apply-job`. *Tested.*
- **AWS:** in CloudFormation choose **Update stack**, replace the template with the new release's template URL, and keep your parameters. *Not yet run.*
- **Azure:** deploy the new `azuredeploy.json` into the same resource group with the same parameters. *Not yet run.*
- **Google Cloud:** `git pull` (the stack deploys from `main`), then `terraform plan` and `terraform apply`. *Not yet run.*

## Upgrading the app

Change the image tag (**Image tag**, under *Advanced* in the deploy form, `image_tag` in the variables) to the new version and apply. Going back
to an older app version the same way also worked: the settings written by the newer version were still readable. *Tested v0.10.7 to v0.10.8 and
back.*

## If an upgrade fails

**A bad image tag takes the app down.** With one replica the old pod is removed before the new one can start (the data volume can only be used by
one pod), so if the new image cannot be pulled the app stays down until you fix it. Measured: down from about 30 seconds into the apply; the apply
reported only `context deadline exceeded` after 10.5 minutes (it does not mention the image); correcting the tag and applying again brought it
back in 97 seconds, with nothing lost. So:

- To see the real cause, look at the pod: `kubectl describe pod -l app.kubernetes.io/component=omnigate` shows `ErrImagePull` or
  `ImagePullBackOff` and the tag it tried.
- Fix the tag and apply again. The second apply is an in-place update, not a replace.
- Avoid it: check the tag exists before applying, for example `docker manifest inspect ocir.us-phoenix-1.oci.oraclecloud.com/ax8tpjdxhykk/omnigate:v0.10.8`
  (it prints the manifest if the tag exists and an error if not).

**If a pod will not start after a setting change**, look at the cluster's own message:
`kubectl get rs -l app.kubernetes.io/instance=omnigate` then `kubectl describe rs <name>`. If the cause is already fixed but nothing happens (Kubernetes
retries with a growing delay), `kubectl rollout restart deploy/omnigate-omnigate` retries at once.

## Rolling back

- **Rolling back the app** (older image tag): works, as above.
- **Switching a feature off** (for example **Serve HTTPS** off to get plain HTTP on 8080 back): works and is the supported way to undo the HTTPS
  default. Stay on the new release and change the setting.
- **Rolling the stack back to an older release does not work across `oke-stack-v1.1.13`.** Pointing the stack at `oke-stack-v1.1.12` after
  `v1.1.13` left the pod impossible to create (the older chart removes a service account the newer one added; the app stays down until you roll
  forward again). Roll forward instead: stay on the current release (or move to a newer one) and change settings. The same caution applies to
  other clouds: do not go back to an older stack release; fix forward.

## Known issue fixed after `v1.1.13` and the matching AWS and Azure releases

In the first HTTPS release, turning **Serve HTTPS** off, or replacing the automatic certificate with your own, left the app unable to start until
the stack was re-applied (the pod referenced a service account that the chart no longer created). Releases after `oke-stack-v1.1.13`,
`eks-stack-v1.0.14` and `aks-stack-v1.0.11` always create it, so all three certificate modes (automatic, your own, HTTPS off) can be switched freely;
each switch took 75 to 96 seconds with nothing lost. If you are on those releases, upgrade the stack before changing the certificate settings.
