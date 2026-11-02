# IT & operational risk demo pack (draft)

A demo data set and a list of trusted questions for a mid-size financial firm's technology and operational risk. Everything is invented. It is the first of two risk packs (the second is insurance risk); the shape follows the manufacturing demo.

**Status: draft for review. Wired into the four stack charts as `demoDataset=it-risk` (not on the deploy forms; deployed once on GKE, 2026-11-02: it installs and seeds, 4 of 12 questions answered correctly through Ask).** The questions are checked only in the sense that each reference query runs and returns rows on a local Postgres; nobody has asked them through the Ask app. On app v0.10.14 the Ask app answers most multi-table questions wrongly or not at all (thinkingsense-ai/Server#43), so these questions will not work in a demo until that is fixed.

## Files

- `seed-it-risk-postgres.sql` creates one Postgres schema, `risk`: business services with recovery objectives, applications, outages, risk register, risk appetite, controls and their tests, key risk indicators and their monthly readings, audit issues.
- `seed-it-risk-mariadb.sql` creates one MariaDB database, `security`: third-party vendors and vulnerabilities.
- `demo-questions-it-risk.json` has twelve trusted questions with the reference SQL that defines the right answer, in the same format as `demo-questions-manufacturing.json`. Four of them (patch deadlines by service, unassessed critical third parties by service, vendors behind the most tier-1 services, tier-1 services with an open critical vulnerability and an outage) join across the two databases; the rest stay inside one.

## Two data sources, on purpose

The free edition allows three data sources (connectors). This pack uses two, one Postgres and one MariaDB, so the demo also shows federation. A live test on a GKE stack (2026-11) found three constraints, which is why the layout looks like this:

- Register each source under the same name as its schema or database (`risk`, `security`). For MariaDB the app qualifies tables with the source's name, so any other name produces SQL that fails.
- A cross-database join only sees a source's default schema, so each source holds a single schema. Several Postgres schemas behind one source work for questions inside that source, but not in a join to another source.
- Register with `OMNIGATE_BACKENDS` entries `risk=jdbc:postgresql://...?currentSchema=risk|...` and `security=jdbc:mariadb://.../security|...`, and `OMNIGATE_ROUTER_SCHEMA_RULES=risk:risk,security:security`.

Another pack side by side needs its own Postgres source, which leaves no room for more than that on the free edition; it is not decided how to fit the insurance pack.

Dates are relative to the day the script runs, so "overdue" and "last 12 months" stay meaningful soon after install and drift as the data ages. The key risk indicator readings for the current month are typed in to agree with the data on the day of writing (7 controls overdue, 4 overdue audit issues, 5 critical vulnerabilities past deadline, 549 tier-1 outage minutes in 90 days, 3 vendors unassessed); they do not recompute.

## Vocabulary used (from public frameworks, to be checked against what JPMC described)

Business service with a tier and recovery time/point objectives (RTO/RPO); risk register with inherent and residual score (likelihood x impact); risk appetite per category; control (preventive, detective, corrective) with a test frequency and last test result; key risk indicator with amber and red thresholds; third-party tier and assessment age; patch deadline against severity; audit issue with a due date.

## To do before this ships

1. Check the vocabulary and the twelve questions against the JPMC conversation.
2. Add `demoDataset` to the deploy forms if we want customers to choose it. A GKE deploy (2026-11-02) found and fixed two chart bugs (the MariaDB wait, the question seeding); the other three clouds have not run it live.
3. Run the accuracy script against it (needs `questions.json` for this pack) after Server#43 is fixed.
4. Ask-app pack selector (Server issue), and the data-source count (see above).
5. The reference SQL is checked on Postgres only (both halves loaded into one database). The MariaDB half has not been run against the reference SQL through the federation planner outside the live test.
