"""Starts llama-server for one model on one shape, and records exactly how.

  python3 serve.py up    <model-id> <shape-id> [--port 8091] [--engine docker|native] [--vision] [--dry-run] [--meta FILE]
  python3 serve.py down  [--name omnigate-bench-llm]
  python3 serve.py check-flags [--bin llama-server]     # every flag this harness passes must appear in the binary's --help

The command is built by build_command() (pure, tested). A result is only meaningful with its meta file: model, file hashes, shape, the full command
and, for docker, the image id, so the same run can be repeated. Memory and speed are measured by the benchmark, not assumed here.
Standard library only."""
import json, os, shlex, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "omnigate-bench-llm"


def load(name):
    with open(os.path.join(HERE, name)) as f: return json.load(f)


def server_args(entry, shape, port, model_path, mmproj_path=None):
    """The llama-server arguments (no binary, no container wrapper)."""
    a = ["-m", model_path, "--host", "0.0.0.0", "--port", str(port), "-c", str(entry.get("context", 8192)),
         "-t", str(shape["threads"]), "-ngl", str(shape["gpu_layers"]), "--parallel", str(shape["parallel"]), "--jinja"]
    a += ["--flash-attn", "on" if shape.get("flash_attn") else "off"]
    a += list(entry.get("extra_args", []))      # per-model flags, e.g. --reasoning off for Gemma 4 (it thinks by default under --jinja)
    if shape.get("split_mode"): a += ["--split-mode", shape["split_mode"]]
    if mmproj_path: a += ["--mmproj", mmproj_path]
    return a


def build_command(entry, shape, shapes_doc, port, models_dir, engine="docker", vision=False, name=NAME):
    """The full command line (a list) that starts the server. For docker the model directory is mounted read-only at /models."""
    files = entry["files"]
    if engine == "native":
        mp = os.path.join(models_dir, files["main"]["name"]); vp = os.path.join(models_dir, files["mmproj"]["name"]) if vision and "mmproj" in files else None
        return ["llama-server"] + server_args(entry, shape, port, mp, vp)
    image = shapes_doc["image"]["cuda" if shape["kind"] == "cuda" else "cpu"]
    mp = "/models/" + files["main"]["name"]; vp = "/models/" + files["mmproj"]["name"] if vision and "mmproj" in files else None
    cmd = ["docker", "run", "-d", "--name", name, "--rm", "-p", f"{port}:{port}", "-v", f"{models_dir}:/models:ro"]
    if shape["kind"] == "cuda": cmd += ["--gpus", "all"]
    return cmd + [image] + server_args(entry, shape, port, mp, vp)


def used_flags(entry, shape):
    return sorted({x for x in server_args(entry, shape, 0, "m", "p") if x.startswith("-")})


def check_flags(binary="llama-server"):
    """Returns the flags this harness passes that the binary's --help does not mention (empty list = all present)."""
    out = subprocess.run([binary, "--help"], capture_output=True, text=True).stdout
    probe = {"-m", "--host", "--port", "-c", "-t", "-ngl", "--parallel", "--jinja", "--flash-attn", "--split-mode", "--mmproj", "--reasoning"}
    return sorted(f for f in probe if f not in out)


def wait_healthy(port, seconds=900):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5).status == 200: return round(time.time() - t0, 1)
        except Exception: pass
        time.sleep(3)
    raise SystemExit(f"llama-server did not become healthy in {seconds}s (docker logs {NAME})")


def image_id(image):
    r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True)
    return r.stdout.strip() or None


def arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    if not argv: print(__doc__); return 1
    cmd = argv[0]
    if cmd == "check-flags":
        missing = check_flags(arg(argv, "--bin", "llama-server"))
        print("missing flags:", missing or "none"); return 1 if missing else 0
    if cmd == "down":
        subprocess.run(["docker", "rm", "-f", arg(argv, "--name", NAME)], capture_output=True); return 0
    if cmd != "up" or len(argv) < 3: print(__doc__); return 1
    mid, sid = argv[1], argv[2]
    models, shapes = load("models.json")["models"], load("shapes.json")
    if mid not in models or sid not in shapes["shapes"]: print("unknown model or shape"); return 1
    entry, shape = models[mid], shapes["shapes"][sid]
    port = int(arg(argv, "--port", 8091)); engine = arg(argv, "--engine", "docker"); vision = "--vision" in argv
    mdir = os.environ.get("MODELS_DIR", os.path.expanduser("~/omnigate-models"))
    command = build_command(entry, shape, shapes, port, mdir, engine, vision)
    meta = {"model": mid, "base": entry["base"], "licence": entry["licence"], "revision": entry["revision"], "files": entry["files"], "shape": sid,
            "oci_shape": (shape.get("oci") or {}).get("shape"), "engine": engine, "command": command, "vision": vision, "sampling": entry.get("sampling"),
            "thinking": entry.get("thinking"), "prompt_adapter": entry.get("prompt_adapter"), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if "--dry-run" in argv: print(shlex.join(command)); return 0
    if engine == "docker": meta["image"] = shapes["image"]["cuda" if shape["kind"] == "cuda" else "cpu"]
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True) if engine == "docker" else None
    if engine == "docker": subprocess.run(command, check=True)
    else: subprocess.Popen(command, stdout=open(os.path.join(mdir, "llama-server.log"), "w"), stderr=subprocess.STDOUT)
    meta["healthy_after_s"] = wait_healthy(port)
    if engine == "docker": meta["image_id"] = image_id(meta["image"])
    if "--meta" in argv: json.dump(meta, open(arg(argv, "--meta"), "w"), indent=1)
    print(f"{mid} on {sid} is serving on port {port} (healthy after {meta['healthy_after_s']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
