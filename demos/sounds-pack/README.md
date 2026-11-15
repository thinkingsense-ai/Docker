# Sounds demo pack (open bird and fish recordings, structured side)

72 recordings (48 bird, 24 fish) with who recorded them, where, when, the call type and the licence, 25 species, and Smithsonian NMNH specimen counts for the 8 bird species.
Real, open data: Xeno-canto (via GBIF) and FishSounds, all non-commercial licences; **only metadata is in this repo**, the audio is fetched by `../multimodal-poc/fetch_data.py` into a git-ignored cache.
This is the structured half of the multimodal work in `../multimodal-poc` (audio and image models are tested there).

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...
docker compose --project-directory . -f demos/sounds-pack/docker-compose.sounds.yml up --build   # from the repository root
```

`build_pack.py` regenerates `seed-sounds.sql` (with table and column comments, where the app reads descriptions), `demo-questions-sounds.json` (17 questions with reference SQL) and `sounds-knowledge.json` from `../multimodal-poc/manifest/`.
Tables: `sounds.recordings`, `sounds.species`, `sounds.licenses`.

## Free-form results (Sonnet 4.5, question bank off, 3 runs, `demos/benchmark`, 2026-11-15)

15, 13, 16 of 17 (first run set; one correct answer was scored wrong by a truncated judge reply, now fixed) and 13, 16, 15 of 17 after cleaning the fish call types and fixing the judge.
12 of 17 questions right in all runs. Every needed table and description was shown for 17 of 17. What fails:

- **A zero-row answer** ("Which recordings can be used commercially?", correct answer: none): the model lists recordings anyway in 2 of 3 runs, treating non-commercial licences as usable.
- **Grouping granularity**: "Which fish species have more than one recording, and what call types do they have?" is wrong in all 3 runs: the model groups by species and call type, so a species with two recordings of different call types disappears. Not a data problem.
- **Output shape**: one aggregated row expected, 24 individual rows returned; or one group (birds) dropped from a two-group answer.
