# Smithsonian POC demo: set up and present

This is the live demo of ThinkingSense on the Smithsonian's own Open Access records. Three people use it:
an **admin** who builds and governs the subject vocabulary, a **curator** who asks across all museums, and the
**public**, who only ever see Open Access (CC0) records. Everything runs on your own machine with local models.
Nothing is sent to an outside service unless you add a cloud model key (optional, see step 5).

You do not need to know how ThinkingSense works inside. Follow the steps, then use the walkthrough at the end.

## What you need (once)

| Need | How |
|---|---|
| A Mac or Linux machine with about 16 GB of memory | The three small models and the server run together |
| Java 21 and Maven | `brew install openjdk@21 maven` (Mac) |
| Node 20 or later | `brew install node` (only to build the web screens) |
| PostgreSQL 14 or later, running locally on port 5432 | `brew install postgresql@16 && brew services start postgresql@16`. The demo expects to log in as your own user with no password (the default for a local install); set `SI_DB_USER` to use a different user. |
| llama.cpp | `brew install llama.cpp` (gives the `llama-server` command) |
| The ThinkingSense Server code | `git clone https://github.com/thinkingsense-ai/Server.git` and use the `main` branch |

This is the copy in the Docker repo (`demos/smithsonian-poc/`). `launch.sh` and `demo.sh` are written to run from the Server
repository's `demo-smithsonian-poc/` folder (they use `../target/omnigate.jar`), so copy this folder there or work from the Server repo.

## Step 1. Build the app

From the Server folder:

```bash
(cd web && npm ci && npm run build)
mvn -DskipTests package
```

This makes `target/omnigate.jar`. It takes a few minutes the first time.

The picture gallery, the vocabulary build and the model-share panel are on `main` after release v0.10.7. The published
v0.10.7 image does not have them, so build from `main`.

## Step 2. Download the three models (once, about 2 GB)

Put these files in `~/.cache/omnigate-models/` (or set `OMNIGATE_MODELS_DIR` to another folder):

| File | What it is | Where |
|---|---|---|
| `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` | The "agentic" model that writes queries | https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF |
| `qwen2.5-0.5b-instruct-q4_k_m.gguf` | The small, fast model | https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF |
| `nomic-embed-text-v1.5.Q4_K_M.gguf` | Compares subject labels | https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF |

Use the embedding model above, not a chat model: a chat model merges unrelated subjects.

## Step 3. Check, then start everything

```bash
cd demo-smithsonian-poc
./demo.sh check     # tells you what is missing, if anything
./demo.sh up        # about 30 seconds
```

`up` starts the three model servers, loads the Smithsonian sample into a Postgres database called `si_poc`, starts
the demo on port 8110, builds the subject vocabulary, and approves four demo questions. When it finishes it prints
the addresses and logins.

| Person | Address | Login |
|---|---|---|
| Admin | http://127.0.0.1:8110/admin | `admin` / `Admin-SI-1` |
| Curator | http://localhost:8110 | `curator` / `Curator-SI-1` |
| Public | http://localhost:8110 | `public` / `Public-SI-1` |

Use `127.0.0.1` for the admin and `localhost` for the Ask app. Both live on one machine, and the browser shares the
sign-in cookie between two addresses on the same name, so using different names stops them signing each other out.
These logins are for the demo only.

Other commands: `./demo.sh status` (what is running), `./demo.sh stop`, `./demo.sh reset` (clears the demo's saved
settings so the next `up` starts clean).

## Step 4. Warm it up before you present

Open the Ask app as the curator and ask any one question, so the models are loaded. The first question after a
cold start can take 20 to 30 seconds. After that the demo questions answer in 2 to 5 seconds.

## Step 5. Optional: add a cloud model

Without a key, everything runs on the local models. To let hard questions escalate to a cloud model (this is what
makes the "small model vs cloud model" split on the Models page interesting), create a `.env` file in the Server
folder with `OMNIGATE_LLM_API_KEY=<your key>` and run `./demo.sh up` again. Say so in the room: with a key, the question,
the table layout and sometimes the result rows go to the cloud provider, so this is no longer a local-only demo.

