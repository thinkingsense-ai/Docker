"""Creates and removes OCI nodes for the local-model benchmark, with a cost guard: every node carries an expiry, and `reap` terminates the expired ones.

  python3 oci_node.py plan   <shape-id> [--ttl-hours 4]          # prints the exact oci command and cloud-init; creates nothing
  python3 oci_node.py launch <shape-id> [--ttl-hours 4] --yes    # creates the node (billable); without --yes it only prints the plan
  python3 oci_node.py list                                        # benchmark nodes in the compartment, with time left
  python3 oci_node.py reap   [--yes]                              # terminates benchmark nodes past their expiry (dry run without --yes)
  python3 oci_node.py terminate <instance-ocid> --yes

Environment: OCI_COMPARTMENT_ID, OCI_SUBNET_ID, OCI_IMAGE_ID (an image for the shape's architecture; a GPU shape needs a GPU image with drivers),
OCI_AD (availability domain name), SSH_PUBKEY_FILE (default ~/.ssh/id_rsa.pub). The oci CLI must already be configured (~/.oci/config).
Guards: --ttl-hours is required in effect (default 4, at most 24); the node gets freeform tags harness=local-models and expires=<epoch>; cloud-init also
schedules a shutdown at the expiry (a backstop only: GPU and bare-metal shapes may keep billing while stopped, so `reap` TERMINATES).
Cloud-init installs Docker with get.docker.com: acceptable on a disposable benchmark node, not for anything long-lived.
Nothing here has been run against a real tenancy: the tenancy has zero GPU quota today (see the write-up). Standard library only."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = "local-models"; MAX_TTL_HOURS = 24


def shapes():
    with open(os.path.join(HERE, "shapes.json")) as f: return json.load(f)["shapes"]


def cloud_init(ttl_hours):
    minutes = int(ttl_hours * 60)
    return ("#cloud-config\nruncmd:\n  - [sh, -c, \"curl -fsSL https://get.docker.com | sh\"]\n"
            f"  - [sh, -c, \"shutdown -h +{minutes}\"]\n")


def launch_command(shape_id, env, ttl_hours, now=None, user_data_file="/tmp/cloud-init.yml"):
    """The oci CLI argument list that creates the node (pure; tested)."""
    sh = shapes()[shape_id]; o = sh.get("oci")
    if not o: raise SystemExit(f"shape '{shape_id}' has no OCI shape (it is a local target)")
    if not 0 < ttl_hours <= MAX_TTL_HOURS: raise SystemExit(f"--ttl-hours must be above 0 and at most {MAX_TTL_HOURS}")
    for k in ("OCI_COMPARTMENT_ID", "OCI_SUBNET_ID", "OCI_IMAGE_ID", "OCI_AD"):
        if not env.get(k): raise SystemExit(f"{k} is not set")
    now = int(now if now is not None else time.time()); expires = now + int(ttl_hours * 3600)
    cmd = ["oci", "compute", "instance", "launch", "--compartment-id", env["OCI_COMPARTMENT_ID"], "--availability-domain", env["OCI_AD"],
           "--subnet-id", env["OCI_SUBNET_ID"], "--image-id", env["OCI_IMAGE_ID"], "--shape", o["shape"],
           "--display-name", f"bench-{shape_id}-{now}", "--boot-volume-size-in-gbs", str(o.get("boot_gb", 200)),
           "--freeform-tags", json.dumps({"harness": TAG, "expires": str(expires)}), "--user-data-file", user_data_file,
           "--ssh-authorized-keys-file", env.get("SSH_PUBKEY_FILE", os.path.expanduser("~/.ssh/id_rsa.pub")), "--wait-for-state", "RUNNING"]
    if o.get("ocpus"): cmd += ["--shape-config", json.dumps({"ocpus": o["ocpus"], "memoryInGBs": o["memory_gb"]})]   # Flex shapes only
    return cmd


def expired(instances, now=None):
    """Instances (oci list JSON 'data') that are ours and past their expiry. An untagged or unparsable expiry is NOT ours to touch."""
    now = int(now if now is not None else time.time()); out = []
    for i in instances:
        t = i.get("freeform-tags") or {}
        if t.get("harness") != TAG: continue
        try: exp = int(t.get("expires", ""))
        except ValueError: continue
        if exp <= now and i.get("lifecycle-state") not in ("TERMINATING", "TERMINATED"): out.append(i)
    return out


def oci_json(args):
    r = subprocess.run(["oci"] + args + ["--output", "json"], capture_output=True, text=True, env={**os.environ, "SUPPRESS_LABEL_WARNING": "True"})
    if r.returncode: raise SystemExit("oci failed: " + r.stderr.strip()[:300])
    return json.loads(r.stdout or "{}").get("data", [])


def list_nodes(env):
    return [i for i in oci_json(["compute", "instance", "list", "--compartment-id", env["OCI_COMPARTMENT_ID"], "--all"])
            if (i.get("freeform-tags") or {}).get("harness") == TAG and i.get("lifecycle-state") not in ("TERMINATING", "TERMINATED")]


def terminate(ocid):
    subprocess.run(["oci", "compute", "instance", "terminate", "--instance-id", ocid, "--preserve-boot-volume", "false", "--force"], check=True,
                   env={**os.environ, "SUPPRESS_LABEL_WARNING": "True"})


def arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    if not argv: print(__doc__); return 1
    cmd, env, yes = argv[0], os.environ, "--yes" in argv
    if cmd in ("plan", "launch"):
        if len(argv) < 2: print(__doc__); return 1
        ttl = float(arg(argv, "--ttl-hours", 4)); path = os.path.join(tempfile.gettempdir(), "bench-cloud-init.yml")
        open(path, "w").write(cloud_init(ttl)); c = launch_command(argv[1], env, ttl, user_data_file=path)
        print(" ".join(map(str, c)) if cmd == "plan" or not yes else "launching ..."); print("cloud-init:\n" + cloud_init(ttl))
        if cmd == "launch" and not yes: print("(plan only: add --yes to create the node)"); return 0
        if cmd == "launch": subprocess.run(c, check=True, env={**os.environ, "SUPPRESS_LABEL_WARNING": "True"})
        return 0
    if cmd == "list":
        for i in list_nodes(env):
            left = int(i["freeform-tags"].get("expires", 0)) - int(time.time())
            print(f"{i['id']}  {i['display-name']}  {i['shape']}  {i['lifecycle-state']}  {left // 60} min left")
        return 0
    if cmd == "reap":
        gone = expired(list_nodes(env))
        for i in gone:
            print(("terminating " if yes else "would terminate ") + i["display-name"], i["id"])
            if yes: terminate(i["id"])
        print(f"{len(gone)} expired node(s)"); return 0
    if cmd == "terminate" and len(argv) > 1 and yes: terminate(argv[1]); return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
