#!/bin/bash
# SAP read spike: the app with SAP's public API sandbox mounted as a REST source (read-only). From the repository root:
#   cp demos/sap-spike/.env.example demos/sap-spike/.env     # then put your sandbox key in it (api.sap.com > an API > Show API Key); .env is git-ignored
#   export OMNIGATE_LLM_API_KEY=sk-ant-...                    # for Ask
#   OMNIGATE_JAR=/path/to/omnigate.jar demos/sap-spike/run.sh # a jar that has the REST-source changes (Server PR "REST source: header name, nested records, gzip"); see README
# Ask is then at http://localhost:8087 (demo / demo). Stop it with: docker rm -f sap-spike
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
KEY=$(sed -n 's/^SAP_API_KEY=//p' "$HERE/.env" | tr -d "\"' \r"); [ -n "$KEY" ] || { echo "Put SAP_API_KEY=<your sandbox key> in demos/sap-spike/.env" >&2; exit 1; }
[ -f "${OMNIGATE_JAR:-}" ] || { echo "Set OMNIGATE_JAR to an omnigate.jar built with the REST-source changes (the released v0.10.18 cannot read SAP: see README)." >&2; exit 1; }
[ -n "${OMNIGATE_LLM_API_KEY:-}" ] || { echo "Set OMNIGATE_LLM_API_KEY (Anthropic) so Ask can answer." >&2; exit 1; }
IMAGE=${OMNIGATE_IMAGE:-sap-spike-app}; PORT=${PORT:-8087}
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building the app image ($IMAGE) from the repository Dockerfile..."; docker build -q -t "$IMAGE" "$HERE/../.." >/dev/null
fi
# One source, three read-only tables. SAP's API holds millions of invoices and refuses an unbounded read (HTTP 500), so each table is a bounded, filtered window written into its path.
# $format=json is in every path because OData answers in XML unless told otherwise and the source sends no Accept header.
SEL_INV='SupplierInvoice,FiscalYear,CompanyCode,InvoicingParty,DocumentCurrency,InvoiceGrossAmount,PaymentBlockingReason,SupplierInvoiceStatus,DocumentDate,DueCalculationBaseDate,PaymentTerms'
SEL_PO='PurchaseOrder,CompanyCode,Supplier,PurchaseOrderDate,DocumentCurrency,PurchasingProcessingStatus'
MODEL=$(python3 - "$KEY" "$SEL_INV" "$SEL_PO" <<'PY'
import json, sys
key, inv, po = sys.argv[1:4]
inv_path = "/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice"
tables = {
  "blocked_invoices": inv_path + "?$format=json&$filter=PaymentBlockingReason%20ne%20%27%27&$top=200&$select=" + inv,
  "recent_invoices": inv_path + "?$format=json&$filter=FiscalYear%20eq%20%272021%27&$top=300&$select=" + inv,
  "purchase_orders": "/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder?$format=json&$top=300&$select=" + po,
}
op = {"baseUrl": "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap", "tables": tables, "authHeader": key, "authHeaderName": "apikey", "recordsField": "d.results", "nextPageField": "d.__next"}
print(json.dumps({"version": "1.0", "schemas": [{"name": "sap", "type": "custom", "factory": "com.omnigate.calcite.RestSchemaFactory", "operand": op}]}, separators=(",", ":")))
PY
)
docker rm -f sap-spike >/dev/null 2>&1 || true
docker run -d --name sap-spike -p "$PORT:8080" -v "$OMNIGATE_JAR:/app/omnigate.jar:ro" \
  -e OMNIGATE_INSECURE=true -e "OMNIGATE_BACKENDS=sap=jdbc:calcite:model=inline:$MODEL|x|x" -e OMNIGATE_ROUTER_SCHEMA_RULES=sap:sap \
  -e OMNIGATE_LLM_MODE=cloud-first -e OMNIGATE_LLM_API_KEY="$OMNIGATE_LLM_API_KEY" \
  -e 'OMNIGATE_APP_USERS=demo:lJX+xXgLcPmnjyXStA9VQQ==:HdoV/jHar1OSBbnTk8Iu8fbLcoBGFJ/Qe83zERd4Mac=::' \
  -e OMNIGATE_APP_BANNER="SAP read spike: SAP's public API sandbox (read-only sample data, not ours)." "$IMAGE" >/dev/null
echo "Starting on http://localhost:$PORT (demo / demo); logs: docker logs -f sap-spike"
