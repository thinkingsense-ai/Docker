# Table adapter (CSV, TSV, XLSX)

A thinking-layer adapter (`docs/agency-spec.md` section 4): `GET /adapter` (manifest), `GET /health`, `POST /ingest` (raw body, `X-Filename`). It reads the file with the Python standard library and returns a description: row count, each column's guessed type, empty and distinct counts, a range or the common values, and the first 10 rows. It stores nothing and sends nothing anywhere; the layer drops the file after the call and keeps only this record (private to the uploader, expires after `AGENCY_UPLOAD_HOURS`).

```bash
AGENCY_ADAPTERS=http://table-adapter:8091 docker compose --project-directory . -f demos/treasury-pack/docker-compose.treasury.yml -f addons/thinking-layer/docker-compose.layer.yml -f addons/table-adapter/docker-compose.table.yml up --build
```

The user also needs the Server's "upload files" grant (Admin > users). Tests: `python3 -m unittest discover -s addons/table-adapter/tests`.

**What it does not do.** The table is not loaded into any data source, so the Server cannot answer questions about its rows yet (the record offers no "ask about this" prompts for that reason). A scratch schema readable only by the uploader needs a Server-side route to write rows; that is a Server issue, not built. First sheet only; 100,000 rows and 60 columns; 10 MB; column types are guesses; date cells in XLSX are recognised from the cell's number format; formulas show their last saved value; macros, other sheets and images are ignored. Workbooks with a DTD are refused; the container runs read-only as a non-root user.

Tested with synthetic workbooks built in the tests and one CSV through the layer and the browser. Not tested with files saved by Excel, Numbers or LibreOffice.
