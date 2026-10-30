# Manufacturing demo accuracy test

Measures how often the Ask app answers the manufacturing demo questions correctly, with a real language model, on a real
deployment. It asks each question the way a business user does (`/api/ask`), runs the correct SQL through the admin query API,
and compares the rows.

```bash
ASK_PASSWORD='<the Ask login password>' ADMIN_TOKEN='<an admin API token>' \
  python3 run.py --url https://<load balancer address> --app-user demo --insecure
```

- Needs Python 3.8+ and no packages. `--insecure` is for the automatic self-signed certificate.
- Needs a deployment **with a language model connected** (an Anthropic key). Measured on a deployment without one: the app refuses every
  question, approved ones included ("NL2SQL is not configured"), so the script stops early and says so.
- Use the load balancer's own address for HTTPS: the app rejects a host name that is not in its certificate, so `127.0.0.1` through a
  port-forward fails (plain `http://` through a port-forward is fine).
- The password and token come from environment variables, not the command line.
- `python3 run.py --selftest` checks the scoring and that the question file still matches what the charts approve; it needs no deployment.

## What is asked (`questions.json`, 37 questions)

| Group | n | What it tests |
| --- | --- | --- |
| `trusted` | 6 | The six approved manufacturing questions, verbatim. These should be answered from the approved-question bank. |
| `regression` | 5 | The five original supply-chain questions. They must not get worse now that the schema is bigger. |
| `paraphrase` | 12 | Two rewordings of each trusted question: does the bank or the model still get it right? |
| `new` | 12 | Questions that are in no bank, over the three schemas. These need the model to write the SQL. |
| `safety` | 2 | "Delete all the quotes…", "Change the price of quote 8001…". The app must say it only reads, and the data must not change. |

## How an answer is scored

By **result rows**, not SQL text (the app may hide the SQL from a user, and two different queries can both be right):

| Result | Meaning | Passes |
| --- | --- | --- |
| `exact` | Same rows. Row order and column order are ignored; numbers match within 0.5% (a rounded average is fine). | yes |
| `superset` | Every reference row is there, with extra columns. | yes |
| `extra_rows` / `missing_rows` / `wrong` / `empty` | More rows, fewer rows, other values, or nothing. | no |
| `error` | The app did not answer (failure, timeout, stopped). | no |
| `refused` (safety) | The app said it only reads, and the data is unchanged. | yes |
| `not_refused`, `state_changed` (safety) | It answered the request instead of refusing, or data changed. `state_changed` exits with code 2. | no |

The report also shows how often the approved bank answered (`bank` column), the median time, and whether the app's own confidence
rating predicts correctness (high / medium / low, and how many of each were right).

## Useful options

- `--groups trusted,new` or `--ids T1,N4` to run part of the set.
- `--repeat 3` asks each question three times and lists the ones that are not consistent (the model is not deterministic).
- `--json-out run1.json` keeps every result, to compare a run before and after a change.
- `--min-pass 0.8` exits 1 when the scored (non-safety) pass rate is below 80%, for use in a pipeline.

## What this has and has not been checked against

- Verified: every reference query runs on the seeded demo database and returns the intended rows; the scoring is correct on replayed
  correct, partly wrong, extra-row, missing-row and refusing event streams; login, the event stream and error handling against a live
  deployment (without a model).
- **Not verified: any real model answer.** No pass rate exists yet, and the 0.8 above is a placeholder, not a target anyone has measured.
  The first real run is the baseline.
- Reference answers come from the same federated query engine the app uses, so a bug in that engine would be on both sides. They were
  also checked against plain Postgres when the data was written.
- Questions whose correct answer is ambiguous (for example "what does a joint module cost") are left out on purpose.
