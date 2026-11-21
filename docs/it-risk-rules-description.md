# IT-risk rules: a description for audit and model-risk readers

Step 8h of `docs/agency-risk-register-plan.md`. Written 2026-11-21 from the code at the commit that adds it; each rule below names the file that holds it, so a reader can check this page against the code.

**What this is.** Every judgement the IT-risk screens and workflows make is a written rule over stated inputs. **No machine-learning model decides, grades, rates, ranks or approves anything.** (A model can be configured to draft a recommendation in the payment and vulnerability workflows; the incident-brief and risk-assessment workflows recommend from the rules alone, labelled `rules-only`.) The rules are a method, not a standard, and every number in them is a **demo constant** that a head of technology risk would own in a real deployment.
**What it is not.** It is not a model that has been validated against outcomes. The simulated estate and the sample incidents are invented or paraphrased; the pilot (`demos/it-risk-pilot`) measures how often a risk partner agrees with the rules, and has not yet been run on a real person's labels.

| Rule set | File | Inputs | Decides | Tested against | A person must still decide |
|---|---|---|---|---|---|
| Feed filter and clustering | `addons/feed-adapter/rules.py` | A headline, a short description read and dropped, the feed's kind | Whether a headline becomes an event under review, its claim type, which headlines share one | 32 adapter tests; the pilot's label sheets | Whether the event is real and relevant; tracing it |
| Link judge | `demos/payment-workflow/rca_judge.py` | A link's sources: speaker kind, relation, what each asserts | The strongest grade the sources support; whether a link claims more | Gold set `rca_judge_gold.json`, 18 cases (10 from the specification, 8 planted errors) | Entering each source's relation and what it asserts (entered with the data, not extracted by a model) |
| Brief gate | `demos/payment-workflow/rca_rules.py` | Causes, grades, sources, the judge's audit, the exposure rating | Whether the problem record may be published or only held | `tests/test_rca.py` and the rest of the workflow suite | Approving, holding or sending back, by a named approver |
| Exposure rating | `agency/web/src/exposureModel.ts`, port `demos/payment-workflow/exposure_rules.py` | Five approved questions over the estate | A 0 to 3 score per question; the overall rating is the HIGHEST score | Gold set `exposure_gold.json`, 15 cases | The thresholds; whether the estate data is right |
| Priorities | `agency/web/src/priorityModel.ts`, port `demos/payment-workflow/priority_rules.py` | One estate row per system | Likelihood band, impact band, rating, triggers, order | Gold set `priority_gold.json`, 14 cases | The thresholds; business impact (not scored) |
| Assessment gate | `demos/payment-workflow/assess_rules.py` | The Priorities proposal, the register's current rating, the exposure rating | The proposed rating, category and evidence; how many approvers; who may not approve | `tests/test_assess.py`, 20 tests | Recording or sending back, by the second line |

## Feed filter (`rules.py`)
- A **context** feed never creates an event under review. A headline matching roundup, newsletter, podcast, webinar or "edition" patterns is skipped.
- It needs an AI term (a list of words such as "artificial intelligence", "LLM", "agentic", "deepfake", product names; a bare "AI" only when capitalised). With an attack term AND an incident term it is a **claim** (`ai-attack-claimed` from a reporting feed, `ai-attack-confirmed` from an official one). With only an incident or a weakness term it is `ai-adjacent`. Otherwise it is not matched.
- **Clustering:** two matched headlines share an event under review when within two days and sharing one name, or within a week and sharing two. Two events already traced are never merged. The earliest headline leads.
- **Why:** to bring a possible story to a person, not to judge it. A feed item is a lead, never evidence: reporting cannot raise a cause above "stated". **Unmeasured:** precision and recall; that is what the pilot sheets are for.

