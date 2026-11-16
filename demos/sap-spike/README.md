# SAP read spike

Can we read SAP through our own app? This mounts SAP's **public API sandbox** (S/4HANA Cloud sample data, read-only, not ours) as a REST source and asks questions in Ask.
Written 2026-11-16 with a free SAP ID; the sandbox key is shown on any API's page at https://api.sap.com (Show API Key).

## Run it

```bash
cp demos/sap-spike/.env.example demos/sap-spike/.env     # put your key in it; .env is git-ignored
export OMNIGATE_LLM_API_KEY=sk-ant-...
OMNIGATE_JAR=/path/to/omnigate.jar demos/sap-spike/run.sh   # Ask at http://localhost:8087 (demo / demo); stop: docker rm -f sap-spike
```

`OMNIGATE_JAR` must be a jar with the REST-source changes in the Server PR "REST source: key header name, nested records, gzip" (the released v0.10.18 cannot read SAP, see below). Without a key, `odata_mock.py` serves the same response shape for tests (invented data).

## What we found

**It works.** On the real sandbox, Ask answered "How many supplier invoices are blocked for payment, and what is the largest blocked invoice amount?" with **46 and 484,614.90**, and "Which suppliers have the most blocked invoices?" with USSU-VSF12 45, USSU-VSF85 1. Both match SAP's own API read directly (`$filter=PaymentBlockingReason ne ''` counts 46; the largest row is 484,614.90).

**The released app (v0.10.18) cannot read SAP.** Each of these was seen, not assumed:
1. **The key header.** The sandbox only accepts the key in a header named `apikey` (its 401 says "Failed to resolve API Key variable request.header.apikey"). The REST source can only send `Authorization`, so it gets HTTP 401.
2. **Nested records.** SAP's OData v2 answers `{"d": {"results": [...]}}`. `recordsField` and `nextPageField` were a single top-level key, so the app failed with "has no 'd.results' field".
3. **gzip.** The sandbox compresses the body even when not asked (`content-encoding: gzip`); the app's HTTP client does not decompress it.
4. **XML by default.** OData v2 answers in XML unless told otherwise; the source sends no `Accept` header. This kit puts `$format=json` in each table path instead of changing code.
The Server PR adds an optional `authHeaderName`, dotted paths for `recordsField` / `nextPageField`, and gzip handling, with tests (all existing REST tests still pass).

**The sandbox is big, so a table is a bounded window, not a whole table.** About **9.9 million** supplier invoices. Asking for all of them (no `$top`) fails after about 32 seconds with HTTP 500 (a SAP runtime error); `$top=500` answers in about 1.3 seconds, and `$skip` works. So each table in `run.sh` is a filtered, bounded query written into its path: `blocked_invoices` (the 46 payment-blocked ones, complete), `recent_invoices` (up to 300 from fiscal year 2021), `purchase_orders` (the first 300). **Counts are over the window**: "How many purchase orders" answers 300 because that is the window, not SAP's total.

**What the data looks like.** Dates are `/Date(ms)/` strings and amounts are strings. The first 500 invoices (fiscal year 2016) have no payment block; the 46 blocked ones are fiscal year 2021 with reason `A`. Which status code means what (`5`, `D`, `B`, `3` all appear) was not checked, so do not read them yet.

## Not done, and why it matters for the workflow

- **Invoice to purchase order.** The invoice header has no PO field (the link sits on the invoice items, reached through `$expand`), and the REST source flattens only scalar fields, so a three-way match (invoice, PO, receipt) cannot be done yet. This is the real gap for the invoice-exception workflow.
- **No workflow dry run on a SAP invoice yet.** The payment-exception example reads Treasury data; pointing it at these tables is the next step.
- **Write-back is untested.** The sandbox is read-only per SAP's community; we did not try the release call. A real tenant needs OAuth or basic auth and a communication user, not a sandbox key.
- **Only the supplier-invoice and purchase-order services were tried.** The invoice-service paths were not checked against SAP's documentation beyond what the sandbox accepted.
