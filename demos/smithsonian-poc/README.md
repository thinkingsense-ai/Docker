# Smithsonian POC demo (admin, curator, public)

**Start here: [SETUP.md](SETUP.md)** (install, `./bootstrap.sh`, `demo up`, and a 10-minute walkthrough). The notes below are the short version.

Three people, one semantic layer, on the Smithsonian's own Open Access sample (31,185 rows, 7,792 records, 5 museums), across **two data sources**: the records in PostgreSQL and the museum directory as a CSV in object storage (a small local S3-compatible store that stands in for Amazon S3; needs Docker).
Nothing leaves the machine: the models run locally; a cloud model is only used if `.env` supplies a key.

| Person | Signs in at | Sees |
|---|---|---|
| Admin (`admin` / `Admin-SI-1`) | `http://127.0.0.1:8110/admin` (use `127.0.0.1` for the admin and `localhost` for Ask, or the two sign-ins sign each other out) | Data Sources, the subject-vocabulary review queue (Business Catalog), the Models page with the measured share of answers by small model vs cloud model |
| Curator (`curator` / `Curator-SI-1`) | `http://localhost:8110` | Staff questions across all museums, with charts and a picture gallery |
| Public (`public` / `Public-SI-1`) | `http://localhost:8110` | Open Access (CC0) records only, under an "unofficial prototype" banner, with pictures and links to each record |

## Set up
The quickest way is `./bootstrap.sh` (once) and then `~/smithsonian-poc/demo up` (see SETUP.md). By hand:
1. `demo-smithsonian-poc/load-data.sh` loads the data into Postgres database `si_poc` and puts `museums.csv` in a bucket (`si-poc`) of a local S3-compatible store (port 19110, Docker; SeaweedFS, because MinIO's image is no longer publicly downloadable).
2. Start the local model servers (agentic `:18090`, fast `:8092`, nomic embeddings `:8120`) and run `demo-smithsonian-poc/launch.sh`.
3. Build the vocabulary (admin session cookie needed):
   `curl -b cookies -H 'Content-Type: application/json' -d '{"backend":"si","table":"si_topics","labelColumn":"topic","unitColumn":"unit_code"}' http://localhost:8110/api/ontology/vocabulary/build`
   then download `GET /api/ontology/vocabulary/concepts.csv` to `vocabulary-concepts.csv` and run `load-vocabulary.sh`.
   Today's numbers: 3,509 labels, 53 auto-accepted concepts, 433 merges for a curator to review, 3.1% coverage.
4. `approve-demo-questions.sh` approves the five demo questions.

## Notes
- The subject vocabulary needs a real embedding model (nomic-embed-text). A chat model used for embeddings merges unrelated labels.
- Every record in the sample is already CC0, so the public/staff difference appears once staff-only records are loaded.
- The public user's filter is applied by the access policy (`access-policy.yaml`); the federated path substitutes the filter value as an escaped literal.
