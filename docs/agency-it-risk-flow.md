# Agency for IT risk: application brief and flow (design, not built)

Status: design for review, 2026-11-20. Nothing in this note is implemented. It replaces the "category with three Workspaces" framing of `agency-risk-it.md` section 7 for the first release: Agency does IT risk only, and other domains come later through a Workspace dropdown.

Source: Leo's specification (`itrisk.md`, call with Kumar on 2026-11-20). The copy used here is the one in Downloads; the newer copy sent through Messages could not be opened from this machine (macOS blocks the Messages folder), so anything that changed in it is not reflected. Section 8 of that file (first release: MVP, Pilot, Scale) was pasted in the request and is quoted below.

## 1. The application in one paragraph

Agency for IT risk is a place where a head of technology risk answers two questions, in this order, and gets a graded, sourced answer to each.

1. **What is making the news as "AI hacking", and is it true?** A continuous watch over technical news turns each wave of incidents into a candidate. The system traces each candidate from symptom to root cause, grades every link by its evidence, and gives a verdict on the claim. This is Leo's use case, run as a standing process instead of a one-off brief.
2. **Could the same thing happen to us?** For a chosen incident, the system looks at where our own critical resources live (databases, object storage, Slack, SharePoint), asks five fixed questions of those records, and returns a rating with the rows behind it. This is the "are we exposed?" step of the Scale stage.

Every answer carries its evidence. Anything the system infers is labelled inferred. Nothing is published or acted on without a named approver, and every approval is bound to the exact text approved.

## 2. How this maps to section 8 (first release)

| Stage in the spec | Done when | Where it lives in this design |
|---|---|---|
| **MVP** | Decompose November and July on public data; every link graded and sourced | Built (Docker#242 to #245). It becomes the *Incident detail* screen. |
| **Pilot** | Run it on the next incident cluster as it happens; the brief ships within a day; a bank risk lead uses it instead of the threat review; the change-capacity root condition is tested against the firm's change records | Ask 1, the **Watch** feed, makes "as it happens" real. The change-records test is Ask 2 question 4. |
| **Scale** | Connect one firm's own change and incident data; it answers "are we exposed?" from the firm's own records | Ask 2, **Exposure**. In this release the firm's records are simulated (section 6.3); connecting real ones is the first thing after. |

## 3. Decisions taken from the request

1. **IT risk only.** The domain chips and the "Compare domains" cards leave the screen. Agency opens straight into IT risk.
2. **Workspaces become a dropdown at the top right**, like the Ask app's Workspace selector (`Server/web/src/pages/GroupPicker.tsx`: a dropdown in the top-right corner, one Workspace at a time, the session's Workspace is stored by the Server). Today it lists one entry, "IT and operational risk". Later domains (BOM risk, supply chain risk, Treasury, and so on) appear as more entries without changing the layout.
3. **A bluer palette.** The warm pastel goes. The accent moves from the logo's teal (`#0BA9AA`) a shade toward blue (section 7).
4. **Two asks, two screens.** Watch and Exposure are separate steps in the left navigation, not one long page.

## 4. Flow

```
Top bar:  Agency by thinking sense                         [ Workspace: IT and operational risk v ]  curator  Sign out

Left nav            Main
---------           ---------------------------------------------------------------------------
Watch               1. WATCH     A list of incident clusters the feed has found, newest first
Exposure              |          each: headline, claim, #incidents, date, status (new / traced / briefed)
Briefs                v
Approvals (n)       2. INCIDENT  One cluster, traced: symptom > cause > driver > root condition,
Sources                |         each link graded, verdict on the claim, control to fix
                       v         [ Brief ] [ Are we exposed? ]
                    3. EXPOSURE  Five questions about our own resources, a rating each, one overall rating,
                       |         the rows behind every rating
                       v
                    4. DECISION  Send the brief and the rating for approval: publish / hold / send back
                                 (named approver, bound to the exact text, dry run)
```

Who sees what: everyone with access reads Watch and Incident. Exposure needs the right to read the estate sources (the Server decides this per person, as it does for every answer). Starting a decision needs `canStartWorkflows`; approving needs `canApprove`. This is the same rule set Agency already relays.

