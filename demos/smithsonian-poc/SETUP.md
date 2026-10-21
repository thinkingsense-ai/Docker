# Smithsonian POC demo: set up and present

This is the live demo of ThinkingSense on the Smithsonian's own Open Access records. Three people use it: an **admin** who builds
and governs the subject vocabulary, a **curator** who asks across all museums, and the **public**, who only ever see Open Access
(CC0) records. Everything runs on your own machine with small local models. Nothing is sent to an outside service unless you add a
cloud model key (optional, step 5).

You do not need to know how ThinkingSense works inside. Do steps 1 to 4 once (about 20 minutes, most of it waiting for a build and a
download), then use the walkthrough at the end.

**What you need:** a Mac (or Linux) with about 16 GB of memory and 5 GB of free disk, an internet connection for the first run, and
read access to the private `thinkingsense-ai/Server` repository on GitHub.

## Step 1. Install the tools (once)

Copy this whole block into Terminal (you also need **Docker Desktop** installed and running: the demo's second data source, a CSV in
object storage, runs in a small local S3-compatible container (SeaweedFS) that stands in for Amazon S3):

```bash
brew install openjdk@21 maven node llama.cpp postgresql@16
brew services start postgresql@16
```

Then check the two things that most often go wrong. Each should print what is shown.

```bash
psql -h 127.0.0.1 -d postgres -c "select 1"
```

Expected: a small table with `1`. If it asks for a password, or says it cannot connect, PostgreSQL is not ready: run
`brew services restart postgresql@16`, wait 10 seconds, and try again. The demo logs in to PostgreSQL as **your own Mac user with no
password**, which is how a local Homebrew install works by default. (To use a different database user, set `SI_DB_USER`.)

```bash
/opt/homebrew/opt/openjdk@21/bin/java -version
```

Expected: a line containing `21`. You may have a newer Java as your default (for example 25 or 27). That is fine and the next step
handles it, but **do not run the demo scripts by hand with a different default Java**; use the launcher the next step creates.

## Step 2. Get the code, build it, and download the models (once)

Download `bootstrap.sh` from this folder (or clone this repository), then:

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

It sets up in `~/smithsonian-poc` (put it somewhere else with `SI_WORKDIR=~/code/si ./bootstrap.sh`). It does these in order and
prints `ok` for each, so you can see where you are:

1. **Checks your tools** and tells you the exact fix for anything missing.
2. **Clones the ThinkingSense Server code** into `~/smithsonian-poc/Server`. If this fails, you do not have access to the private
   repository yet: ask for it, then run `gh auth login`.
3. **Builds the app** (5 to 10 minutes the first time; you will see nothing while it works, the logs are in
   `~/smithsonian-poc/build-*.log`). It makes `Server/target/omnigate.jar`.
4. **Downloads three small models** (about 1.6 GB) into `~/.cache/omnigate-models/`. If your connection drops, run `./bootstrap.sh`
   again and it resumes.
5. **Creates a launcher** called `~/smithsonian-poc/demo` that always uses Java 21 and runs from the right folder.

It is safe to run again at any time; it skips what is done. It finishes with `All set.`

> The build uses the code on the `main` branch. The picture gallery, the vocabulary build and the model-share panel are on `main`
> after release v0.10.7; the published v0.10.7 container image does not have them, so build from `main` as above.

## Step 3. Start the demo

```bash
~/smithsonian-poc/demo up
```

About 30 seconds. It starts three small model servers, loads the Smithsonian sample into a database called `si_poc`, starts the
demo on port 8110, builds the subject vocabulary, and approves five demo questions (one of them joins the database with the CSV in object storage). When it finishes you see:

```
Ready. Admin  http://127.0.0.1:8110/admin   (admin / Admin-SI-1)
       Ask    http://localhost:8110         (curator / Curator-SI-1, public / Public-SI-1)
```

| Person | Address | Login |
|---|---|---|
| Admin | http://127.0.0.1:8110/admin | `admin` / `Admin-SI-1` |
| Curator | http://localhost:8110 | `curator` / `Curator-SI-1` |
| Public | http://localhost:8110 | `public` / `Public-SI-1` |

**Use `127.0.0.1` for the admin and `localhost` for the Ask app, exactly as written.** The browser shares the sign-in cookie between two
addresses with the same name, so using one name for both signs the admin and the curator out of each other. These logins are for the demo only.

Useful commands (all through the launcher):

| Command | What it does |
|---|---|
| `~/smithsonian-poc/demo status` | shows what is running |
| `~/smithsonian-poc/demo stop` | stops the demo and its models |
| `~/smithsonian-poc/demo reset` | clears the demo's saved settings so the next `up` starts clean |
| `~/smithsonian-poc/demo check` | lists anything missing |

## Step 4. Check it works (one minute)

1. Open **http://localhost:8110**, sign in as `curator` / `Curator-SI-1`.
2. Ask: *What do we hold on the American Civil War across all museums, and how much of it has an image?*
3. You should see two museums: **NPG 90 records** and **SAAM 6**, with a chart. The first question after a cold start takes 20 to 30
   seconds while the models load; after that the demo questions answer in 2 to 5 seconds.

If you see that, you are ready. If not, go to "If something goes wrong" below.

## Step 5. Optional: add a cloud model

