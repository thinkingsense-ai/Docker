# Upgrading and rolling back a deployment

How to move a running ThinkingSense deployment to a new release, and what to do when it goes wrong. Every step and timing below was run on a real
deployment: OCI, AWS and Azure (a previous stack release with a database row, an admin-console entry and a licence in place, then upgraded, rolled
back and deliberately broken). Google Cloud is the one cloud whose own update commands (marked **not yet run**) have not been tried; it uses the same
Helm chart.

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
2. **Take a backup.** Nothing backs your data up for you today. Run `scripts/backup-omnigate.sh --kubeconfig <file> --out <folder> --consistent`
   (a few seconds; the app is stopped for about 12 of them). It saves your databases, the admin console's settings and the licence, and a restore
   from it was tested end to end. Full instructions, including how to restore: [BACKUP-AND-RESTORE.md](BACKUP-AND-RESTORE.md).
3. **Check what will change** before applying. On OCI use a *plan* first (Resource Manager: stack, then **Plan**). A normal upgrade shows `0 to add,
   0 to destroy` and only an in-place update of the Helm release (and, for a stack upgrade that touches the network, the load balancer's security
   list). If it wants to replace the cluster or the database, stop.
4. **If you change the image tag, check that it exists** (a mistyped tag is the most common way an upgrade fails, see below).

## Upgrading the stack

- **OCI:** in the Resource Manager stack choose **Edit**, point it at the new release zip, then **Plan**, then **Apply**. From the command line:
  `oci resource-manager stack update --stack-id <id> --config-source <new zip> --working-directory omnigateokestack --force`, then
  `oci resource-manager job create-plan-job ...` and `create-apply-job`. *Tested.*
- **AWS:** in CloudFormation choose **Update stack**, replace the template with the new release's template URL (from the AWS docs page), keep your
  parameters, and review the change set. CLI: `aws cloudformation create-change-set --change-set-name upgrade --template-url <new template url>
  --parameters <your parameters, ParameterKey=X,UsePreviousValue=true> --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM`, then `execute-change-set`.
  About 2.5 minutes. The change set should list the build trigger, the deployer function and the Helm release; if it lists only a few unrelated
  resources, nothing is being upgraded. *Tested.* **This only works when you move to `eks-stack-v1.0.16` or later.** In earlier releases an update
  reports `UPDATE_COMPLETE` but changes nothing (the deployer image was never rebuilt), so those stacks can only pick up a newer *app* (image tag).
- **Azure:** deploy the new release's `azuredeploy.json` into the same resource group with the same parameters (`az deployment group create -g <rg>
  --template-file azuredeploy.json --parameters @params.json`). About 5 to 6 minutes (the install script runs again). `az deployment group what-if`
  lists the cluster as "Modify" with many property "deletes"; that is Azure's usual noise about properties the template does not set, and the
  cluster is not changed. *Tested.*
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

What happens next depends on the cloud:

- **AWS rolls a failed update back by itself.** After about 8 minutes the stack reports `UPDATE_FAILED` with the failing Helm command in the message
  (so the bad tag is visible), then `UPDATE_ROLLBACK_COMPLETE`, and the app comes back on the previous version without anyone doing anything. Measured:
  down about 9 minutes in total, nothing lost.
- **Azure does not.** The deployment fails after about 14 minutes with a long nested error that starts with an unrelated kubeconfig warning, and the
  app stays down until you deploy again with the correct tag (4.6 minutes). Measured: down about 19 minutes in total, nothing lost.
- **OCI** is as described above (about 14 minutes down).

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

## AWS notes

- **Your own certificate:** the two form fields hold at most 4096 characters (a CloudFormation limit), and a keystore that also carries the CA's
  certificate was 5,900, so a real chain may not fit. From `eks-stack-v1.0.17` you can put the certificate in AWS Secrets Manager instead and give the
  stack the secret's ARN (**Your certificate in Secrets Manager**); see the AWS README. Tested with a 5,928-character keystore.
- **Switching HTTPS settings** adds or removes a load balancer listener, which can take a minute or two to start answering after the stack
  reports success.

## Known issue fixed after `v1.1.13` and the matching AWS and Azure releases

In the first HTTPS release, turning **Serve HTTPS** off, or replacing the automatic certificate with your own, left the app unable to start until
the stack was re-applied (the pod referenced a service account that the chart no longer created). Releases after `oke-stack-v1.1.13`,
`eks-stack-v1.0.14` and `aks-stack-v1.0.11` always create it, so all three certificate modes (automatic, your own, HTTPS off) can be switched freely;
each switch took 75 to 96 seconds with nothing lost. If you are on those releases, upgrade the stack before changing the certificate settings.