## 5. Ask 1: Watch, the continuous process

### 5.1 What it does

Every N minutes (default 30) a feed service reads the configured sources, drops what it has seen, keeps what looks like an AI-hacking story, groups items about the same event or the same week into a cluster, and puts the cluster in the Watch list as a candidate. A person (the analyst) opens a candidate and presses *Trace it*, which runs the existing decomposition, judge and brief. Nothing is traced or published without a person pressing a button in this release.

### 5.2 Sources

| Source | Role | State |
|---|---|---|
| RSS or Atom from technical news sites | primary: titles, links and dates | **To be chosen (the user asked us to search for the best few and propose them; not yet done).** Which sites offer a feed, and on what terms, has not been checked. Candidate list for Leo and Kumar to confirm: a security news site, a general technology outlet, a vendor status page, a government advisory feed. |
| X | the public story only; per the spec a post can be a lead, never evidence of a cause | **Not decided.** Needs a paid API plan and terms we have not read. Design it behind the same adapter so it can be added without changing the rest. |
| Official statements (company status pages, agency advisories) | the only things that can grade a cause `confirmed` or `disputed` | Same adapter, flagged `official`. |

Each item stores: source, URL, title, publication time, speaker kind (`operator`, `regulator`, `reporting`, `social`), and a one-sentence paraphrase written by us. It does **not** store article text (the seed data follows the same rule). This keeps copyright and storage small and is what the existing `signals` table already holds.

### 5.2a Feed research (2026-11-20, our notes; the user's own research to be compared)

Each feed was fetched once with a plain client and read for item count, newest date and headlines. Nothing was stored. Headlines are what the live feeds returned today; no article was opened, so none of them is evidence of a cause.

| Feed | Items / newest | On topic (AI in title, outage or incident) | robots.txt for the feed path | Verdict |
|---|---|---|---|---|
| SecurityWeek | 10 / 20 Nov | 2 of 10 AI; two on-topic outage and AI-patching headlines | allowed | **Start with** |
| Dark Reading | 50 / 19 Nov | 21 of 50 AI | allowed | **Start with** (noisy, vendor-style pieces) |
| Wired security | 20 / 18 Nov | 6 of 20 AI; a "cyberattack or just an outage" explainer | allowed | **Start with** |
| The Hacker News | 50 / 20 Nov | 8 of 50 AI | allowed | Add after terms are read |
| BleepingComputer | 15 / 20 Nov | 0 AI in titles; fast on incidents | allowed, crawl delay 1 s | Add after terms: its 2014 user agreement restricts storing site content except personal, non-commercial use |
| The Register (security) | 50 / 20 Nov | 12 of 50 AI; an outages headline | **disallowed** for the feed path | Do **not** use unless they permit it |
| Krebs on Security | 10 / 11 Nov | few | allowed, **crawl delay 35 s** | Low priority; slow, infrequent |
| SANS ISC | 10 / 20 Nov | 1 AI | allowed | Optional, technical |
| CISA advisories | 30 / 19 Nov | advisories, no AI titles | allowed | **Start with** (official, US government) |
| UK NCSC | 20 / 11 Nov | 3 AI incl. a critical-infrastructure warning | no robots file | **Start with** (official) |
| GitHub status | 25 / 19 Nov | many incident posts | allowed | Example of a provider status feed |
| AWS status | 38 / newest 15 Sep | stale | n/a | Not useful as is |
| Cloudflare status | 25 / newest dated 11 Dec (a date in the future) | n/a | n/a | Date is wrong; check before use |
| OpenAI news, Hugging Face blog | 1,418 and 914 items | needs a filter | n/a | Operator statements for July-type events; only with a keyword filter |
| Ars Technica security, Anthropic news | 404 at the paths tried | | | Find the right URLs or skip |
| Microsoft MSRC blog | 0 items parsed | | | Different format or blocked; find another route |

### 5.2b The user's feed list, checked the same way (2026-11-20)

The user supplied 13 feeds. Fetched once each: 12 work; Trend Micro's address does not resolve. Robots results below used a generic user agent and must be re-checked with the real Agency user agent.

