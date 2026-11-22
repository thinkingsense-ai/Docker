# IT-risk pilot (step 8h)

Measures how often a risk partner agrees with what the rules did. `docs/agency-risk-register-plan.md` section 7; the rules themselves are described in `docs/it-risk-rules-description.md`.

## Run it

Needs the sandbox (or any stack with the `rca`, `estate` and `register` schemas) and an admin API token for the Server's governed query path:

```bash
set -a; . agency/local/.runtime/tokens.env; set +a; export ASK_ADMIN_TOKEN=$AGENCY_ADMIN_API_TOKEN
python3 demos/it-risk-pilot/pilot.py export --out demos/it-risk-pilot/out --sample 40 --seed 1
```

That writes three CSV sheets and `manifest.json` into `out/` (git-ignored, because the sheets name real headlines):

| Sheet | What it holds | The person fills in |
|---|---|---|
| `feed-raised.csv` | every event under review the feed raised (headline, source, claim type, link) | `leo_label`: `relevant`, `not_for_us` or `not_real` |
| `feed-not-raised.csv` | a seeded random sample (default 40) of the reporting and official headlines the feed did NOT raise | the same label: what they would have raised |
| `priorities.csv` | our ranked systems with each reason | `leo_rating` (Critical, High, Medium, Low) and `leo_rank` (their order of the top ten; blank allowed) |

Labels: **relevant** = a real story that bears on AI-driven attack or weakness and on a firm like ours; **not_for_us** = real but not for a firm like ours; **not_real** = not an incident (opinion, promotion, rumour). Case, spaces and dashes are ignored. A blank is left out and counted; an unreadable label is reported, never guessed.

When the sheets are filled in:

```bash
python3 demos/it-risk-pilot/pilot.py score --dir demos/it-risk-pilot/out
```

writes `results.json` and `results.md` (also printed). Tests: `python3 -m unittest demos/it-risk-pilot/test_pilot.py` (15, no network).

## Sending the sheets to a reviewer: the blind bundle

The three sheets above show OUR answers (rating, rank, reasons, which headlines the feed raised). Giving those to the person who is judging would anchor them, so do not send them. Build a blind bundle instead:

```bash
python3 demos/it-risk-pilot/pilot.py bundle --dir demos/it-risk-pilot/out --to demos/it-risk-pilot/out/bundle
```

`1-headlines.csv` shuffles the raised stories and the not-raised sample into one sheet with neutral ids (H01, H02, ...); `2-systems.csv` lists the systems alphabetically with their facts, without our rating, rank or reasons. Send those two files with `for-the-reviewer.md` (instructions, about 30 to 45 minutes). **Keep `out/key.json`**: it maps the ids back and is never put in the bundle. When the reviewer returns the two files:

```bash
python3 demos/it-risk-pilot/pilot.py merge --dir demos/it-risk-pilot/out --returned PATH_TO_RETURNED_FILES
python3 demos/it-risk-pilot/pilot.py score --dir demos/it-risk-pilot/out
```

`merge` puts their labels back on the right rows and reports any id that is missing or that we did not send. The bundle's sources of bias are limited, not removed: the reviewer still sees real headlines and our systems' facts, and a person can sometimes guess a feed's habits.

## What is measured

- **Feed precision** of what it raised (real and relevant; real at all), with a 95% Wilson interval.
- **Feed recall, as an ESTIMATE:** from the not-raised sample, scaled to the population, with the range the sample allows. It only counts headlines the feed read.
- **Priorities, Critical and High only:** precision (of ours, how many he agreed are Critical or High) and recall (of his, how many we caught), the systems we disagreed on, a confusion table by rating, exact and within-one-step agreement.
- **Order:** top-ten overlap, exact positions and Kendall tau-b between his order and ours.
- **No target false-positive rate**, as Leo asked: the report gives numbers and intervals, not a pass or a fail.

## Honest limits

- The samples are small; the intervals are the result, not the point values. 12 raised events and 40 sampled headlines cannot support a precise recall.
- **No labels have been collected.** Nothing here has been run on a real person's judgement; the scorer is tested only on planted labels (hand-worked expected values), and the export only on the local sandbox.
- The systems are an invented estate of 11, so "top ten" is nearly the whole list, and the priorities result says how the rules read a simulated firm, not a real one.
- The feed sheet shows each event's lead headline and link, not article text (none is stored); a person may need to open the link.
- A pilot on real data needs the stack's real feed history and a real estate; the schema and the scorer would not change.
