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
