# Free-form accuracy benchmark

A repeatable way to measure how well the app writes SQL for questions nobody has approved, on the Treasury and BOM demo packs, and to see *why* it
gets some wrong. It exists because one score from one run cannot tell a real improvement from noise: the same question flips between right and
wrong from run to run.

## What is here

| File | Purpose |
|---|---|
| `benchmark-treasury.json`, `benchmark-bom.json` | The 24 + 24 pack questions with their reference SQL, tags (tables, joins, relative dates, cross-source...), the business rules each answer depends on (drafted by a model from the reference SQL: review before relying on them), clarified wording (`ask`) for 5 ambiguous questions, and notes on 3 reference defects (`referenceNote`) |
| `tools/run_variant.sh` | One variant end to end: stack up (question bank **off**), reference rows, N judged runs, context report, stack down |
| `tools/llmproxy.py` | Logging pass-through proxy between the app and the model API: every prompt and reply is kept, so a wrong answer can be traced to what the model was shown |
| `tools/bench_run.py` | Asks each question in a fresh session and records the answer, the SQL and which logged calls belong to it |
| `tools/reference_rows.py` | Runs the reference SQL on the running stack, so the answer key has the *same day's* data (the packs' dates move with the day they first start: an answer key from another day marks date questions wrong) |
| `tools/judge.py` | A model grades each answer against the reference rows (same entities and figures; ignores order, extra columns, ids vs names, rounding) |
| `tools/summarize.py`, `tools/context_report.py`, `tools/classify_failures.py` | Compare variants; check which tables and descriptions the model was shown; name the cause of each never-right question |
| `tools/gen_comments.py` | Writes each table's description as `COMMENT ON TABLE` (see below) |

```bash
export ANTHROPIC_API_KEY=sk-ant-...
demos/benchmark/tools/run_variant.sh treasury base 3               # three runs, no table comments
demos/benchmark/tools/run_variant.sh treasury comments 3 --comments  # the same, with the descriptions written into the database
python3 demos/benchmark/tools/summarize.py /tmp/bench-out treasury_base_haiku-5-5 treasury_comments_haiku-5-5
```

Run at least three times per variant. Report the range, not one number. Need Docker, Python 3 with the `anthropic` package, free ports 8080 and 9099.
About 10 minutes per run for Treasury and 13 for BOM; Haiku 5.5 costs a few cents per run.

## Results (app 0.10.17, Claude Haiku 5.5, 2026-11-14)

Questions asked as in `benchmark-*.json` (5 with clarified wording), question bank off, three runs per variant, judged by Haiku 5.5 against same-day reference rows.

| | Runs (of 24) | Mean | Right in every run | Sometimes | Never |
|---|---|---|---|---|---|
| Treasury, no comments | 12, 10, 13 | 11.7 | 9 | 5 | 10 |
| Treasury, descriptions as table comments | 15, 16, 15 | **15.3** | 14 | 2 | 8 |
| BOM, no comments | 11, 13, 13 | 12.3 | 11 | 2 | 11 |
| BOM, descriptions as table comments | 14, 15, 15 | **14.7** | 13 | 3 | 8 |

- **The descriptions were not reaching the model.** The app's SQL prompt shows a table's *database* comment (`COMMENT ON TABLE`) and column comments. The descriptions the
  packs load into the ontology (`*-knowledge.json`, the Admin console) are not read for SQL: a table description appeared in **0 of 48** question prompts. That is why the
  packs' descriptions showed no measurable benefit before. Written as database comments they appear in 48 of 48 and the score rises by about 3.7 (Treasury) and 2.3 (BOM) questions of 24.
- **A cost of making them visible.** With comments, 5 Treasury questions were refused in all three runs ("single-table steps failed"), against none without. The app splits a question into one
  step per table when five or more tables from more than one database are retrieved, then refuses unless every step succeeds, and a step for an irrelevant table rightly says it cannot answer.
  Two of those five were right in every run before. See `Server` note `docs/design/free-form-accuracy-findings.md`.
- **The model was shown the tables the reference needs for 19 of 24 (Treasury) and 21 of 24 (BOM) questions**, with about 8 to 12 tables offered where 2.4 to 4.6 are needed.
- **Caveats.** Haiku 5.5 only. The descriptions were written by the people who wrote the data, so this is closer to a ceiling than to what a customer's own comments would give. Three runs
  per variant; the Treasury ranges do not overlap, the BOM ranges barely do. A control without the proxy (fresh stack, no comments) scored 15 and 13 on Treasury, about two questions above the proxied baseline;
  that difference is within the run-to-run spread, but treat absolute levels as uncertain by about two questions and trust the comparisons between variants run the same way.

## Defects in the pack questions found while building this

- BOM "Which material is used by the most parts?": the reference returns the top 5 materials; the benchmark asks for "the five materials".
- Treasury "How many open accounts are fed by API, file and portal?": the reference counts every account that is not Closed (Frozen included) while the knowledge file says only Open accounts count. The benchmark asks for "accounts that are not closed".
- Treasury "How accurate were the weekly cash forecasts ... over the last 12 weeks?": the reference has no 12-week window.
