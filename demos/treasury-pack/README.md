# Treasury demo pack

Corporate cash and treasury questions across two systems: the treasury database (Postgres) and the ERP (MariaDB). It is built around one idea from
J.P. Morgan's June 2026 piece "Proof of Movement: AI, Autonomy and the New Architecture of Corporate Cash": the first job is *visibility*, one
normalized view of cash, payables, hedges and debt, and the hard part is that the data lives in separate systems. **All data is invented** (company,
banks, vendors, accounts, amounts). Nothing here is from, or endorsed by, J.P. Morgan.

## Run it

```bash
export OMNIGATE_LLM_API_KEY=sk-ant-...       # your Anthropic key; answers need it
docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml up --build
```

Run it from the repository root. Ask is at `http://localhost:8080` (`demo` / `demo`); the admin console is open at `/admin` on localhost only.
Change both before the stack is reachable beyond your own machine. Stop and wipe it with `down -v`. Set `TREASURY_BANK_RETRIEVAL=false` to see
the model working without the approved questions.

A one-shot `seed-knowledge` service describes every table (including the rules a question depends on, such as when a payment breaks the
dual-approval policy or what counts as stale) and defines three named measures (`treasury-knowledge.json`). Whether this helps free-form
answers has not been measured for this pack.

Postgres holds the `treasury` schema, MariaDB the `erp` database, each registered under that name; a statement on one source runs on that database, a
statement naming both is joined across them. Tables are addressed `treasury.<table>` and `erp.<table>`.

## The data

17 tables, about 1,100 rows, six legal entities in six countries, 27 bank accounts at five banks.

- **Treasury (Postgres):** entities, banks, bank accounts, daily balances, FX rates, bank transactions, payment policy, payments, the treasury
  agent's action log, hedges, debt facilities, covenants, weekly cash forecasts with actuals.
- **ERP (MariaDB):** vendors, purchase orders, invoices, general-ledger cash entries.

Dates are relative to the day the stack first starts, so "stale" and "due in 14 days" stay true. `generate-treasury-seed.py` writes both seed files
(deterministic); `build-questions.py` writes the question files.

Traps planted on purpose, each behind at least one question:

- a bank feed that stopped six days ago (a frozen account), and three portal feeds a day or two late;
- a vendor contracted in euros that now invoices in dollars (the article's 6:47 a.m. example);
- two pairs of duplicate invoices, and an invoice with no purchase order;
- two payments released above the dual-approval limit with one approver, and a treasury-agent action taken outside its limit;
- hedges that cover euro and Singapore dollar payables but nothing in yen or pesos;
- a covenant with 3.4% headroom, and one entity whose cash forecast keeps missing by about 27%.

## The questions

`demo-questions-treasury.json` holds 24 approved questions with reference SQL, checked against the data (four read across both systems):

| Group | Questions |
|---|---|
| Visibility | consolidated cash; cash by currency, by entity, by bank (with share); stale balances; trapped cash; feeds by method |
| Reconciliation | old unreconciled ledger entries (ERP + treasury); bank transactions with no ledger match; ledger entries unreconciled though the bank booked them |
| Payables and anomalies | invoices due in 14 days; currency different from the contract; duplicates; no purchase order |
| Payments and control | payments awaiting approval; released above the dual-approval limit; agent actions outside policy; pending payments on held invoices |
| Exposure, debt, forecast | payables against hedges; hedges maturing; covenant headroom; total liquidity; forecast accuracy by entity; entities missing by over 15% |

`probe-questions-treasury.json` holds 12 reworded questions and 4 that should be declined (covenant breach in 60 days, whether to draw the revolver,
optimal hedge ratio, a bank's credit rating).

## Results (app 0.10.16, Claude Sonnet 4.5, run locally 2026-11-06)

Each question was asked through the Ask API and the returned rows compared with the reference SQL. The automatic check is strict, so a few
borderline answers count against it.

| Condition | Result |
|---|---|
| Approved questions, asked verbatim, bank on | **24 of 24** return the reference rows (8 to 14 seconds each) |
| Same questions, bank off (the model writes the SQL itself) | **11 and 9 of 24** in two runs |
| Reworded questions, bank on | **6 of 12** right on a manual read |
| Questions that should be declined | 3 of 4 declined clearly; "credit rating" got a bare "No results found" |

What the free-form runs show:

- Lookups and group-bys over one table mostly come out right. Questions needing a join across systems, a date window or a conversion to US dollars
  often do not: the total cash question was answered with 134.5 million instead of 136.7 million, and one reworded version returned a negative number.
- Date windows are the most common failure. Two questions died on a column check that read `CURRENT_DATE` and `CURRENT_TIMESTAMP` as columns of the
  table (`aa.CURRENT_TIMESTAMP does not exist`). This is drafted for the Server repo (`briefs/server-issue-drafts/`).
- A reworded forecast-accuracy question ("least reliable forecast") was refused as a prediction request, the same routing problem as Server#69.
- One approved question returned the right three rows but its narrative said "two actions" (Server#8, the answer text contradicting its own data).
- Cross-system questions (four of the 24) all run when approved. Free-form, they were the least reliable.

The pattern matches the BOM pack and Server#43: approved questions are the reliable path, free-form accuracy is the weak point, and the article's
"proof, not vibes" point is better served by saved, checked SQL plus the audit log than by letting the model improvise on money.

## What this pack does not do

The article's later layers are not in a database to ask about. ThinkingSense does not forecast, run Monte Carlo scenarios, move money or negotiate
between agents; it reads, explains and records who asked what. Questions that need a simulation or a decision are meant to be declined, and the
decline cases above check that.
