# Multimodal POC: audio and image sources next to structured data

Status: spike, 2026-11-15. Question being tested: can recordings (birds, fish) and their spectrogram images be queried together with
structured records (species, place, date, Smithsonian specimen holdings) through the same semantic layer, and how good are the
annotations a model can add to them? Builds on the free-form findings (`../benchmark/free-form-annotation-report.pdf`): what the model is
shown about a source decides the answer, so model-made annotations are the thing to measure first.

## Data (open, no API key)

| Source | What | Licence | In `manifest/` |
|---|---|---|---|
| Xeno-canto via GBIF | 48 bird recordings, 8 species x 6: species, behaviour (song, call, alarm), place, date, mp3, spectrogram | per recording; all 48 are CC BY-NC-SA 4.0 or BY-NC-ND | `recordings.csv` |
| FishSounds (Borealis, doi:10.5683/SP2/TACOUX) | 24 fish recordings, 17 species: species and call type from the file name, wav, spectrogram | CC BY-NC 4.0 | `recordings.csv` |
| NMNH Extant Specimen Records via GBIF | Smithsonian specimen counts for the same 8 bird species | CC0 / CC BY | `usnm_specimens.csv` |

Audio and images go to `cache/` (git-ignored; all are non-commercial, so use them for internal testing and do not redistribute them).
`python3 fetch_data.py` rebuilds everything (about 500 MB). Xeno-canto's own API now needs an account key; GBIF serves the same recordings without one.

## First measurements (CLAP `laion/clap-htsat-unfused`, first 10 s of each clip, `embed_audio.py`)

| Test | Result | Chance |
|---|---|---|
| Bird or fish, zero-shot from text | 83% of 72 | 50% |
| Which of 8 bird species, zero-shot from common name | 27% of 48 | 12% |
| Nearest other recording has the same species (birds) | 48% | about 11% |
| Same, fish (17 species, 24 clips) | 25% | about 6% |

Reading: a general audio-text model separates the groups and finds similar-sounding clips well enough for "recordings like this one" search,
but it cannot be trusted to name a species. Species annotations should come from a bird-specific classifier or from the curated metadata, and
the semantic layer should keep the two apart (observed metadata versus model-suggested labels, with a confidence). Small sample (8 species,
6 clips each, one prompt wording); treat as direction, not a benchmark.

## BirdNET against the same 48 bird clips (`birdnet_eval.py`, BirdNET V3.0 via `pip install birdnet`)

| Test | CLAP (general audio-text model) | BirdNET V3.0 |
|---|---|---|
| Species right, all of BirdNET's 11,560 species open | not applicable | 37 of 48 (77%) |
| Species right, restricted to the 8 candidate species | 13 of 48 (27%) | 46 of 48 (96%) |

- A bird-specific classifier does what the general model could not: it names the species. Per species (restricted): 6 of 6 for seven species, 4 of 6 for Blue Jay.
- Open-set errors can be confident: an American Robin clip came back as Brown-backed Solitaire at 0.85 (a thrush with a similar song). A model label needs its confidence and
  its alternatives next to it, and should not overwrite the curated species column.
- Restricting to an expected species list (here the 8, in practice the species known for the place and season) is worth about 19 points. That is a structured-data input to the model, which is the kind of join the semantic layer is for.
- **Licence:** the BirdNET code is MIT but its models are CC BY-NC-SA 4.0 (non-commercial; the project counts research and education as non-commercial). Fine for this research spike, not for a commercial product without a different licence or model.
- Same caveats: 48 clips, 8 species, first run, clips are the ones the dataset's contributors considered good examples of the species. Not a field-accuracy figure.
- Running it: BirdNET starts worker processes, so it must run as a script file with a main guard (a stdin script crashes with an unhelpful "producer exited" error).

## Vector search in Postgres (pgvector, `vector_search.py`)

