"""Creates and removes Google Cloud (GCE) nodes for the local-model benchmark, with a cost guard: every node carries an expiry, GCE itself deletes it at that time, and `reap` deletes any left over.

  python3 gce_node.py plan   <shape-id> [--ttl-hours 4] [--spot]        # prints the exact gcloud command and startup script; creates nothing
  python3 gce_node.py launch <shape-id> [--ttl-hours 4] [--spot] --yes   # creates the node (billable); without --yes it only prints the plan
  python3 gce_node.py list                                                # benchmark nodes in the project, with time left
  python3 gce_node.py reap   [--yes]                                      # deletes benchmark nodes past their expiry (dry run without --yes)
  python3 gce_node.py delete <instance-name> [--zone ZONE] --yes
  python3 gce_node.py images                                              # lists the GPU-ready (Deep Learning VM) image families to put in GCE_IMAGE_FAMILY

Environment: GCP_PROJECT (default: the gcloud project), GCP_ZONE (default us-central1-a; the zone must offer the machine type: `gcloud compute machine-types list --filter=name=<type>`),
GCE_IMAGE_FAMILY and GCE_IMAGE_PROJECT (a CPU shape defaults to Ubuntu 24.04 LTS; a GPU shape MUST set both: use a Deep Learning VM family with the NVIDIA driver, see `images`),
GCE_NETWORK and GCE_SUBNET (optional; the default network is used when neither is set), SSH_PUBKEY_FILE (default ~/.ssh/id_rsa.pub; the key is installed for the user `ubuntu`, which queue.sh and push_repo.sh expect).
Guards: --ttl-hours is required in effect (default 4, at most 24). The node gets labels harness=local-models and expires=<epoch>, AND `--max-run-duration` with `--instance-termination-action=DELETE`,
so Google deletes the VM (and its boot disk) at the expiry even if this script is never run again. `reap` is the second line of defence for a node whose limit was removed.
The startup script installs Docker with get.docker.com (acceptable on a disposable benchmark node, not for anything long-lived) and, on a GPU node, the NVIDIA container toolkit when `nvidia-smi` works.
Nothing here has been run against a real project: GPU quota is 0 until the quota request in gce_quota.py is approved and the billing account is a paid one. Standard library only."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = "local-models"; MAX_TTL_HOURS = 24
CPU_IMAGE = {"amd64": ("ubuntu-2404-lts-amd64", "ubuntu-os-cloud"), "arm64": ("ubuntu-2404-lts-arm64", "ubuntu-os-cloud")}


def shapes():
    with open(os.path.join(HERE, "shapes.json")) as f: return json.load(f)["shapes"]


def startup_script(kind):
    s = ("#!/bin/bash\nset -eu\ncurl -fsSL https://get.docker.com | sh\n"
         "id ubuntu >/dev/null 2>&1 && usermod -aG docker ubuntu || true\n")
    if kind == "cuda":
        s += ("if nvidia-smi >/dev/null 2>&1; then\n"
              "  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg\n"
              "  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#' > /etc/apt/sources.list.d/nvidia-container-toolkit.list\n"
              "  apt-get update && apt-get install -y nvidia-container-toolkit && nvidia-ctk runtime configure --runtime=docker && systemctl restart docker\n"
              "fi\n")
    return s


def launch_command(shape_id, env, ttl_hours, now=None, startup_file="/tmp/bench-startup.sh", spot=False, pubkey=None):
    """The gcloud argument list that creates the node (pure; tested)."""
    sh = shapes().get(shape_id) or {}
    g = sh.get("gcp")
    if not g: raise SystemExit(f"shape '{shape_id}' has no Google Cloud machine type (it is a local target or not mapped)")
    if not 0 < ttl_hours <= MAX_TTL_HOURS: raise SystemExit(f"--ttl-hours must be above 0 and at most {MAX_TTL_HOURS}")
    project = env.get("GCP_PROJECT")
    if not project: raise SystemExit("GCP_PROJECT is not set")
    zone = env.get("GCP_ZONE", "us-central1-a")
    family, image_project = env.get("GCE_IMAGE_FAMILY"), env.get("GCE_IMAGE_PROJECT")
    if sh["kind"] == "cuda" and not (family and image_project):
        raise SystemExit("a GPU shape needs GCE_IMAGE_FAMILY and GCE_IMAGE_PROJECT (a Deep Learning VM image with the NVIDIA driver): run `gce_node.py images`")
    if not family: family, image_project = CPU_IMAGE[sh["arch"]]
    now = int(now if now is not None else time.time()); ttl_s = int(ttl_hours * 3600); expires = now + ttl_s
    cmd = ["gcloud", "compute", "instances", "create", f"bench-{shape_id}-{now}", "--project", project, "--zone", zone,
           "--machine-type", g["machine_type"], "--image-family", family, "--image-project", image_project,
           "--boot-disk-size", f"{g.get('boot_gb', sh.get('oci', {}).get('boot_gb', 200))}GB", "--boot-disk-type", "pd-balanced",
           "--labels", f"harness={TAG},expires={expires}",
           "--max-run-duration", f"{ttl_s}s", "--instance-termination-action", "DELETE",
           "--metadata-from-file", f"startup-script={startup_file}" + (f",ssh-keys={pubkey}" if pubkey else "")]
    if g.get("accelerator"): cmd += ["--accelerator", f"type={g['accelerator']['type']},count={g['accelerator']['count']}"]
    if sh["kind"] == "cuda": cmd += ["--maintenance-policy", "TERMINATE"]                 # a GPU VM cannot live-migrate
    if spot: cmd += ["--provisioning-model", "SPOT"]
    if env.get("GCE_NETWORK"): cmd += ["--network", env["GCE_NETWORK"]]
    if env.get("GCE_SUBNET"): cmd += ["--subnet", env["GCE_SUBNET"]]
    return cmd


def expired(instances, now=None):
    """Instances (gcloud list JSON) that are ours and past their expiry. An unlabelled or unparsable expiry is NOT ours to touch."""
    now = int(now if now is not None else time.time()); out = []
    for i in instances:
        t = i.get("labels") or {}
        if t.get("harness") != TAG: continue
        try: exp = int(t.get("expires", ""))
        except ValueError: continue
        if exp <= now and i.get("status") not in ("STOPPING", "TERMINATED"): out.append(i)
    return out


def gcloud_json(args):
    r = subprocess.run(["gcloud"] + args + ["--format=json"], capture_output=True, text=True)
    if r.returncode: raise SystemExit("gcloud failed: " + r.stderr.strip()[:300])
    return json.loads(r.stdout or "[]")


def project_of(env):
    if env.get("GCP_PROJECT"): return env["GCP_PROJECT"]
    r = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True)
    return r.stdout.strip()


def list_nodes(project):
    return [i for i in gcloud_json(["compute", "instances", "list", "--project", project, f"--filter=labels.harness={TAG}"]) if i.get("status") not in ("STOPPING", "TERMINATED")]


def zone_of(i): return (i.get("zone") or "").rsplit("/", 1)[-1]


def delete(project, name, zone):
    subprocess.run(["gcloud", "compute", "instances", "delete", name, "--project", project, "--zone", zone, "--quiet", "--delete-disks=all"], check=True)


def arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    if not argv: print(__doc__); return 1
    cmd, yes = argv[0], "--yes" in argv
    env = dict(os.environ); env["GCP_PROJECT"] = project_of(env)
    if cmd in ("plan", "launch"):
        if len(argv) < 2: print(__doc__); return 1
        ttl = float(arg(argv, "--ttl-hours", 4)); path = os.path.join(tempfile.gettempdir(), "bench-startup.sh")
        shape = shapes().get(argv[1]) or {}
        open(path, "w").write(startup_script(shape.get("kind", "cpu")))
        keyfile = os.path.expanduser(env.get("SSH_PUBKEY_FILE", "~/.ssh/id_rsa.pub")); sshmeta = None
        if os.path.exists(keyfile):
            sshmeta = os.path.join(tempfile.gettempdir(), "bench-ssh-keys"); open(sshmeta, "w").write("ubuntu:" + open(keyfile).read().strip() + "\n")
        c = launch_command(argv[1], env, ttl, startup_file=path, spot="--spot" in argv, pubkey=sshmeta)
        print(" ".join(map(str, c))); print("startup script:\n" + startup_script(shape.get("kind", "cpu")))
        if cmd == "launch" and not yes: print("(plan only: add --yes to create the node)"); return 0
        if cmd == "launch": subprocess.run(c, check=True)
        return 0
    if cmd == "list":
        for i in list_nodes(env["GCP_PROJECT"]):
            left = int((i.get("labels") or {}).get("expires", 0)) - int(time.time())
            print(f"{i['name']}  {zone_of(i)}  {i['machineType'].rsplit('/', 1)[-1]}  {i['status']}  {left // 60} min left")
        return 0
    if cmd == "reap":
        gone = expired(list_nodes(env["GCP_PROJECT"]))
        for i in gone:
            print(("deleting " if yes else "would delete ") + i["name"], zone_of(i))
            if yes: delete(env["GCP_PROJECT"], i["name"], zone_of(i))
        print(f"{len(gone)} expired node(s)"); return 0
    if cmd == "delete" and len(argv) > 1 and yes: delete(env["GCP_PROJECT"], argv[1], arg(argv, "--zone", env.get("GCP_ZONE", "us-central1-a"))); return 0
    if cmd == "images":
        for i in gcloud_json(["compute", "images", "list", "--project", "deeplearning-platform-release", "--no-standard-images", "--filter=family~'^common-cu.*ubuntu'", "--sort-by=~creationTimestamp", "--limit", "10"]):
            print(f"{i.get('family')}  (image project: deeplearning-platform-release)")
        return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
