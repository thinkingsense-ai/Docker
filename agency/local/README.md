# Agency on this machine (a design sandbox)

All six packs, the thinking layer with the new UI, the table, document and image adapters, upload sharing, the pack Workspaces and a set of demo logins, in Docker on your laptop.
**Local only**: fixed demo logins in a public repository; nothing here is meant to be reachable beyond your own machine.

```bash
agency/local/up.sh            # start (first run: several minutes, it builds the images and downloads the app, the embedding model and the museum sample)
agency/local/up.sh layer      # after changing addons/thinking-layer or agency/web: rebuild and restart only the layer and its UI
agency/local/up.sh down       # stop and wipe the data
export OMNIGATE_LLM_API_KEY=sk-ant-...   # before up.sh, for free-form questions; without it the approved questions still work
```

| What | Where |
|---|---|
| Agency | http://localhost:8097 |
| Ask (for comparison) | http://localhost:8080 |
| Admin console | http://localhost:8080/admin (`admin` / `Admin-SI-1`) |

| Login | Password | Can |
|---|---|---|
| `curator` | `Curator-SI-1` | see everything, SQL and sources, upload files, start workflows |
| `alice` | `demo` | upload, start workflows |
| `bob`, `carol` | `demo` | upload, approve workflows |
| `public` | `Public-SI-1` | the restricted view (Smithsonian Open Access records only, no uploads, no workflows) |

Sign in as different people in different browser profiles (or private windows) to try sharing an upload and the two-person approval.

What `up.sh` does: the all-packs stack (`docker-compose.yml` + `demos/all-packs/docker-compose.packs.yml`) on the app release the repository pins, `addons/thinking-layer` and the three adapters, then `bootstrap.py`, which loads `packs/workspaces.yaml` into the Server (`PUT /api/config/groups`) and sets each login's grants through the admin API. It is safe to run again.

## Workflows need the commercial edition

The app's workflow API is a commercial-edition feature. For design work only, an untracked file `agency/local/commercial.override.yml` (ignored by git, see `.gitignore`) runs the app image as the commercial edition on this laptop with the app's own development switches and its built-in workflow **simulator**: the rules and recommendation text are canned (`workflow-manifest.json`), and write-back is always a dry run. If the file is not there, `up.sh` starts without it and the workflow screens stay hidden ("Workflows off" in the header). Do not publish or ship it; real workflows need a licensed deployment (see `demos/payment-workflow` for the Temporal version).

## What to know while designing

- Layer sessions are in memory: restarting the layer (including `up.sh layer`) signs everyone out.
- Uploaded files, shares and preferences are in the layer's memory too, and uploads expire after an hour (`AGENCY_UPLOAD_HOURS`).
- Approved questions answer from the question bank; the first one after a start can take 10 to 15 seconds while models load.
- The audio adapter (BirdNET + CLAP, non-commercial, about 1 GB of models) and the Bird and fish sounds pack are not part of this sandbox; their card shows as "Docker only".
- Free-form questions need a real model key; with the dummy key they will fail.
