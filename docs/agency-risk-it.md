# Agency for AI-native risk management: IT risk first (input, output, action, workflow)

Status: proposal for review. Nothing in this note is built. Written 2026-11-20 against app v0.10.22 (the stacks and `docker-compose.yml` already pin it).
Source specification: *Use Case: IT Risk Root-Cause Analysis* ("Seeing past the fear"), prepared by Leo (our JPMC advisor) for Kumar and the team, call of 2026-11-20.
Companion to `agency-design.md`, `agency-spec.md`, `agency-personas.md`, `packs/it-risk/`.

## 1. What the specification asks for, in our words

When a cluster of IT incidents hits and a scary explanation is already circulating ("AI hacking"), a bank's head of technology or operational risk needs, the same day, a
one-page brief that (a) traces each incident from symptom to root cause, (b) grades every link in that chain by its evidence, (c) says whether the circulating claim holds,
and (d) names the control that failed, so budget goes to the right fix. The worked case is the November 2026 cluster: six outages in six days, plus the July model-sandbox breakout.

What makes it different from asking a model for a summary (the spec's own "zero-shot brief", its Appendix B): it states the FAA cause as settled when the sources dispute it,
and it cannot show its reasoning, grade a link, or repeat the same way next month.

## 2. Input, output, action, workflow at a glance

| | IT risk root-cause analysis |
|---|---|
| **Input** | A *scope*: the incidents (named, dated) or a window, the *claim* to test, the audience, the allowed source kinds. Evidence: public sources first (company and agency statements, advisories, news, X for the public story only); later the firm's own change, incident, vendor and control records. |
| **Output** | A one-page *brief*: per incident a causal chain (symptom, cause, driver, root condition), **every link graded and sourced**; a verdict on the claim; the control that owns each root condition; open questions. Versioned and reproducible. |
| **Action** | A named person *publishes* the brief (or holds it, or sends it back). The system names the control to fix and, on approval, records a control-review request. All writes are dry runs here. |
| **Workflow** | Five steps: set scope, gather signals, decompose, classify, publish. Rules gate and judge between the steps; one human gate before publishing. |

## 3. Input

### 3.1 The scope (what the person provides)

| Field | Example (from the spec) | Rule |
|---|---|---|
| Incidents | Six outages, 12 to 17 Nov 2026 (Microsoft 365, FAA, JPMorgan Chase, United, NSANet, Apple); or "everything in the last 30 days at systemically important operators" | Named incidents win over a window; a window is expanded into a list the person confirms |
| Claim to test | "This is AI hacking" | Optional; one sentence; the brief returns a verdict on it |
| Audience | Head of technology or operational risk | Sets length and vocabulary only, never what is claimed |
| Allowed sources | Official statements, agency advisories, news; X for the story only | Source kinds are `official`, `agency`, `news`, `vendor_status`, `social`, `internal`. `social` can never support a cause |
| Window and as-of date | 12 to 17 Nov, as of 19 Nov | The as-of date goes on the brief; official causes arrive on the operators' schedule |

### 3.2 The evidence (what the system reads)

| Tier | Sources | State today |
|---|---|---|
| Public | Statements, advisories, news pages, status pages; X for the story | **No live fetch exists.** The only mechanism near it is the Server's generic REST source (needs per-source header and shape work: Server#103) |
| The firm's own | Incidents, controls, risk register and appetite, vendors, vulnerabilities (the `it-risk` pack: Postgres `risk`, MariaDB `security`) | Exists, as invented sample data, answers 12 approved questions |
| Change records | Change calendar, patch backlog, test capacity | **Missing from the pack.** The spec's central root condition ("change and test capacity behind change volume") can only be tested against these |

Every signal is stored once with its publisher, URL, retrieval time, a content hash, and an excerpt of at most 25 words of our own choosing; we keep a paraphrase and a link,
not the article. The brief links, it does not reproduce.

## 4. Output

### 4.1 The brief (one page)

1. **Headline and claim verdict.** One sentence, plus one of `supported`, `not supported by any official cause`, `insufficient evidence`. The verdict names how many incidents are still open (here: FAA disputed, United not named).
2. **Incident table.** One row per incident, four layers (symptom, cause, driver, root condition), each cell carrying a grade chip and a source count.
3. **Roll-up.** Root conditions grouped (for November: change management and test capacity; concentration), each mapped to the control that owns it.
4. **The control to fix.** Named control, owner role, the evidence behind it.
5. **What is still open.** Links graded `inferred`, `disputed`, `not named` or `to be tested`, and what would settle each.
6. **Provenance.** As-of date, brief version, source list, judge version, who approved.

### 4.2 The grade vocabulary (from the spec's section 5, made explicit)

| Grade | Meaning | May a brief state it as fact? |
|---|---|---|
| `confirmed` | An official source (the operator or a regulator) states it and nothing official contradicts it | Yes |
| `stated` | The party involved states it; not corroborated by anyone else | Yes, attributed ("OpenAI says") |
| `disputed` | Two official sources disagree (FAA cause) | No; show both |
| `not named` | No official cause published yet (United) | No |
| `inferred` | Our reasoning from other links; no source says it (driver: AI finding bugs faster) | No; labelled as inferred |
| `to be tested` | A hypothesis with a defined test against the firm's own records (change and test capacity) | No |

These six, the rules below and the judge rubric are **our proposal**; Leo and Kumar should confirm them.

### 4.3 The November case as the acceptance test

The spec's own result, which our brief must reproduce and the zero-shot brief must fail:

| Incident | Cause | Grade |
|---|---|---|
| Microsoft 365 (12 to 13 Nov) | A July Windows defect triggered by a Teams traffic shift while about 14% of capacity was offline | `confirmed` (Microsoft: not a cyberattack, not AI agents) |
| FAA ground stop (13 Nov) | A contractor's copper-to-fiber telecom upgrade (Secretary Duffy) versus legacy TDM instability (FAA) | `disputed` |
| JPMorgan Chase (16 Nov) | Software bug in on-premise hardware systems | `confirmed` |
| United (16 Nov) | Departure control system; a union memo points to weight and balance | `not named` |
| NSANet (17 Nov) | Degradation during scheduled maintenance | `confirmed` |
| Apple services (17 Nov) | An internal update | `confirmed` |
| Driver across all | AI finding bugs faster, raising patch pressure | `inferred` |
| Root condition across all | Change and test capacity behind change volume | `to be tested` |

Result: causes confirmed for 4 of 6 (stated for 5 of 6, counting the disputed FAA cause); no official source attributes any of the six to an attack. The July breakout (Hugging Face)
is a second, smaller case: zero-days chained across systems `confirmed`, training pressure `stated by OpenAI`, weak containment `stated by OpenAI`.
Note the spec says both "five of six have a stated cause" and "confirmed for 4 of 6"; both hold, and the brief should show both numbers.

## 5. Action

What a person can do with the brief, and what the system does on their behalf. No action writes to a customer system: the sandbox write-back is a dry run, as in the payment and vulnerability workflows.

| Action | Who | Effect |
|---|---|---|
| **Publish** | Named approver (head of technology risk); not the initiator; never the AI | Fixes version N of the brief, records it in the decision record, makes it exportable |
| **Hold** | The approver | Keeps the draft, lists what it waits for (for example "United: cause not named"), and re-opens when a new official source arrives |
| **Send back** | The approver | Returns the draft with a reason; a new version is produced, the old one stays in the record |
| **Open control review** | The approver, on publish | Records a request to the control owner naming the control to fix (dry run: shows the call, sends nothing) |
| **Re-run** | The initiator | New version of the same scope with fresh signals; the diff against the last version is shown |

Allowed verdicts are clamped by rules (section 6.3); the AI chooses among allowed ones and can propose "hold".

## 6. Workflow

```
Set scope -> Gather signals -> Decompose -> Classify -> [rules gate + judge] -> Draft brief -> Approve -> Publish (dry run) -> Decision record
   person         system         system       system        system             AI, clamped     person       system            hash-chained
```

### 6.1 Steps

| Step | What happens | Who/what | Evidence kept |
|---|---|---|---|
| 1. Set scope | Person names incidents, claim, audience, allowed sources; the system expands a window into a list to confirm | Person | The scope record |
| 2. Gather signals | Fetch the allowed sources for those incidents; store signal records; merge reposts of one event | Signal adapter (not built) | URL, time, hash, excerpt |
| 3. Decompose | For each incident, propose the four layers and attach signals to each link | Model, constrained to the schema | Links with sources |
| 4. Classify | Map each root condition to the framework and the owning control (NIST CSF function and category; internal control owner) | Rules plus model for the mapping | Control map |
| Gate | Deterministic checks (6.3), then the judge grades each link against its cited source text (6.4) | Rules, then judge model | Grades, reasons, judge version |
| 5. Draft | Compose the brief from graded links only; propose publish or hold | Model, clamped to allowed verdicts | The draft and its hash |
| Approve | Named approver publishes, holds or sends back, with a reason | Person | The decision, bound to the draft hash |
| Publish | Fix the version, export, record the control-review request (dry run) | System | Hash-chained decision record |

### 6.2 Where the data lives (answers to the spec's question 1)

The causal chain is held as rows in a governed source, not as a new Server feature. A small Postgres schema `rca`:

| Table | Holds |
|---|---|
| `rca.events` | One row per incident: operator, dates, symptom |
| `rca.signals` | Source records (kind, publisher, URL, retrieved at, hash, excerpt) |
| `rca.links` | One row per link: event, layer, statement, grade, reason, run, version |
| `rca.link_sources` | Which signals support which link |
| `rca.claims` | Claim text, verdict, run |
| `rca.control_map` | Root condition to framework category and internal control |
| `rca.briefs` | Run, version, draft hash, approver, published at |

Registered as a backend in the IT-risk Workspace, it is queryable through Ask, joins to the firm's own `risk.incidents` and `risk.controls` (the spec's "are we exposed?" step),
and inherits grants. Open point: grade codes need ontology descriptions, as found on the SAP spike (code values do not explain themselves to the model).

