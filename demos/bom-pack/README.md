# BOM / sourcing demo pack

A mechanical bill-of-materials and sourcing dataset, for showing ThinkingSense on the kind of questions a manufacturing or hardware
company asks: what is in a product, what it costs, who can make it, and what happens when a supplier has a problem. **All data is invented**
(companies, part numbers, prices, quality records). It is separate from the smaller `manufacturing` pack, which stays as it is.

Modelled on the kinds of questions in a public BOM knowledge-graph demo (cost reduction, custom-to-catalog substitution, compliant
re-sourcing, supply risk, engineering-change impact). The data, schema and questions here are our own.

## Run it

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...       # your Anthropic key; answers need it
docker compose --project-directory . -f demos/bom-pack/docker-compose.bom.yml up --build
```

Run it from the repository root. Ask is at `http://localhost:8080` (`demo` / `demo`, who can see the generated SQL); the admin console is open at `/admin` on localhost only.
Change both before the stack is reachable beyond your own machine. Stop and wipe it with `down -v`.

The stack is Postgres (the `bom` schema, loaded from `seed-bom.sql`), ThinkingSense reading it through a SELECT-only account, a small
embedding model that matches new questions to approved ones, and a one-shot job that approves the 24 questions below, and another that describes every table and defines three named measures (`bom-knowledge.json`). Tables are addressed
`bom.<table>`. Set `BOM_BANK_RETRIEVAL=false` to see the model working without the approved questions.

## The data

22 tables, about 640 rows: 3 products from 2 customers (a robot arm, a survey drone, a hydraulic pump unit), 12 assemblies, 42 parts
(custom, catalog and standard), 13 catalog items, 188 supplier quotes across 14 facilities, certificates, machines, work orders,
nonconformances, engineering changes, supply events, purchase orders, inventory and design-for-manufacturing findings.
`generate-bom-seed.py` writes `seed-bom.sql` (deterministic); `build-questions.py` writes the question files.

Traps in the data that the questions depend on:

- Detroit's AS9100 certificate lapsed on 2026-03-31. The dates are fixed, so certificates that run to 2027 will start to lapse next year.
- Mississauga (97%) and Wichita (96%) are at capacity and cannot take new work.
- Shenzhen has an active high-severity fire.
- The drone (SK-9) needs AS9100 and North American sourcing; Kestrel Dynamics has not approved two suppliers.
- A catalog part counts as a substitute only if material, type, finish, tolerance and size all fit, the part is not critical, it costs less,
  and, for the aerospace product, the distributor holds AS9120.
- "Current source" is the cheapest landed price (unit cost plus tariff), chosen without regard to certificates or capacity.

## The questions

`demo-questions-bom.json` holds 24 approved questions in five groups, each with reference SQL checked against the data:

| Group | Questions |
|---|---|
| Look up | parts in a product; part counts by source type; unit BOM cost against target; most-used material |
| Sourcing and risk | valid AS9100 facilities; facilities at capacity; active disruptions; single-quote parts; Shenzhen fire impact; ECO impact; SK-9 parts from uncertified plants |
| Quality and supply | nonconformance cost by root cause; late deliveries by supplier; parts below safety stock; scrap rate by facility; unapproved suppliers; longest lead time |
| Planning | catalog substitutions and saving; annual saving at product volume; why other parts cannot be substituted; cheapest compliant source for the SK-9; SK-9 parts with no compliant source; SK-9 cost if re-sourced; safe design-for-manufacturing savings |
| Should decline | `probe-questions-bom.json`: return on ad spend, employee salary, next-quarter lead time (no such data) |

## Results on app 0.10.17 (2026-11-13)

Re-run on 0.10.17, the release that partly fixes Server#43, with the same questions. Each answer was graded by an LLM judge (Claude Haiku 5.5)
against the rows from the approved, checked SQL, ignoring row order, extra columns, ids shown instead of names and rounding. This is a fairer
grader than the strict match behind the 0.10.16 table below, so use the like-for-like rows here to compare versions: 0.10.16 and 0.10.17 were
both run on 2026-11-13 with the same model and grader.