## Walkthrough (about 10 minutes)

**1. Admin: what is connected (2 min).** Sign in to the admin. Open **Data Sources**: the Smithsonian database is
there. Say: "This is 31,185 subject rows over 7,792 records from five museums, straight from Open Access."

**2. Admin: the subject vocabulary (3 min).** Open **Business Catalog**, then **Terms & ontology**, then the **Review
Queue** tab. Say: "Each museum names subjects in its own way. ThinkingSense proposed one vocabulary: 53 groups of
labels it is sure are the same, and 433 it wants a person to confirm." Show a card, use the **Keep primary** /
**Prefer secondary** / **Not a conflict** buttons (or the K, S, N keys). Say: "Nothing in the museums' data changes."
One pair worth showing: "American Civil War (1861-1865)" and "Civil War, 1861-1865" are already merged, and both
point to the same 96 records.

**3. Curator: ask across museums (2 min).** Sign in to Ask as `curator`. Ask:
*What do we hold on the American Civil War across all museums, and how much of it has an image?*
It answers from both museums (NPG 90 records, SAAM 6) with a chart and shows its checks. Then in a **new question**
ask: *Show me what the Smithsonian has about the Civil War*. You get a **gallery of pictures** with the title,
museum and a link to the record. Click a picture to enlarge it.

**4. Public: the same question, restricted (1 min).** Sign out, sign in as `public`, ask the same picture question.
Note the banner "Unofficial prototype", the same pictures, and say: "A public visitor only ever sees records marked
CC0, enforced by policy, not by trust."

**5. Admin: where answers come from (2 min).** Back in the admin, open **Settings**, then **Models**, and scroll to
**Where answers come from**. Say: "Of the questions asked, this share was answered by the small local model, this
share by the cloud model, and this share by no model at all, because a trusted question already existed." Ask a few
free-form questions as the curator first (for example *How many records have an image?*) so the bars have numbers.

## Good to know

- **Trusted questions.** The four demo questions are pre-approved, so they are fast and reliable. Free-form
  questions go to the small models and are right some of the time; the demo shows this honestly. Do not promise
  that every question works.
- **Every record in the sample is already CC0**, so the public view is not visibly narrower than the curator's.
  The rule is real and applies as soon as staff-only records are loaded.
- **The banner shows for everyone**, including the curator, because it is a server-wide setting.
- **No data leaves the machine** with the local models only. The pictures themselves load from the Smithsonian's
  public image server, so the room needs internet access for them to appear.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `./demo.sh check` says a model is missing | Download it (step 2) into `~/.cache/omnigate-models/` |
| "address already in use" in `server.log` | Another ThinkingSense is running on one of the demo's ports. `./demo.sh stop`, or stop the other one |
| The Ask app says it could not get a working query | The model needs a moment or the question is outside the data. Ask one of the four demo questions, or rephrase |
| Pictures are blank boxes | They are loading from the Smithsonian's server (a few seconds) or there is no internet |
| Admin sign-in bounces you out | Use `127.0.0.1` for the admin and `localhost` for Ask, not the same name for both |
| The review queue is empty | The vocabulary build did not run; run `./demo.sh up` again |
| You want a clean start | `./demo.sh reset` then `./demo.sh up` |

Logs are in `demo-smithsonian-poc/server.log` and `/tmp/si-demo-*.log`.

## What is in this folder

`demo.sh` (the helper), `launch.sh` (starts the app), `load-data.sh` and `load-vocabulary.sh` (the data),
`approve-demo-questions.sh` (the four trusted questions), `access-policy.yaml` (the public rule),
`data-src/` (the Open Access sample, public domain, and the script that pulled it), and `vocabulary-concepts.csv`
(the concepts from the last build, plain CSV the Smithsonian can reuse).