### 6.3 Rules gate (deterministic, readable by a risk partner)

1. **No cause without evidence.** A link with no source can only be `inferred` or `to be tested`; anything else is refused.
2. **Social is a lead.** A link whose only sources are `social` cannot be `confirmed` or `stated`.
3. **Disputed means two.** `disputed` needs two official sources that differ; with one, the grade is `stated`.
4. **The costliest error.** The verdict "not supported" is allowed only if every incident is `confirmed` or the brief names each open incident (disputed, not named) in the verdict sentence. A flat "no attack" while any cause is unnamed is blocked.
5. **Inference is labelled.** Driver and root-condition links graded `inferred` or `to be tested` render with that chip in the brief; the draft cannot drop it.
6. **Approval is bound to the hash,** the initiator and the AI cannot approve, and a new version needs a new approval (the existing workflow engine already enforces these).

### 6.4 The judge (answers to question 2) and how we would measure it

The judge reads one link and its cited excerpts and returns a grade and a one-sentence reason, using a rubric that mirrors the table in 4.2 and the rules in 6.3.
It is a model call plus the deterministic gate, not a model alone. We test it on a gold set built from the spec: the eight rows in 4.3 plus planted errors, most importantly
**the FAA cause stated as settled** (the spec's own zero-shot failure), a social-only cause, an unsourced driver stated as fact, and a "no attack" verdict with United unnamed.
Pass bar (proposal): all planted errors caught, all eight gold grades reproduced, on three runs. Spec measures to report: share of links with a source, claims tested and
confirmed or rejected, time from incidents to brief, against the zero-shot baseline.

### 6.5 Mapping onto what exists

| Piece | Reuse | New |
|---|---|---|
| Engine contract and gateway | `demos/payment-workflow` gateway, Server workflow API (v0.10.19+), hash-chained record, hash-bound approvals, no self-approval | A third definition, `incident-cluster-rca`, beside payment and `vulnerability-exception` |
| Facts | Governed queries through the Server | Reads of `rca.*` and the firm's `risk.*`; the public signals come from the adapter |
| Rules | `it_rules.py` pattern (pure functions) | `rca_rules.py` with the six rules above |
| Recommendation | `recommend.py`, clamped to allowed actions, falls back to `rules-only` | A draft-brief step and a judge prompt |
| Agency | Workflow card, decision record, evidence pane, charts | Scope form, brief view with grade chips and source popovers, PDF export |
| Signals | Adapter contract (`AGENCY_ADAPTERS`) | A signal adapter: allow-listed URLs only, snapshot and hash, no cookies, robots respected; X later, only with an API plan whose terms allow it |

## 7. Agency tailoring (the category, then IT risk)

- **Category profile.** A catalogue profile `risk` that shows three Workspaces on the landing screen: *IT risk* (`it-risk`), *BOM risk* (`bom`), *Supply chain and logistics risk*. The first two exist as packs.
  **Gap:** the existing `supply-chain` pack is suppliers, inventory and procurement, not logistics (shipments, lanes, ports, carriers); a logistics pack would be new data and is out of scope for this deliverable.
- **IT-risk Workspace, two doors.** *Ask* (the 12 approved questions on the firm's data) and *Investigate an incident cluster* (this workflow).
- **Brief view.** One page, printable: incident table with grade chips, claim verdict, control to fix, open items; clicking a chip shows the source excerpt and link.
- **Honesty cues.** An `inferred` or `to be tested` chip is visually distinct from `confirmed`; a brief with open items says so in its first line.

## 8. Dependencies and answers for the Friday questions

| Spec question | Proposed answer | Confidence |
|---|---|---|
| 1. Can the semantic layer hold the causal chain? | Yes as tables plus ontology descriptions (6.2), joined to the firm's own records through the governed query path. Not as a native "causal model" type | Design only; not tried |
| 2. How would the judge grade a link? | Rubric plus deterministic gate, tested on the gold set (6.4) | Design only; no judge run yet |
| 3. Which sources can we pull live today? | None in the product. The REST source type could read an API with a key; public pages need the signal adapter. X needs a paid plan we have not checked | Verified by absence |

## 9. Build order (small pull requests, each testable without the next)

1. **This note** and the gold set as data with tests (no model).
2. `rca` schema, the November and July seed (our paraphrases, links, no article text), ontology descriptions, approved questions; verified through Ask on the local stack.
3. `rca_rules.py` and the judge prompt; the gold-set benchmark with the zero-shot brief as baseline.
4. The `incident-cluster-rca` definition through the gateway; start and approve through the Server's workflow API.
5. Agency: scope form, brief view, actions, PDF export.
6. Signal adapter with allow-listed sources; X only after the plan and terms are checked.
7. Change records in the `it-risk` pack (change calendar, test capacity) so the root condition can move from `to be tested` to confirmed or rejected on a firm's own data.

## 10. Open questions for Leo and Kumar

- Is the six-grade vocabulary right, and who owns the rubric once it ships?
- Who is the approver in a bank (head of technology risk, CRO office), and may the brief leave the firm?
- Should an `inferred` driver ever appear in the headline, or only in the table?
- Which public sources are acceptable to a bank's compliance team, and is X allowed at all, even for the story only?
- For Kumar: can the Server expose a link/grade column type or description so the judge's grades are first-class, and is a signal-fetching source (allow-list, snapshot) in scope for the Server or an Agency adapter?
- What does "the firm's change records" look like at JPMC (system, fields), and can a pilot read them read-only?
