# Sounds demo pack (open bird and fish recordings, structured side)

72 recordings (48 bird, 24 fish) with who recorded them, where, when, the call type and the licence, 25 species, and Smithsonian NMNH specimen counts for the 8 bird species.
Real, open data: Xeno-canto (via GBIF) and FishSounds, all non-commercial licences; **only metadata is in this repo**, the audio is fetched by `../multimodal-poc/fetch_data.py` into a git-ignored cache.
This is the structured half of the multimodal work in `../multimodal-poc` (audio and image models are tested there).

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...
docker compose --project-directory . -f demos/sounds-pack/docker-compose.sounds.yml up --build   # from the repository root
```

**With audio vectors (optional, one command).** `demos/sounds-pack/up-with-vectors.sh [plain|defined]` starts the same pack on a pgvector Postgres with `sounds.recording_embeddings` (the CLAP vectors) loaded, so Ask can answer
"Which 3 recordings sound most like xc1072993, and what species are they on record?" (checked live: it ranks by cosine distance and joins the curated species). The vectors are not committed (they derive from non-commercial recordings): the script makes them
once with `../multimodal-poc/embed_audio.py` (needs `fetch_data.py` first, and torch + transformers). It cannot answer a question phrased only as text ("sounds like a crow alarm call"): the app has no way to turn text into a vector yet (Server#95). Note the example: the nearest recordings to an American Robin are a Song Sparrow and two chickadees, which is the 32% same-species result in the multimodal README, not a bug.

**With audio upload (optional).** `demos/sounds-pack/up-with-vectors.sh --audio` also runs the audio service (`../audio-demo`: BirdNET + CLAP) and sets `OMNIGATE_AUDIO_IDENTIFY_URL` on the app (`docker-compose.audio.yml`), so a clip attached in Ask (.wav .mp3 .flac .ogg .m4a) is identified and the answer cites the species, the nearest recordings and their licences; the `audio_url` column in results shows a play button. It needs an app image that has audio upload (Server#100; until that is released the variable is ignored) and an admin to grant the user "upload files". The Name That Sound page is on http://localhost:8090 at the same time. Models (about 1.2 GB) download once into the `audio-models` volume; the audio and vectors stay local (non-commercial).

`build_pack.py` regenerates `seed-sounds.sql` (with table and column comments, where the app reads descriptions), `demo-questions-sounds.json` (24 questions with reference SQL) and `sounds-knowledge.json` from `../multimodal-poc/manifest/`.
Tables: `sounds.recordings`, `sounds.species`, `sounds.licenses`, and `sounds.model_annotations`.

`sounds.model_annotations` holds **model output, kept apart from the curated data**: BirdNET's top three guesses per bird recording (288 possible rows, 286 present), in two scopes
(`all`: unaided; `expected`: restricted to the 8 species expected for the place and season), with the model's confidence. Made by `../multimodal-poc/birdnet_annotate.py`.
The recordist's species in `recordings.species` stays the reference; a question like "where does the model disagree with the record" is a join between the two. Facts the table shows:
restricted to the expected species the best guess matches 46 of 48; unaided it puts a different species first at 0.8 or more confidence in 10 recordings; and the mean confidence of right and wrong best guesses is almost the same
(0.896 against 0.882), so confidence cannot be used as the trust signal on its own.

## Free-form results (Sonnet 4.5, question bank off, 3 runs, `demos/benchmark`, 2026-11-15)

15, 13, 16 of 17 (first run set; one correct answer was scored wrong by a truncated judge reply, now fixed) and 13, 16, 15 of 17 after cleaning the fish call types and fixing the judge.
12 of 17 questions right in all runs. Every needed table and description was shown for 17 of 17. What fails:

- **A zero-row answer** ("Which recordings can be used commercially?", correct answer: none): the model lists recordings anyway in 2 of 3 runs, treating non-commercial licences as usable.
- **Grouping granularity**: "Which fish species have more than one recording, and what call types do they have?" is wrong in all 3 runs: the model groups by species and call type, so a species with two recordings of different call types disappears. Not a data problem.
- **Output shape**: one aggregated row expected, 24 individual rows returned; or one group (birds) dropped from a two-group answer.

## With the model-annotation table (24 questions, Sonnet 4.5, question bank off, 3 runs, 2026-11-15)

Seven questions about BirdNET's labels were added (best guess against the species on record, confident wrong labels, agreement per species joined to specimen counts, alarm calls against songs).

| Variant | Original 17 | New 7 | Right in every run (of 24) |
|---|---|---|---|
| `model_annotations` with plain comments | 15, 15, 16 | 5, 6, 6 | 19 |
| + comments saying "what the model said / got right / got wrong means rank 1; ranks 2 and 3 are alternatives" | 15, 14, 15 | **7, 7, 7** | 21 |

- **One missing sentence cost two of seven questions.** Without it the model read "the species BirdNET got right" and "labelled with a different species" as *any of the top three guesses* and returned 42 rows
  where 18 were expected, or reported 6 of 6 Blue Jay recordings right where 4 were. With the rule in the table and column comments both questions are right in every run. This is what the governed ontology is for: *which of the model's rows is the model's answer* is a business definition, not something the column names say.
- **The new table did not disturb the old questions** (15, 14, 15 against 13 to 16 before): an extra table with annotated columns was not a distraction.
- **Still failing, unchanged by this work:** the zero-row licence question and the fish "more than one recording" grouping (see above). Rules for the new questions in `../benchmark/benchmark-sounds.json` were written by hand, not drafted by a model.
- **Judge:** haiku-5-5, as before. The v3/v4 runs used the same data and the same day's reference rows.

## How far can annotations go? A ceiling run (24 questions, Sonnet 4.5, 3 runs)

`experiments/ceiling-comments.sql` adds comments that state the business rules behind the three questions that fail in every other variant (zero rows is a valid answer; count per species, not per call type; both groups appear). A deliberately question-shaped upper bound, not shipped.

| Variant | Runs (of 24) | Right in every run | Still failing |
|---|---|---|---|
| Rank-1 comment (shipped) | 22, 21, 22 | 21 | licence zero-row, fish grouping, no-country shape (1 of 3) |
| + ceiling comments | **23, 23, 23** | **23** | fish grouping |

- **Stating the rule fixes the zero-row licence question and the dropped bird group.** "Every licence here is non-commercial, so the answer is empty: say so" turns a hallucinated list into the right empty answer.
- **It does not fix the fish grouping, even with the rule written out.** "Which fish species have more than one recording, and what call types do they have?" is still grouped by species and call type (a species whose two recordings have different call types disappears). The question's own words ("and what call types") pull the grouping; a comment cannot overrule that. That is a prompt or planner matter (Server#93), not an annotation matter.

## A vector column in the pack (`experiments/make_vector_sql.py`, 5 questions, Sonnet 4.5, 3 runs each)

`sounds.recording_embeddings` (pgvector, the CLAP audio vectors) added to the pack; questions anchored on a recording that is already in the table ("Which 5 recordings sound most like xc1072993?", the same-species share of those, the nearest that allows derivatives, species and country of the nearest 3, a count by group).

| Variant | Runs (of 5) |
|---|---|
| Plain comments ("Audio embedding of each recording.") | 5, 5, 5 |
| Comments that define the vector (model, distance, never select it, species is not the same as sound) | 5, 5, 5 |

- **The first attempt failed for a reason nobody would guess from the column list:** the app connects with `currentSchema=sounds`, so pgvector's `<=>` operator, installed in `public`, is not found (`operator does not exist: public.vector <=> public.vector`), for the model's SQL and for the reference SQL alike. The extension has to be installed in the schema the app searches (`CREATE EXTENSION vector SCHEMA sounds`) or `public` added to the connection's search path. This is a deployment fact the semantic layer cannot describe, so the onboarding check has to catch it.
- **With the operator visible, a recording-anchored similarity question needs no special annotation:** the model writes `ORDER BY embedding <=> (SELECT embedding ...)` unaided. The wording of the vector comments did not change the score at five questions. What it cannot do is a question phrased as text ("sounds like a crow alarm call"): that needs a query vector made from the text by the same model, which the app has no way to do yet.