| Feed | Items / newest | AI in title | Verdict |
|---|---|---|---|
| WeLiveSecurity (ESET) | 100 / 19 Nov | 8 | **Reporting.** Add. |
| Zscaler security research | 50 / 19 Nov | 7 | **Reporting.** Add. |
| Wired AI tag | 10 / 20 Nov | 5 | **Reporting.** Add; better than Wired security for this topic. |
| Schneier | 10 / 20 Nov | 3 | **Context** |
| Securelist (Kaspersky) | 10 / 18 Nov | 1 | **Context** (malware detail, low yield) |
| Ars Technica AI | 20 / 19 Nov | 9 | **Context** (AI news, not attack reporting) |
| MIT Technology Review AI | 10 / 18 Nov | 6 | **Context** |
| Krebs | 10 / 18 Nov | 0 | Context, low priority (35 s crawl delay) |
| OpenAI news | 1,418 / 19 Nov | 315 | **Official** for model-vendor events; needs a keyword filter; later |
| Google DeepMind | 100 / 18 Nov | 27 | Official, same; later |
| Wiz | 513 / newest 21 Oct | 15 | Stale; skip until it updates |
| Volexity | 10 / newest 16 Oct | 1 | Stale; skip |
| Trend Micro | does not resolve | | Find the current address or skip |

**A fourth source kind: `context`.** Analysis, commentary and general AI news help an analyst understand a candidate but never create one and never count as a source for a link. The judge already ignores `context` relations; the feed adapter tags these feeds so they appear beside a candidate as reading, not as evidence.

**Merged starter set (seven, plus context):**

| Kind | Feeds |
|---|---|
| Reporting (can create a candidate) | SecurityWeek, Dark Reading, Wired AI, WeLiveSecurity, Zscaler |
| Official (can ground a cause) | CISA advisories, UK NCSC |
| Context (reading only) | Schneier, Securelist, Ars Technica AI, MIT Technology Review AI |
| Later, with a filter | OpenAI news, Google DeepMind, The Hacker News, BleepingComputer (after terms) |

**Statements from operators.** Neither list found a feed for the operators and regulators the spec grades on. A social feed such as an X aggregator is the only candidate route; it may be paid, its terms are unread, and per the spec a post is a lead, never evidence. For this release the analyst pastes the primary source when tracing a candidate, and X stays behind the adapter as a later option.

**Our first proposed starter set (five, superseded by the merged set above):** SecurityWeek, Dark Reading, Wired security, CISA advisories, UK NCSC. Three reporting feeds that carry the AI and outage story, two official sources that can ground a cause. Add The Hacker News and BleepingComputer once their terms are read.

**Gaps that matter:** the official statements the spec grades causes on (Microsoft 365, the FAA, a bank, an airline) mostly have no RSS feed; cloud providers' status pages are the exception. A feed gives leads; confirming a cause still needs a person to find the primary source, or a later adapter for a few named status pages.

**Terms:** only robots.txt was checked, plus one search that surfaced BleepingComputer's 2014 agreement. The Register, SecurityWeek, Dark Reading, Wired and The Hacker News were not read for reuse terms. The design stores only the title, link, date, speaker kind and our own one-sentence paraphrase (never the article text), which should lower the risk, but it belongs on the counsel list next to the licence register.

**One example of why grading matters:** a security feed's headline today says Chase confirmed third-party cyberattacks that may have exposed customer information, while the specification's Chase incident was an on-premise software bug causing a transaction slowdown. They may be different events; the system would hold the first as a lead, not as a cause, until a primary source says which.

### 5.3 What counts as "AI hacking"

Three claim types, chosen so the system does not swallow the fear it is meant to test:

