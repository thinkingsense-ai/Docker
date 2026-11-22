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

## Guided tour (Quickstart)

With the layer's `AGENCY_DEMO_TOUR=on` (the sandbox's `docker-compose.risk-gateway.yml` sets it, with `AGENCY_DEMO_PERSONAS` listing `curator`, `alice`, `bob` and `carol` and their demo passwords) the header shows a **Quickstart tour** button. It opens a panel that walks the seven acts of the demo (watch, problem record, exposure, priorities, register, notifications, audit): for each step it signs in as the right demo person (the layer holds the passwords; the browser never sees them), opens the screen, says what to tell the audience and what to look at, and presses the same buttons a person would. **Play the whole demo** runs every step with a pause between; **Step by step** runs one at a time (Back, Next, Run it again, Stop). The script is `agency/web/src/tourScript.ts`; the buttons it presses carry `data-tour` attributes.

- Every workflow run can be started once, and each finished run leaves a decision-record entry and a register row, so a rehearsal uses them up. Run `AGENCY_PROJECT=agency-risk agency/local/reset-demo.sh` before each rehearsal (it keeps the feed history, the estate and the approved questions). The panel warns when the first run already exists.
- On a window 1100 px or wider the panel is docked as a right-hand column so it never covers the screen being shown; below that it floats (Minimise helps). The start page checks the Server, workflows, the four demo people and the first run id before it lets you play.
- A step whose button is not there (already done in this sandbox) is marked Skipped and play goes on (the end says how many). A step that errors or whose result does not arrive in time is marked "Needs a look" and **play pauses** with Retry, Skip and Stop, because later steps depend on it. The sign-in page names the demo people when the tour is on.
- Local sandbox only. Never set `AGENCY_DEMO_TOUR` on a real deployment: it lets anyone who can reach the layer sign in as those people.
- Answers come from the real Server. With the local CPU model each step can take up to a minute, and the whole demo some ten to twenty minutes.