The CLAP embeddings (512 numbers per clip) are loaded into `sounds.recording_embeddings` (`vector(512)`, cosine distance `<=>`) in a `pgvector/pgvector:pg16` database that also holds the sounds pack, so one SQL statement can rank by sound and filter or join on the curated metadata.
Run `python vector_search.py` after `embed_audio.py` (needs Docker; it starts and removes its own container).

| Test | Result |
|---|---|
| pgvector's top 5 against brute-force numpy (72 queries, then one hybrid query) | identical every time: the engine is exact |
| Audio to audio, birds: same species among the 5 nearest recordings | 32% (chance about 7%) |
| Audio to audio, fish: same species among the 5 nearest | 9% (24 recordings over 17 species: most have no same-species neighbour, so read this as "does not find them") |
| Text to audio, "the song of a <bird>": precision at 5 | 30% (chance 8%); top hit right for 3 of 8 species; American Crow 4 of 5, Blue Jay and Song Sparrow 0 of 5 |
| Hybrid: nearest to "a loud alarm call", birds in the USA, derivatives allowed, joined to specimen counts | correct rows and join; but 0 of the 5 are alarm calls (only 1 recording is labelled one, so this is not a fair test of the text) |

- **The database part works; the embedding part is the limit.** CLAP is a general audio model and is the weak link: BirdNET gets the species right for 46 of 48 clips where CLAP's nearest neighbour manages about half. For species, search BirdNET's labels (the annotation table); use CLAP vectors for "sounds like this" and for kinds of sound that have no species label.
- **Filters before ranking** (licence, country, group) are plain SQL and exact at this size. With millions of rows an HNSW or IVFFlat index makes the search approximate, and a filter that removes most rows can return fewer than the requested number; that needs testing at scale.
- **What the semantic layer has to say about it:** a vector column is not a fact. The comment must say what the vector is, which model made it, that distances only compare vectors from the same model, and that a smaller distance means "sounds more alike", not "same species". `recordings.species` stays the answer to species questions.
- **Licence:** the embeddings are derived from non-commercial recordings. They are not committed (`out/` is ignored); regenerate with `embed_audio.py`.

## Use cases to test (questions, with the answer checked against the manifest)

1. **Structured only, over the new tables:** "How many recordings do we have per species, and from which countries?"; "Which bird recordings are alarm calls?"
2. **Cross-source join:** "For each bird species with a recording, how many Smithsonian specimens does NMNH hold, and how many have coordinates?" (recordings join specimen counts).
3. **Model annotation as a column:** "Which recordings does the model label as fish?" with the model label and score shown next to the recorded metadata; checked against `group`.
4. **Similarity (vector):** "Find recordings that sound like XC<id>" (nearest neighbours in CLAP space), answered with their species, place and date.
5. **Audio plus semantics:** "Which recordings from the same country as this one sound similar and were recorded in the same month?" (vector search constrained by structured filters).
6. **Image side:** the spectrogram images embedded with an image model (CLIP) and queried the same way; compare with audio embeddings for the same clips.
7. **Governance:** the licence column decides what may be shown to the public persona (non-commercial recordings only to staff).

Pass criteria per use case: reference answer from the manifest, same-day, at least three runs for any generated SQL (as in `../benchmark`); for similarity,
top-3 contains the same species at least as often as the baseline above.

## Next steps

- ~~Pack database and structured questions~~ done: `../sounds-pack`.
- ~~Embeddings in pgvector~~ done (`vector_search.py`, section above). Open: let the app ask a vector question (a tool or connector that turns text into a query vector), and try a better audio model than CLAP for retrieval.
- ~~Expose BirdNET as a model-annotation table~~ done: `birdnet_annotate.py` writes `manifest/birdnet_annotations.csv`; the table `sounds.model_annotations` in `../sounds-pack` joins it to the curated metadata (use case 3), with 7 questions in the benchmark.
- Image embeddings for the spectrograms (use case 6).
