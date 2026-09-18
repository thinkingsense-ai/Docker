# Deploy OmniGate on GKE

This deploys OmniGate (NL2SQL gateway) with a seeded Postgres demo backend onto a new Google
Kubernetes Engine cluster. Everything below runs in this Cloud Shell session — nothing to install
locally.

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
terraform destroy
```
