# IT-risk exposure estate (simulated)

Build step 3 of [docs/agency-it-risk-flow.md](../../docs/agency-it-risk-flow.md). Invented data for an invented firm so the five exposure questions can be asked and, in step 4, rated. **Nothing here describes a real organisation, and no real SharePoint, Slack, object store or database was read.** Figures are as of 2026-11-20 and stored, not computed from today.

| File | What it is |
|---|---|
| `seed-estate-postgres.sql` | schema `estate`: systems, `scenario_technology` (which technologies a case like November 2026 would hit), access paths, buckets (object-store inventory), patches, changes, dependencies, recovery tests, and the SharePoint and Slack landing tables |
| `demo-questions-estate.json` | the five approved questions with reference SQL, in the proposed order: where the technology runs; critical data and who can reach it; where runbooks and credentials sit; patches and untested changes; dependants and last recovery test |
| `grant-estate.sql` | read-only grant for the app user |
| `docker-compose.estate.yml` | adds the seed and the `estate` schema to the all-packs stack (`agency/local/up.sh` does it) |
| `replay/`, `replay.sh`, `docker-compose.estate-replay.yml` | optional stand-in for the Kafka connector (see below) |

**SharePoint and Slack** are modelled the way a Kafka sink connector in upsert mode lands them: one row per document or message holding its latest state plus the topic, partition and offset of its last event. A real tenant later swaps the replay for the connector; the questions do not change.

**Replay.** Off by default. It applies two events to the running stack, one at a time: a message in a public channel carrying a credential for the production gateway (an invented placeholder, not a secret), and the credentials sheet re-shared with the whole company. Those change the third answer (8 rows become 9, and the credential's audience goes from 3 people to 3,100), so an exposure rating would rise as the events arrive. Re-running is safe; a fresh Postgres volume returns to the start-up state.

```bash
# with the stack up (agency/local/up.sh)
docker run --rm --network agency-risk_default -e ESTATE_REPLAY_SECONDS=5 \
  -v "$PWD/demos/it-risk-estate/replay:/replay:ro" -v "$PWD/demos/it-risk-estate/replay.sh:/replay.sh:ro" \
  --entrypoint sh postgres:16-alpine /replay.sh
```

**Loading into an existing stack.** Postgres runs init files only on a fresh volume, so either wipe it (`agency/local/up.sh down`) or load the seed by hand (`psql ... < seed-estate-postgres.sql`, then `grant-estate.sql`) and re-run `agency/local/up.sh` so the question bank indexes the new questions.

**Checked (2026-11-20):** each reference SQL run on the stack's Postgres (6, 12, 8, 6 and 6 rows); the five questions asked through Agency as `curator` came back with the same row counts, the one whose evidence was read in full was answered from the question bank (`origin: question_bank`, no model), 5 to 9 s each; the replay script run against the stack. **Not checked:** the rating (step 4), the cloud charts (they do not carry this schema), a real connector.

## Field names (step 8f)

The tables are named toward the real systems' fields, so a ServiceNow or Datadog connector later changes the source and not the questions. The values are invented.

| Column | ServiceNow CMDB | Datadog |
|---|---|---|
| `systems.business_criticality` | `business_criticality` | tag `tier` |
| `systems.owned_by`, `support_group` | `owned_by`, `support_group` | tag `team` |
| `systems.environment` | `environment` | tag `env` |
| `systems.install_status`, `end_of_support` | `install_status`, `end_of_support` | none |
| `systems.last_discovered` | `last_discovered` | agent reporting |
| `patches.cve`, `cvss_score` | none | `cve`, `cvss.score` |
| `patches.known_exploited`, `epss` | none | none (public KEV and EPSS lists in the real world) |
| `systems.loss_event` | none | none (plain words: money lost, denial of service to many customers, or a breach with legal risk) |

The mapping is ours and has not been checked against a real tenant. The five approved questions still return `tier` and `owner_team` as column names (aliases), so the Exposure screen, its gold set and the workflow gate are unchanged. The new columns (`end_of_support`, `known_exploited`, `epss`, `loss_event`) are for the Priorities list (step 8c). The CVE identifiers are invented and do not refer to real flaws. Reload the schema (drop and create) on an existing stack.

## Priorities (step 8c)

`demo-questions-priorities.json` holds one approved question, "Which of our systems should we fix first, and what do we know about each?", one row per system: tier, environment, data class, `internet_facing` (new column, invented: the customer portal and the vendor-hosted HR suite), dependants, end of support, open patches, known-exploited and exploit-score figures, untested changes, recovery test age and result, credentials visible too widely, whether the system runs the technology in the November case. The SQL uses joins to grouped tables, no window functions (Server#139).

The ranking is a rules module: `agency/web/src/priorityModel.ts` (the Priorities screen) and `demos/payment-workflow/priority_rules.py` (the port the risk-assessment workflow gate will use in 8d), tested against the same hand-worked gold set `priority_gold.json` (14 cases: the real rows at start-up, with the exposure rating Critical, and after the replay, plus planted errors). Likelihood and impact are each a Low to Critical band, added to a rating; four triggers lift a system to at least High; the order is rating, triggers, dependants, tier. **A method, not a standard; every threshold is a demo constant** (exploit-score bands 0.1 and 0.5, support 90 days, recovery 180 days, three dependants). A system with no recovery record is noted, not treated as never tested. Business impact (the BRP column) is deliberately not scored. Existing stacks need the estate schema dropped and recreated (the new column) and the question seeded.