Without a key, everything runs on the local models. To let hard questions escalate to a cloud model (this is what makes the "small
model vs cloud model" split on the Models page interesting), create a file named `.env` in `~/smithsonian-poc/Server/` containing one
line, `OMNIGATE_LLM_API_KEY=<your key>`, and run `~/smithsonian-poc/demo up` again. Say so in the room: with a key, the question, the
table layout and sometimes the result rows go to the cloud provider, so this is no longer a local-only demo.

## Walkthrough (about 10 minutes)

**1. Admin: what is connected (2 min).** Sign in to the admin. Open **Data Sources**: there are **two**. `si` is the Smithsonian database in
PostgreSQL: 31,185 subject rows over 7,792 records from five museums, straight from Open Access. `museums` is a **CSV file in object
storage** (a local S3-compatible server standing in for Amazon S3): the museum directory, with each unit's full name, department and web site. Say:
"The records live in a database, the directory is just a file in a bucket. ThinkingSense reads both in place."

**2. Admin: the subject vocabulary (3 min).** Open **Business Catalog**, then **Terms & ontology**, then the **Review Queue** tab. Say:
"Each museum names subjects in its own way. ThinkingSense proposed one vocabulary: 53 groups of labels it is sure are the same, and 433
it wants a person to confirm." Show a card and use the **Keep primary** / **Prefer secondary** / **Not a conflict** buttons (or the
K, S, N keys). Say: "Nothing in the museums' data changes." One pair worth showing: "American Civil War (1861-1865)" and "Civil
War, 1861-1865" are already merged, and both point to the same 96 records.

**3. Curator: ask across museums (2 min).** Sign in to Ask as `curator`. Ask: *What do we hold on the American Civil War across all
museums, and how much of it has an image?* It answers from both museums (NPG 90 records, SAAM 6) with a chart and shows its checks.
Then ask *How many records does each museum hold, with its full name and department?* This one **joins the database with the CSV in
object storage** in a single question: the full museum names and departments come from the file, the counts from the database.
Then in a **new question** ask: *Show me what the Smithsonian has about the Civil War*. You get a **gallery of pictures** with the
title, museum and a link to the record. Click a picture to enlarge it.

**4. Public: the same question, restricted (1 min).** Sign out, sign in as `public`, ask the same picture question. Note the banner
"Unofficial prototype", the same pictures, and say: "A public visitor only ever sees records marked CC0, enforced by policy, not by
trust."

**5. Admin: where answers come from (2 min).** Back in the admin, open **Settings**, then **Models**, and scroll to **Where answers
come from**. Say: "Of the questions asked, this share was answered by the small local model, this share by the cloud model, and this
share by no model at all, because a trusted question already existed." Ask a few free-form questions as the curator first (for example
*How many records have an image?*) so the bars have numbers.

## Good to know

- **Trusted questions.** The five demo questions are pre-approved, so they are fast and reliable. Free-form questions go to the small
  models and are right some of the time; the demo shows this honestly. Do not promise that every question works.
- **Every record in the sample is already CC0**, so the public view is not visibly narrower than the curator's. The rule is real and
  applies as soon as staff-only records are loaded.
- **The banner shows for everyone**, including the curator, because it is a server-wide setting.
- **No data leaves the machine** with the local models only. The pictures themselves load from the Smithsonian's public image server,
  so the room needs internet access for them to appear.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `bootstrap.sh` says `MISSING` for something | Run the `fix:` command it prints, then run `./bootstrap.sh` again |
| `psql ... select 1` asks for a password or cannot connect | `brew services restart postgresql@16`, wait 10 seconds, try again. The demo needs a local PostgreSQL that lets your Mac user in without a password |
| Strange Java errors, or "unsupported class version" | You ran a script by hand with a different default Java. Use `~/smithsonian-poc/demo ...`, which always uses Java 21 |
| `demo up` prints `agentic already running on :18090` (or `fast`/`embeddings`) but nothing was started | Something else is using that port, for example a `kubectl port-forward`. Find it with `lsof -nP -iTCP:18090 -sTCP:LISTEN`, stop it, then `demo stop` and `demo up`. The demo needs ports **8110, 18090, 8092 and 8120** free |
| "address already in use" in `server.log` | Another ThinkingSense is running on port 8110. `demo stop`, or stop the other one |
| The Ask app says it could not get a working query | The model needs a moment, or the question is outside the data. Ask one of the five demo questions, or rephrase |
| Pictures are blank boxes | They load from the Smithsonian's server (a few seconds), or there is no internet |
| Admin sign-in bounces you out | Use `127.0.0.1` for the admin and `localhost` for Ask, not the same name for both |
| The review queue is empty | The vocabulary build did not run; run `demo up` again |
| You want a clean start | `demo reset` then `demo up` |

Logs are in `~/smithsonian-poc/Server/demo-smithsonian-poc/server.log` and `/tmp/si-demo-*.log`.

## Where things live

```
~/smithsonian-poc/
  demo                         the launcher you run (always Java 21)
  build-web.log, build-app.log build logs
  Server/                      the ThinkingSense Server code (cloned)
    target/omnigate.jar        the built app
    demo-smithsonian-poc/      the demo kit: demo.sh, launch.sh, load-data.sh, load-vocabulary.sh,
                               approve-demo-questions.sh, access-policy.yaml, data-src/, vocabulary-concepts.csv
~/.cache/omnigate-models/      the three small models
```

`demo-smithsonian-poc/` in the Server repository and `demos/smithsonian-poc/` in the Docker repository hold the same kit. If you prefer to
do the steps by hand instead of `bootstrap.sh`: install the tools (step 1), `git clone` the Server repository, run
`(cd web && npm ci && npm run build)` and `mvn -DskipTests package` in it with Java 21, download the three models (see `bootstrap.sh`
for the exact files), then run `./demo.sh up` from `Server/demo-smithsonian-poc/` with Java 21 first on your path.
