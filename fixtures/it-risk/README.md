# IT & operational risk demo pack (draft)

A demo data set and a list of trusted questions for a mid-size financial firm's technology and operational risk. Everything is invented. It is the first of two risk packs (the second is insurance risk); the shape follows the manufacturing demo.

**Status: draft for review. Not wired into any stack yet.** The questions are checked only in the sense that each reference query runs and returns rows on a local Postgres; nobody has asked them through the Ask app. On app v0.10.14 the Ask app answers most multi-table questions wrongly or not at all (thinkingsense-ai/Server#43), so these questions will not work in a demo until that is fixed.

## Files

- `seed-it-risk.sql` creates three schemas, one data source each: `governance` (risk register, risk appetite, controls, key risk indicators and their monthly readings, audit issues), `operations` (business services with recovery objectives, applications, outages) and `security` (third-party vendors, vulnerabilities).
- `demo-questions-it-risk.json` has twelve trusted questions with the reference SQL that defines the right answer, in the same format as `demo-questions-manufacturing.json`.

Dates are relative to the day the script runs, so "overdue" and "last 12 months" stay meaningful soon after install and drift as the data ages. The key risk indicator readings for the current month are typed in to agree with the data on the day of writing (7 controls overdue, 4 overdue audit issues, 5 critical vulnerabilities past deadline, 549 tier-1 outage minutes in 90 days, 3 vendors unassessed); they do not recompute.

## Vocabulary used (from public frameworks, to be checked against what JPMC described)

Business service with a tier and recovery time/point objectives (RTO/RPO); risk register with inherent and residual score (likelihood x impact); risk appetite per category; control (preventive, detective, corrective) with a test frequency and last test result; key risk indicator with amber and red thresholds; third-party tier and assessment age; patch deadline against severity; audit issue with a due date.

## To do before this ships

1. Check the vocabulary and the twelve questions against the JPMC conversation.
2. Wire into the four charts the way `manufacturingDemo` is (init container, `demo-questions` seeding, a `demoDataset` setting).
3. Run the accuracy script against it (needs `questions.json` for this pack) after Server#43 is fixed.
4. Ask-app pack selector (Server issue), and the data-source count: three packs side by side need more than the free edition's three sources.
