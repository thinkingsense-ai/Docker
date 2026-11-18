# Local-model harness

Measures how well a *local* model writes SQL for the 24 + 24 Treasury and BOM benchmark questions, on a named piece of hardware, so "answer locally, escalate to a foundation
model below some confidence" can use a measured accuracy instead of a guess. It adds to `demos/benchmark/` and reuses its questions, logging proxy, runner and judge.
Background, candidates and the OCI resources it needs are in the write-up *Local models first, foundation model on escalation*.

## What is here

| File | What it does |
|---|---|
| `models.json` | The candidate models: repository, **pinned commit**, per-file **SHA-256**, licence, base model, context, sampling, thinking notes |
| `shapes.json` | Hardware targets: the OCI shape to launch, and the `llama-server` settings for it (threads, GPU layers, parallelism, flash attention) |
| `fetch.py` | Downloads a model's files and **refuses** anything unpinned, unlicensed or with a wrong hash; resumes; never sends a token to a CDN |
| `serve.py` | Starts `llama-server` (Docker or native) for a model on a shape; writes a meta file (command, hashes, image id); `check-flags` verifies flag names |
| `override-local.yml` | Compose override: the app in `local-only` mode talks to the local server through the logging proxy |
| `run_local.sh` | One model on one shape, end to end: fetch, serve, run the benchmark, stop |
| `report.py` | `summary` (accuracy, time, tokens per model and shape) and `calibrate` (escalation threshold vs measured accuracy) |
| `oci_node.py` | Creates a benchmark node on OCI with a mandatory expiry, lists them, and **reaps** expired ones |
| `tests/` | 23 tests, no network or cloud needed (`python3 -m unittest discover -s demos/benchmark/local-models/tests`) |

Small hooks were added to `tools/`: `llmproxy.py` forwards to `LLM_UPSTREAM` (default Anthropic), `run_variant.sh` takes `BENCH_OVERRIDE`, and `bench_run.py` records each
question's `confidence` and whether it `escalated`. Existing runs behave as before.

## Run one model

On the node (or on this laptop with shape `local-docker`; Docker needs at least 8 GB for a 4B model):

```bash
export ANTHROPIC_API_KEY=sk-ant-...            # the judge only; the local run never calls a hosted model
demos/benchmark/local-models/run_local.sh qwen3-4b-q4km x86-cpu-16 treasury 3
python3 demos/benchmark/local-models/report.py summary /tmp/bench-out treasury_base_qwen3-4b-q4km-x86-cpu-16
```

Vision and audio (`--vision`) download the multimodal projector as well; leave it off for the SQL runs.

## Calibrate the escalation threshold

Run the same pack with the frontier model the existing way (`tools/run_variant.sh treasury base 3`, result tag `treasury_base_sonnet-4-5` with `BENCH_MODEL=claude-sonnet-4-5`), then:

```bash
python3 demos/benchmark/local-models/report.py calibrate /tmp/bench-out treasury_base_qwen3-4b-q4km-x86-cpu-16 treasury_base_sonnet-4-5
```

It prints, per threshold, the share kept locally, the accuracy of the kept answers, and the blended score if the rest escalate, and names the lowest threshold within one question
(`--tolerance`) of the frontier model alone. If no threshold qualifies it says so. That is a valid result.

## On OCI

```bash
export OCI_COMPARTMENT_ID=... OCI_SUBNET_ID=... OCI_IMAGE_ID=... OCI_AD=...        # an image for the shape's architecture; GPU shapes need drivers
python3 demos/benchmark/local-models/oci_node.py plan x86-cpu-16 --ttl-hours 4      # prints the command; creates nothing
python3 demos/benchmark/local-models/oci_node.py launch x86-cpu-16 --ttl-hours 4 --yes
python3 demos/benchmark/local-models/oci_node.py reap --yes                          # run it from cron too: terminates expired benchmark nodes
```

Every node is tagged `harness=local-models` with an expiry, capped at 24 hours; `reap` touches only nodes with that tag and a parsable, passed expiry.
CPU quota exists in the tenancy; **GPU quota is zero today**, so the GPU shapes cannot launch until it is granted.

## Add a model

1. Find the GGUF repository and copy its latest commit (`https://huggingface.co/api/models/<repo>`, field `sha`).
2. Copy each file's SHA-256 from `https://huggingface.co/api/models/<repo>/tree/main` (`lfs.oid`).
3. Add the entry to `models.json` with the licence tag and the *base* model; a third-party conversion says so in `source`.
4. Read the licence of the base model; counsel records it in the licence register before the model is bundled anywhere.

## Checked and not checked

Checked: the 23 unit tests; a real download from Hugging Face with the CDN redirect and the hash check (and the bad-hash path); every `llama-server` flag used exists in the real
`ghcr.io/ggml-org/llama.cpp:server` image (both `server` and `server-cuda` tags exist for amd64 and arm64); the commands that `serve.py` and `oci_node.py` build.

**Not checked:** serving a model and running the benchmark through it (nothing downloaded beyond a 60 MB test file); any OCI launch (no GPU quota; no node created); CUDA serving;
the Server's name for the confidence field in its answer events (`bench_run.py` takes the first event key containing "confidence"; confirm it on the first live run, or `calibrate`
will say it found none); the app accepting a local server at `OMNIGATE_ASSISTANT_REMOTE_HOST` in `local-only` mode on v0.10.21 (documented in `docs/llm-configuration.md`, never run here).

**Found live on the first node (fixed):** the app probes its local model with `GET /health` at boot, so the logging proxy must pass GET through (it now does, with a test); the Ubuntu OCI image's host firewall drops container-to-host traffic, so `run_local.sh` opens port 9099 to the Docker bridge range; cloud-init now adds the `ubuntu` user to the docker group; and the local override keeps the host's real API key out of the app container.

**Known gaps:** no prompt adapter for the SQL-specialist models (Arctic-Text2SQL-R1 was trained on SQLite `CREATE TABLE` prompts; its first score is recorded as *unadapted*); no
Arctic 14B GGUF found; Docker image tags should be replaced by digests before a result is quoted (the meta file records the image id used); GPU shape names are from Oracle's
published families and are not visible in this tenancy until quota exists (`shape_listed_in_tenancy` in `shapes.json`).
