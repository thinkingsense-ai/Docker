# Agency IT-risk: register, priorities and regulatory clocks (plan, step 8 and after)

Status: plan, written 2026-11-21, nothing built. It replaces the old step 8 ("pilot hardening") in `docs/agency-it-risk-flow.md` section 9 with a longer sequence, using the answers Leo and Kumar wrote into the shared report ("AI-driven IT risk: taxonomy, levels and regulation", Claude doc `NvgtKHscscczqe8tpjmQ5v`). Facts about outside standards below are ours from general knowledge unless marked checked.

## 1. What Leo and Kumar answered, and what we decided

| Topic | Answer | What we do |
|---|---|---|
| TRP | Points to a public article on technology risk prioritization (fetched 2026-11-21). It is a method, not a standard: a ranked list from likelihood, impact, asset criticality, dependencies, time pressure and remediation effort, with **escalation triggers that override the score**, a treatment and a named owner for each priority, re-scored as things change. It cites NIST SP 800-30, FAIR and the CISA KEV catalogue. | Build the ranked list as "Priorities" (section 4). Expected-loss ranges (FAIR) are later. |
| BRP | Not answered. | Keep a business-impact column, empty until a firm supplies its business services. |
| "CISP" | CIS Controls. | Map controls to CIS Controls v8 (check the current version number before use) next to NIST CSF 2.0. |
| Taxonomy | Adapt from NIST SP 800-37 rev 2 and the public L1 to L3 examples pasted in the doc (Technology and System Risk; Information Security and Cyber Risk; Compliance as a peer L1). That pasted text is an AI search summary: input, not authority. | Section 2. |
| Rating scale | Four values: Critical, High, Medium, Low. | One shared scale module. **Exposure today says "Moderate"; it becomes "Medium"** (UI, Python port, gold set). |
| Material | "Later." Think of it as an incident that reaches the press as bad news. | Not built. The clock display (section 5) waits on it. |
| Inherent / residual | Show inherent plus the control evidence; the second line judges. | We never compute residual. |
| Likelihood inputs | Yes to all: EPSS, CISA KEV, internet exposure, an expert band. | Section 4. |
| Loss event | Money lost at a bank; a denial of service to a large set of customers; an attack that breaches data and creates legal risk. | Written into the taxonomy as the definition of an L1 event. |
| False positives | No target number. Focus first on Critical and High items that lead to material and inherent risk. | Measure precision and recall **for Critical and High only** (section 7). |
| Regulator clock | "You make a decision." | DORA first, MAS second (section 5). |
| ServiceNow, Datadog | Server connectors are fine, but history must be kept. Kumar asked whether that is a connector or a REST stream. | Section 6; it is a question back to Kumar. |
| Three lines | Three roles, not three Workspaces. | Section 3. |
| Decision-record export | Yes: signed, complete, filterable by control; Kumar says open a Server PR if needed. | Section 8, Server PR S2. |
| Window functions (Server#139) | "No known limit." | We have a counterexample; #139 stands. Priority queries avoid window functions until it is fixed. |
| Governed register | "Govern with users and roles; suggest changes." | Section 3. |

## 2. Taxonomy and vocabulary (step 8a)

- **L1 / L2 / L3** from the examples in the doc: L1 Technology and System Risk (L2 Technology Management Failure, System and Infrastructure Disruption, Data and Backup Failure); L1 Information Security and Cyber Risk (L2 Access and Vulnerability Management Failure, Security Incident or Breach); L1 Compliance and Regulatory Risk (a peer L1). Leo's own five L3s from the meeting stay under Technology Management Failure. Stored as a `register.taxonomy` table with the framework mapping per node (NIST CSF 2.0 category, ITIL 4 practice, CIS Control), our mapping, marked unchecked.
- **Level has one meaning on screen:** the 4-value rating. Taxonomy depth is "category". Incident priority (P1 to P4) is not shown until an incident-management feed exists.
- **Loss event** = money lost; denial of service to a large set of customers; a breach that creates legal risk. A candidate is an *event under review* until it is traced; a brief is a *problem record* (rename on screen only, tables keep their names).
- **TRP** is the name of the Priorities list; BRP is the empty column. Both are labelled "method, not a standard".

## 3. Register, roles and governance (steps 8b, 8d)

**Where it lives.** Tables in an add-on schema `register` on the existing Postgres (the Server#138 pattern), not a Server concept, for the proof of concept. Revisit when Kumar answers question 1 of his list.

**Every change is an append.** A rating is never edited in place. `register.assessments` gets a new row per change: item, category, rating, likelihood band and its inputs, impact band and its inputs, inherent flag, control-evidence references, set by, role, time, run id, evidence digest. The current view is the latest row. This is what makes it governed: who set it, when, with what evidence, and every earlier value kept.

**Writes only through an approved workflow.** The add-on role that writes the register is the worker's, and the worker writes only after the Server's workflow API records an approval by the second line. Attribution therefore comes from the Server's own decision record (signed-in user, hash-chained), not from a field the add-on fills in. This reuses the engine already built for the payment, vulnerability and brief workflows; the new definition is `risk-assessment`.

**Three roles in one Workspace.**

| Line | Can | Cannot |
|---|---|---|
| First (owner, operator) | Read, supply control evidence, propose a rating | Approve a rating |
| Second (risk) | Judge: approve or send back a rating, decide treatment | Approve what they proposed |
| Third (audit) | Read everything, export the decision record | Change anything, approve |

Today the Server has `canStartWorkflows`, `canApprove`, `canUploadFiles`. The first line maps to start, the second to approve; **the third needs a read-only, record-export grant that does not exist**. That is Server PR S1 (below). Until then Agency shows the role it infers from grants and says so.

## 4. Priorities, the TRP-style list (step 8c)

A pure rules module with a gold set (like the exposure rating and the link judge), a Python port for the workflow gate, one approved question, and a Priorities screen. No model decides anything.

1. **Escalation triggers first** (overrides, from the article's step 1; ours, to be agreed with Leo): a vulnerability on the CISA KEV list on an internet-exposed system of the top business tier; a credential found in a shared channel; an exposed system with no recovery test in 180 days; the exposure rating already Critical.
2. **Likelihood band** (Low to Critical): KEV listed, EPSS value (bands to agree; both are public data, reuse terms unread), internet exposure from the estate, an expert band entered by a person.
3. **Impact band:** business tier (ServiceNow `business_criticality`), number of dependants (`cmdb_rel_ci` count), data classification, environment (production only counts fully).
4. **Rating** = a stated 4 by 4 table of the two bands; a trigger raises it to at least High.
5. **Order** = rating, then triggers hit, then dependants. Each row carries its reason in one sentence ("Critical: KEV-listed flaw on a tier-1 internet-facing system with 14 dependants").
6. **Business impact (BRP)** column stays empty.

Thresholds are demo constants and labelled as such. Window functions are avoided in the SQL (Server#139); ranking is done in the module.

## 5. Notification clocks (step 8e, after Leo defines material)

A table of rules: regulator, what starts the clock, durations, report kind, source, and whether we checked it. Agency shows the clocks an incident would start **only once a person has recorded the decision** that it is major or material; nothing is inferred and nothing is sent.

- **First: DORA (EU).** Initial notification within 4 hours of classifying an incident as major and no later than 24 hours from awareness; intermediate after 72 hours; final within one month. Checked in secondary sources 2026-11-21; read the delegated regulation before a customer sees it.
- **Second: MAS (Singapore).** 1 hour to notify, 14 days for the root-cause report, under the notices that replaced Notice 644 (which notice applies depends on the entity type).
- Reason for the order: a bank in the EU or Singapore is the stated target; DORA has three stages and a classification step that fits a recorded decision; MAS is the tighter clock and goes in as a second row, not a second design.
- NIS2, SEC 8-K Item 1.05, NYDFS Part 500, the US banking agencies' 36 hours and the AI Act serious-incident rule are recalled only and stay out of the product until checked.

## 6. Source mapping: ServiceNow and Datadog (step 8f)

The simulated `estate` tables stay, renamed toward the real fields so that a connector later changes the source, not the questions.

| Estate concept | ServiceNow CMDB field | Datadog field |
|---|---|---|
| Business tier | `business_criticality` | tag `tier` or `service` |
| Environment | `environment` | tag `env` |
| Owner | `owned_by`, `support_group` | tag `team` |
| Lifecycle | `end_of_support`, `install_status` | none |
| Dependants | count of `cmdb_rel_ci` | service map (not needed first) |
| Last seen | `last_discovered` | agent reporting |
| Vulnerability and exploit | none | `cve`, `cvss.score`, KEV and EPSS from public data |
| Active attack | none | security signal severity |
| Reliability | none | SLO `error_budget_remaining` |

**History.** A Server connector reads current state; it keeps no history. Proposal (question to Kumar): a small snapshot job writes the fields above into Postgres tables once an hour, the Server reads those tables as SQL like the feed, and the live connector remains for "right now" questions. No real ServiceNow or Datadog tenant exists for us; free developer or trial instances are recalled, not checked.

## 7. Measuring what it gets right (step 8h)

Leo labels a sample of what the feed raised: real and relevant, real but not for us, not real. We report precision overall and, as asked, **precision and recall for Critical and High only**, plus whether his order of the top ten matches ours. There is no target false-positive rate. Also written in this step: the one-page rules description for audit and model-risk readers (each rule, its inputs, why, its gold set, what a person must decide).

## 8. Audit export (step 8g) and Server pull requests

Agency side: a decision-record view per run and per control, filterable by control, actor, date and outcome, with the chain check already built. The **signature has to come from the Server**.

Server PRs we would open for Kumar (design notes first, he merges):

- **S1, roles:** a read-only audit grant (read the decision record and registers, nothing else) and, if wanted, named lines as roles instead of a combination of grants.
- **S2, signed export:** the decision record as JSON lines with the hash chain and a detached signature, filterable by control id, run, actor and time.
- **S3, history:** connector snapshots or a stream with history for ServiceNow and Datadog (question, not a request yet).
- **S4, #139:** link it from #138 and note that ranking queries are the case it blocks.

## 9. Build order

Each is a small pull request that can be tested alone.

| Step | What | Depends on |
|---|---|---|
| 8a | Taxonomy table, framework mapping, shared 4-value rating module; Exposure "Moderate" becomes "Medium"; on-screen vocabulary | none |
| 8b | `register` schema, assessments table, categories on the November and July cases and the feed candidates, grants | 8a |
| 8c | Priorities: rules module, gold set, Python port, approved question, screen | 8a, 8b, 8f fields |
| 8d | `risk-assessment` workflow: propose, second-line approve, control evidence, writes the register; roles shown | 8b, S1 for the third line |
| 8f | Estate fields renamed toward CMDB and Datadog names, KEV and EPSS columns (invented values), loss-event text | 8a |
| 8e | Clock rules table and display on the record | Leo's definition of material, 8d |
| 8g | Decision-record view and export | S2 |
| 8h | Pilot: Leo's labels, precision and recall for Critical and High, the rules description | 8c, 8d |

Suggested order: 8a, 8f, 8b, 8c, 8d, then 8h; 8e and 8g wait on Leo and Kumar.

## 10. Open items

- For Leo: the escalation triggers in section 4 and the four-by-four table; what "material" means in a test a person can apply; whether the NSANet grade stays confirmed (our judge says stated); EPSS bands.
- For Kumar: roles (S1), signed export (S2), history (S3), where the register should live long term, and whether a table created while the Server runs appears without a restart (Server#138 question 2).
- Not verified: every framework mapping, DORA and MAS text, the public KEV and EPSS terms, any real tenant.
- Not built: all of the above.
