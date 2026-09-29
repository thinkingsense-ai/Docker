# Deploy OmniGate on GKE

This deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Google
Kubernetes Engine cluster. Everything below runs in this Cloud Shell session — nothing to install
locally.

**Before you continue:** you need a GCP project with billing already linked to it. The picker
below can create a brand new project for you, but a newly-created project has **no billing
account linked yet** — `setup.sh`'s billing check will stop you if you pick one of those. Easiest
path: use an existing project you know has billing enabled, or create one now at
[console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate) and link
a billing account to it (Console → Billing → Link a billing account) before coming back here.

Also note: what you need below is the project's **Project ID**, not its Project Name — GCP lets
these be different strings (e.g. name "My Project", ID "my-project-42781"), and the ID is what
`gcloud`/Terraform actually need. The picker shows both; double-check you're copying the ID.

<walkthrough-project-setup></walkthrough-project-setup>

## 1. Run the guided setup

```sh
cd omnigategkestack
./setup.sh
```

It'll prompt you for your GCP project (defaulting to the one you just picked above), region,
Ask-app login, and an Anthropic API key from
[console.anthropic.com](https://console.anthropic.com) (required — the gateway deploys fine
without one but can't answer any question). Then it enables the required APIs, writes
`terraform.tfvars` for you, and runs `terraform init && terraform apply`.

Type `yes` when `terraform apply` prompts for confirmation. Takes about 10-15 minutes — cluster
creation dominates that.

(Prefer to drive Terraform by hand instead? Copy `terraform.tfvars.example` to
`terraform.tfvars`, fill in the same values yourself, then run `terraform init && terraform
apply` directly — `setup.sh` is just that same path collapsed into one prompt-driven script.)

## 2. Access OmniGate

The script prints the `kubectl` credentials command at the end — run it, then:

```sh
kubectl get svc omnigate-omnigate-http
```

Once `EXTERNAL-IP` is populated (not `<pending>`), open `http://<that-ip>:8080/` and log in with
the username/password you set in step 1.

## 3. Clean up

```sh
./destroy.sh
```

Same idea as `setup.sh`, in reverse — run it from this same Cloud Shell directory (not a fresh
"Open in Cloud Shell" click, which clones fresh and won't have this deployment's state; see the
README's "Reconnecting to an existing deployment" section if you're coming back later to do this).