| Condition | 0.10.16, Sonnet 4.5 | 0.10.17, Sonnet 4.5 | 0.10.17, Haiku 5.5 |
|---|---|---|---|
| Approved questions, asked verbatim, bank on (24) | 24 of 24 | 24 of 24 | 24 of 24 |
| Bank off, model writes the SQL (24, two runs) | 7 and 7 | 10 and 7 | 13 and 10 |
| Reworded planning and lookup questions, bank on (11) | 3 | 2 | 3 |
| Questions the data cannot answer (3) | 3 declined | 3 declined | 3 declined |
| Model cost per free-form question (list price, Sonnet 4.5 price assumed $3/$15 per million tokens) | about $0.032 | about $0.041 | about $0.003 |

What this says:

- **0.10.17 shows no reliable gain on BOM free-form accuracy.** 10 and 7 of 24 against 7 and 7 is within the run-to-run spread (the 10 and
  the 7 are the same configuration). Release notes quote 18 to 23 of 37 for manufacturing on cloud models; this pack is a different question set.
- **Haiku 5.5 scored at least as well as Sonnet 4.5** (13 and 10 of 24) at roughly a twelfth of the model cost per question. Two runs only.
- Reworded questions remain the weak spot (2 or 3 of 11 in every configuration).
- The decline cases behave correctly on 0.10.17, though by the model's own judgement (some by giving up on writing SQL, some by saying the data is missing)
  rather than by an answerability check (Server#60).
- Free-form questions use about 6 model calls each and about 8,500 input tokens per question in total; no prompt caching is used.

## Earlier results (app 0.10.16, Claude Sonnet 4.5, run locally 2026-11-05, strict row match)

Each question was asked through the Ask API and the returned rows compared with the reference SQL.

| Condition | Result |
|---|---|
| Approved questions, asked verbatim, bank on | **24 of 24** return the reference rows |
| Same questions, bank off (the model writes the SQL itself) | **12 of 24** correct, 2 partly, 10 wrong or unanswered |
| Reworded planning and lookup questions, bank on | **2 of 11** correct |
| Questions the data cannot answer | **3 of 3** declined with a reason |

Reading these honestly:

- "Verbatim with the bank on" shows that an approved question runs its saved, checked SQL quickly (10 to 16 seconds). It does not show the
  system understands the question; reworded versions mostly fall back to the model, which is the second row.
- Without the bank, the model does well on lookups and single joins (12 of the first 17) and fails on the multi-rule planning questions
  (catalog substitution, compliant re-sourcing, cost under re-sourcing: 0 of 6 correct). It returned the right answer text in several cases
  but with duplicate rows from a needless join (Q6, Q15), and it misread "approved" as "not approved" (Q16).
- One planning question was blocked because its wording contained "forecast"; the predictive-question screen refused it. Reworded to
  "using each product's annual volume" it ran. Worth keeping in mind when writing demo questions.
- The three decline cases behaved correctly, but there is no pre-flight check; the model decides, and one (the salary question) was
  refused only after the model gave up on writing a query. This is Server#60 (answerability check, not yet released).

This is the same pattern as Server#43: free-form accuracy is the weak point, and approved questions are the reliable path. The
planning questions are the ones worth turning into approved questions or metrics before a customer demo.

## Does describing the tables help?

Tried: a plain-language description for all 22 tables (including rules such as "a supplier is not approved when its status is anything but
'approved'" and "a certificate is valid when expires_on is today or later") and three named measures. Five full free-form runs, scored
automatically against the reference rows (stricter than the manual count above): **8, 7 and 6 of 24 with them, 6 and 7 without.** That is
inside the run-to-run noise, so no benefit is claimed. They stay because they make the admin ontology readable. The failures that remain
are in the app, not in the pack's data or descriptions: multi-rule questions never come out right (0 of 6 in every run), and the same
question flips between right and wrong from run to run. Two concrete defects found along the way are filed against the app: a repair that swaps `CURRENT_DATE` for a hard-coded date (Server#68; the
`CURRENT_DATE()` part is fixed in Server#67), and the word "forecast" sending a data question to the predictive tier (Server#69). Free-form accuracy
in general is Server#43.
