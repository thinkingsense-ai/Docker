# Backing up and restoring a deployment

Nothing backs your ThinkingSense deployment up for you. Your data lives on the cluster's disks, and a destroyed stack deletes them. This page
shows how to take a backup and how to bring a deployment back from one, with two scripts that work the same on OCI, AWS, Google Cloud and Azure.
Both scripts were run end to end on real OCI, AWS and Azure deployments (below). Google Cloud uses the same chart and scripts but has not been run.

## What a backup contains

| | In the backup | How |
|---|---|---|
| **Your databases** (the demo data and anything you added) | yes | `pg_dump` of every database in the deployment |
| **The admin console's saved settings** (trusted questions, users, saved settings) | yes | a copy of the app's data volume |
| **The commercial licence** | yes | copied from the cluster |
| **The HTTPS certificate** | no | a new deployment makes its own (it names its own address); if you supplied your own, keep that file |
| **Your deploy settings** (passwords, Anthropic API key, sizes) | no | keep the values you entered in the deploy form somewhere safe; they are not in the cluster in a form you can read back |

Treat a backup folder as a secret: it holds your data and the licence.

## Taking a backup

You need `kubectl` pointed at the cluster. Get the credentials once (the deploy outputs show the command):

- **OCI:** `oci ce cluster create-kubeconfig --cluster-id <cluster id> --region <region> --file ~/.kube/omnigate --token-version 2.0.0`
- **AWS:** `aws eks update-kubeconfig --region <region> --name omnigate-eks --kubeconfig ~/.kube/omnigate`
- **Google Cloud:** `gcloud container clusters get-credentials omnigate-gke --zone <zone> --project <project>`
- **Azure:** `az aks get-credentials --resource-group <your resource group> --name omnigate-aks --file ~/.kube/omnigate`

Then, from a clone of this repository:

```bash
scripts/backup-omnigate.sh --kubeconfig ~/.kube/omnigate --out ./omnigate-backup
```

It writes a timestamped folder (`db-<name>.dump`, `config-store.tgz`, `licence.txt`, `manifest.txt`) and takes a few seconds. It does not stop the app.

**Settings copied while the app runs may miss the last moments' changes.** For a copy that is exactly consistent, add `--consistent`: the app is stopped
for about 12 seconds (the whole script takes about 15) and started again.

```bash
scripts/backup-omnigate.sh --kubeconfig ~/.kube/omnigate --out ./omnigate-backup --consistent
```

How often: take one before every upgrade (see [UPGRADING.md](UPGRADING.md)), and on a schedule that matches how much of the admin console's work you
could bear to redo. **Copy the folder somewhere that is not the cluster** (a bucket or a file share); a backup that lives on the same disks it is
protecting does not survive the disaster it is for.

## Restoring

To recover from a lost or damaged deployment: deploy a fresh stack from the same release (or a newer one), let it come up, then restore into it.

```bash
scripts/restore-omnigate.sh --from ./omnigate-backup/20261020T194147Z --kubeconfig ~/.kube/omnigate --yes
```

This **replaces** the databases in the backup and the admin console's saved settings with what is in the backup, and puts the licence back. The app
is stopped for the restore (about 40 seconds in the test) and started again. Without `--yes` the script refuses. The new deployment keeps its own
HTTPS certificate and its own deploy settings (the passwords you gave it). You can also restore over the *same* deployment, for example after a bad
change.

## What was tested

On OCI, a deployment with 100,000 rows of your own data in a new table (with a checksum), a change to the demo data, three admin-console entries and a
licence installed:

1. Both kinds of backup were taken (6 seconds running; 15 seconds consistent).
2. The stack was destroyed completely, volumes included, and a fresh stack was deployed from the same release. It started with none of the data.
3. The restore (43 seconds) brought back all 100,000 rows with the same checksum, the demo-data change, all admin-console entries and the licence
   (the deployment became the commercial edition again), and logins worked.
4. The second backup (copied while running) was restored over a deliberately damaged deployment (rows deleted) with the same result (38 seconds).
5. A running copy taken *while the admin console was being written to* still restored to a working app, holding the entries written before the
   copy (14 of 40): an earlier point in time, not a corrupted one.

The same test was then repeated on **AWS** (`eks-stack-v1.0.16`) and **Azure** (`aks-stack-v1.0.12`), each with a fresh deployment, with the same data and
the same checks:

| | Backup, running / consistent | Restore, consistent backup | Restore, running backup over damaged data | Result |
|---|---|---|---|---|
| OCI | 6 s / 15 s | 43 s | 38 s | identical to the original |
| AWS | 7 s / 21 s | 39 s | 46 s | identical to the original |
| Azure | 3 s / 12 s | 35 s | 35 s | identical to the original |

"Identical" means the 100,000 rows had the same checksum, the demo-data change, all admin-console entries, the licence (commercial edition) and the
logins were back. AWS and Azure were destroyed completely before the fresh deployment (AWS left no volumes behind).

## Not covered

- **Google Cloud** uses the same scripts and chart but was not run there. The procedure is the same; only getting `kubectl` access differs (above).
- **Several replicas with an external config database:** the settings are in the database, so the database dumps cover them. The scripts detect
  there is no data volume and say so. Not tested.
- **Large data sets:** the 100,000-row test took seconds. A multi-gigabyte database (for example the TPC-H add-on) takes proportionally longer and
  the dump file is as large as the data.
- **A restore into an older release than the one the backup came from** was not tried (the settings format may have changed); restore into the
  same release or a newer one. Restoring into a newer release than the backup was taken on was not tried either.
- **Cloud disk snapshots** (OCI block volume backups, EBS or Persistent Disk snapshots, Azure disk snapshots) are another way to protect the
  volumes; they are not part of these scripts and were not tested.
- **Scheduling** the backup, and copying it off the cluster, are left to you.