- `ai-attack-claimed`: someone says an AI-driven attack caused it (the story Leo's brief tests).
- `ai-attack-confirmed`: an operator or regulator says so.
- `ai-adjacent`: an outage or vulnerability story that mentions AI (for example patch pressure) without claiming an attack.

A rule-based first pass (keywords and source kind) assigns the type. A model pass can refine it, but it is optional and off by default, because the same rule as the judge applies: the model may propose, the rules gate decides. A candidate is only ever *claimed* until an official source says otherwise.

### 5.4 Data

New tables beside the existing `rca` schema: `feed_sources`, `feed_items` (the signal rows above plus a `seen_hash`), `candidates` (cluster id, title, claim type, status), `candidate_items`. Candidates become `rca.claims` and `rca.events` only when an analyst traces them; until then they are labelled *not yet traced*.

### 5.5 Where it runs

A small stdlib Python service, `addons/feed-adapter`, like the other adapters: it only fetches and writes, it holds no user sessions, and it writes through the Server's own routes or a dedicated schema owner (open question 3). The Agency layer lists candidates as the signed-in user.

### 5.6 What can go wrong, and the answer

| Risk | Answer |
|---|---|
| A viral post is wrong | Social items are leads; they never raise a cause above `inferred`. |
| A feed disappears or changes format | The adapter reports each source's last success; Watch shows "Source X has not updated since ..." |
| Duplicates and reposts | Hash on normalised title and URL; cluster by time window and shared names. |
| The system calls "no attack" too early | Existing rule: no flat "no attack" while any cause is open. A new candidate starts as `claim not yet tested`. |
| Cost and noise | Rule-based filter first; a model only on the shortlist, and only when a key is configured. |

## 6. Ask 2: Exposure, "could this happen to us"

### 6.1 The estate

The question needs a map of what the firm owns. The resources named in the request, and how Agency reaches each one:

| Resource | What we ask of it | How the Server reaches it |
|---|---|---|
| Databases (Postgres, MariaDB) | systems, owners, classification, patch and change records | SQL source, as for every pack |
| Object store (S3 compatible) | buckets, public access, encryption, who can write | the Server's file/object source |
| SharePoint | sites and libraries, sharing scope, whether recovery or credential documents sit there | a stream of change events (Kafka connector) landing in Postgres tables; the Server reads the tables as SQL (answer to Q6) |
| Slack | channels and whether secrets or runbooks are posted in broad channels | the same: a stream of events into Postgres tables (answer to Q6) |

In this release all four are **simulated**: invented data in the `estate` schema, and for SharePoint and Slack a replay of invented events into the same Postgres tables a real Kafka connector would fill (a small replay service stands in for the connector), labelled as invented on screen. The aim is to prove the flow, the stream shape and the rating, not to claim a real connector. A real tenant later means swapping the replay for the connector; the questions and the rating do not change.

### 6.2 The five questions

Each question is an approved question with reference SQL, runs as the signed-in person, and returns rows. They are written around "a similar incident", meaning the incident's root condition and affected technology (for example: a latent defect in a gateway, triggered by load, during a change).

| # | Question | What it shows | Source |
|---|---|---|---|
| 1 | Where does the affected technology run in our estate? | the blast radius in systems | databases (the estate inventory) |
| 2 | Which of those systems hold critical data, and who can reach them? | the data at stake and the access path | databases, object store |
| 3 | Where do runbooks, credentials or recovery steps for them sit, and who can see them? | what an attacker, or a rushed engineer, would find | SharePoint, Slack |
| 4 | Are those systems behind on patches or running changes without enough testing? | the spec's root condition, tested against our own change and patch records | databases (change and patch records) |
| 5 | If one fails, what depends on it and how fast can we recover? | concentration and recovery | databases (dependencies, recovery tests) |

These five are a proposal, not Leo's list; open question 1 asks him to confirm or replace them.

### 6.3 The rating

Rule-based, like the judge, so a risk partner can challenge each rule.

- Each question gets 0 (no concern), 1 (watch), 2 (concern) or 3 (critical), from a short stated rule over the returned rows. Examples: Q2 scores 3 if a system with `restricted` data is reachable by a group wider than its owner team; Q4 scores 2 if any in-scope system has a security patch overdue by more than 15 days; Q5 scores 3 if a tier-1 service has no recovery test in the last 180 days.
- The overall rating is the highest of the five, shown as Low, Moderate, High or Critical, **with the question that set it**. Not an average, because one unrecoverable tier-1 system is not diluted by four clean answers.
- Every score shows the rows behind it and the rule that produced it. A question that cannot be answered (a source is not loaded) scores *unknown*, never 0, and the overall rating says so.
- Thresholds (days overdue, recovery window) are demo constants, listed on screen, owned by the head of technology risk in a real deployment.

### 6.4 Output

A one-page exposure view next to the brief: the incident and claim, the five answers with scores, the overall rating and what set it, the control to fix (already in the brief) and the named owner. It can be copied as text and printed.

### 6.5 Action

The same decision as today, widened: *publish the brief and the exposure rating*, *hold*, or *send back*, as one approval bound to the combined text. Opening a control review stays a dry run. The initiator and any AI identity cannot approve.

## 7. Look and feel

**Palette.** The logo teal is `#0BA9AA`. Pastel failed on contrast and looked washed out, so the accent moves a shade toward blue and the surfaces go cool and nearly white. All text pairs below are computed contrast ratios.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F5FAFC` | `#0F1A1F` | page |
| `--panel` | `#FFFFFF` | `#16252C` | cards, answers |
| `--ink` | `#14262E` (14.8 on bg) | `#E6EEF2` (15.1) | body text |
| `--muted` | `#4A606A` (6.3) | `#A9BDC6` (9.1) | secondary text |
| `--accent` | `#0A6C94` (5.6 on bg) | `#7FB7CC` (8.0) | links, focus, selected |
| `--fill` | `#0A7BA6` with white text (4.8) | `#5BB6D6` with dark text (7.7) | primary button |
| `--accent-tint` | `#E1F0F6` (accent on it 5.0) | `#1B3440` | selected row, verdict box |
| grade colours | keep the existing green, amber, red set, re-checked against the new surfaces | | grades and ratings |

`#0A6C94` is about 12 degrees of hue bluer than the logo teal and the darkest step that keeps 4.5:1 on a tint. A plain `#0BA9AA` would fail as text (it is a mid-tone), so the logo colour is used for the wordmark only. Rating colours need to read as an ordered scale without relying on colour alone (word plus shape), so Low, Moderate, High and Critical each carry a label and a marker.

**Layout.** One column of content at most 1000 px, a slim left nav (Watch, Exposure, Briefs, Approvals, Sources), the Workspace dropdown at the top right, then the account name and Sign out. The pack cards, the "Compare domains" row, the file drop zone and the generic ask box leave the first screen; free-form asking stays available as a quiet "Ask a question" entry in the nav.

**Phone and tablet.** Same rule as today: single column under 761 px, the nav collapses into a drawer.

## 8. What changes from the build today

| Today | Design |
|---|---|
| Agency opens on a domain choice and pack cards | Opens on Watch |
| Incident brief is a page you reach under Investigate | Incident detail, one click from a Watch candidate |
| The November and July cases are seeded | They stay as the two seeded candidates; new ones arrive through the feed |
| One approval for the brief | One approval for the brief plus the exposure rating |
| Palette: warm pastel | Palette: blue (section 7) |
| Domains: chips and cards | Domains: Workspace dropdown, one entry for now |
| Exposure | New |
| Feed | New |

Reused unchanged: the Server's access and approved-question path, the layer's session handling, the `rca` schema and judge, the workflow gateway (Temporal) and the decision record.

## 9. Build order

Each step is a small pull request that can be tested without the next one.

1. **Shell and palette:** the blue tokens and the dark-mode pair, the Workspace dropdown at the top right (one entry), IT risk only on first load, new left navigation with the existing Incident brief behind it. UI tests and a screenshot pass at three widths.
2. **Watch with seeded candidates:** `candidates` tables, the November and July cases listed as candidates, the Watch screen and Incident detail. No live feed yet.
3. **Estate data:** the `estate` schema, the event tables for SharePoint and Slack with a replay service that fills them like a Kafka connector would, approved questions for the five, and the grants.
4. **Exposure screen and rating:** the rating rules as a pure module with a gold set (including planted errors, like the judge), the five-question run, the exposure view.
5. **Decision for both:** extend `incident-cluster-rca` so the approval covers brief and rating (the digest includes the rating).
6. **Feed adapter:** RSS first, rule-based filter and clustering, the source health line in Watch. X only once the plan and terms are known.
7. **Server design note for Kumar (a pull request on the Server repo, to be opened with the user's go-ahead):** how an add-on feed and the Kafka-to-Postgres event tables reach the Server as sources (Q5, Q6). It can go in parallel with steps 2 to 4 and gates only step 6 and a real connector.
8. **Pilot hardening:** a real feed run for several days, with Leo's reading of what it caught and missed.

## 10. Questions to answer, and decisions taken

Each question says why it matters and what the build assumes if it stays unanswered, so nothing waits on an answer. Write the answer on the line under each question.

### Decided (2026-11-20, by the user)

- **The firm's own records are simulated** in this release; there is no real system to connect. Invented data and mock SharePoint and Slack services, labelled as invented on screen.
- **A candidate is only ever traced by a person pressing a button**, never automatically.
- **Answers to Q1 to Q7 recorded 2026-11-20** (below). They change three things in this note: the thresholds (section 6.3), how SharePoint and Slack data arrives (sections 5.5 and 6.1: a stream into Postgres), and the Server pull request (section 9).

### For Leo (the risk view)

**Q1. Are the five exposure questions in section 6.2 the right ones, in the right order? What would you replace or add?**
Why it matters: they decide what the rating is built from. Assumed if unanswered: the five as written.
**Answer:** Yes, start with these five, in this order.

**Q2. What should the rating look like to a head of technology risk: four levels (Low, Moderate, High, Critical), a number, or a heat map?**
Why it matters: the rating is the thing people will quote. Assumed if unanswered: four levels, the highest of the five question scores, with the question that set it.
**Answer:** Use the four levels: Low, Moderate, High, Critical.

**Q3. Which news sources would you trust for the feed, and do you want X for the story only?**
Why it matters: the feed is only as good as its sources, and X needs a paid plan we have not bought. Assumed if unanswered: RSS from technical news and official status pages first, no X.
**Answer:** Search for the best RSS feeds and choose a few that fit best. **Follow-up for us, not yet done:** research and propose the feeds (and check their terms) before the feed adapter is built.

**Q4. What is the policy threshold for "overdue" on a security patch, and for "no recovery test", in a bank?**
Why it matters: Q4 and Q5 of the exposure questions score against these numbers. Assumed if unanswered: 15 days overdue and 180 days since a recovery test, shown on screen as demo constants.
**Answer:** Tighten to half of the assumed values: **15 days** overdue for a security patch and **180 days** since a recovery test. Shown on screen as demo constants; they can be relaxed later.

### For Kumar (the platform view)

**Q5. Can an add-on service write new tables in the Server's Postgres, or should the feed go through a Server route?**
Why it matters: today the layer only reads through the Server. Assumed if unanswered: the feed adapter writes to its own schema in the same Postgres and the Server reads it as a source.
**Answer:** Yes: open a Server pull request for Kumar. **Follow-up, not yet opened:** the Server repo is private and is edited by Kumar; the pull request would be a design note (as Server#95 and #102 were) proposing how the feed reaches Postgres and the Server (see Q6).

**Q6. Is there a supported way to put SharePoint and Slack behind the Server as sources, and has either been run against a real tenant?**
Why it matters: our simulation should mimic the real route. Assumed if unanswered: both as generic REST sources (Microsoft Graph and Slack's web API shapes), mock services standing in.
**Answer:** Create a stream into Postgres, using Kafka connectors. Slack and SharePoint activity arrives as events, lands in Postgres tables, and the Server reads those tables as ordinary SQL sources. This replaces the idea of the Server calling Slack and SharePoint over REST. In this release the stream is **simulated**: a replay of invented events into the same tables, so the Kafka-to-Postgres shape is what the demo shows.

**Q7. Will the Workspace list stay the way the Ask app shows it (one Workspace per session), so Agency's dropdown can read it directly?**
Why it matters: the dropdown should not invent its own list. Assumed if unanswered: yes, one Workspace at a time, read from `/app/namespaces`.
**Answer:** One Workspace at a time, as in the Ask app.

## 11. Not in this design

Live X ingestion, real SharePoint and Slack tenants, a model that writes briefs, notification channels (email, Slack posts), multi-firm tenancy, and the BOM and supply chain risk flows. Each is a later step.