## Link judge (`rca_judge.py`)
Social sources and background rows are ignored. A symptom acknowledged by any non-social source is confirmed. A cause: two or more different official statements are **disputed**; exactly one is **confirmed**; an official source that names no cause is **not named**; only reporting, a union or a reference page is **stated**; nothing usable is **inferred**. A driver or root condition: two or more official parties saying the same is confirmed; one is stated; none is **to be tested** (if a control could test it) or inferred. A link that claims confirmed or stated but whose sources support less is **overstated**, which blocks publishing.
**Why:** the costliest error in a root-cause write-up is stating a cause as settled when an official source disputes it or says nothing.

## Brief gate (`rca_rules.py`)
Publishing is allowed only when: every cause has a source (or is graded inferred or to be tested); the judge finds no overstated link; the verdict sentence names every open incident (never a flat "no attack" while one is open); the exposure rating, when the case has one, is complete (an unread estate blocks: it is not a clean one); a claim and an incident exist. Otherwise only a hold is allowed. The approval is bound to a SHA-256 digest of the exact content; **the initiator and AI or service identities cannot approve**; a stale digest is refused.

## Exposure rating (`exposureModel.ts`)
Five approved questions (where the technology runs, who can reach critical data, where credentials and runbooks sit, overdue patches and untested changes, dependants and recovery tests) each score 0 to 3 by a stated rule; the **overall rating is the highest score, never an average**, and names the questions that set it. A question that cannot be answered is **unknown, never 0**, and the rating then reads "at least". Constants: patch overdue more than 15 days; recovery test older than 180 days (both the user's, from the specification); retest-soon 90 days and "wide" 100 people (mine).

## Priorities (`priorityModel.ts`)
- **Likelihood** Critical if a known-exploited flaw is open or a credential is visible beyond its owners or team; High if an open flaw has an exploit score of 0.5 or more, or the system is internet-facing with a flaw open; Medium if an open flaw scores 0.1 or more, a change skipped testing, vendor support ends within 90 days (or has ended), or the last recovery test is older than 180 days or never happened; else Low. A system with no recovery record is noted, not scored as never tested.
- **Impact** starts at the business tier (1 High, 2 Medium, 3 Low), plus one step for restricted data and one for three or more dependants, minus one outside production and disaster recovery, capped at Critical.
- **Rating:** the two bands add (Low 0 to Critical 3): 0 to 1 Low, 2 to 3 Medium, 4 to 5 High, 6 Critical. **Triggers** lift to at least High: a known-exploited flaw on an internet-facing tier 1 system; a credential visible widely; an internet-facing system never or over 180 days recovery-tested; the exposure rating Critical and the system in scope.
- **Order:** rating, number of triggers, dependants, tier, name. Business impact is deliberately not scored.
- **Why:** to show a person which systems to look at first and why, in one sentence each. The exploit-score bands (0.1, 0.5), the 90 days and the three dependants are my demo constants and still need agreeing.

## Assessment gate (`assess_rules.py`)
Proposes the Priorities rating, a category (the finding that drives the likelihood: open patch, then credential, then untested change, then recovery, then end of support, else the family) and the control evidence as plain text. **A Critical rating needs two different approvers** (a demo constant), others one. Approving adds ONE row to the append-only register; a hold or a send-back adds nothing. The register is **inherent risk with the control evidence beside it: residual risk is never computed**; the second line judges it.

## What a rule never does
It never approves, publishes, rates residual risk, decides a treatment (accept, mitigate, transfer, avoid), decides what is "material", starts a regulator's notification clock, or sends anything to a customer system (every write-back except the register is a dry run). Those are a named person's decisions, recorded in a hash-chained decision record.

## Limits a reader should know
- Gold sets are small and mostly hand-worked by the authors; the planted cases are the errors a careless rule would make, not an independent test set.
- The category and framework mappings (NIST CSF 2.0, ITIL 4, CIS Controls v8) are ours, from general knowledge, not checked clause by clause.
- The exposure and priorities inputs come from a simulated estate; with real CMDB and Datadog data the inputs, and likely the thresholds, change.
- Several constants are mine. They are listed above so that a risk partner can change them and the gold sets will say what moved.
