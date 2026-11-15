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

- Load `recordings.csv` and `usnm_specimens.csv` into a new pack database and register it as a source; write the 5 to 10 questions above with reference SQL (use cases 1, 2, 7 need no model).
- Add embeddings as a table (pgvector) and a small tool that returns the nearest neighbours (use cases 4, 5).
- Try a bird-specific classifier (for example BirdNET) against the same 48 clips and compare with CLAP's 27%.
- Image embeddings for the spectrograms (use case 6).
