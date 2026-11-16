#!/usr/bin/env python3
"""A stand-in for SAP's S/4HANA Cloud sandbox, for testing without an SAP account. It copies the *shape* of SAP's OData v2 JSON (`{"d": {"results": [...], "__next": url}}`, string decimals, `/Date(ms)/`
dates) and the sandbox's key rule (the key must arrive in a request header named `apikey`, else the same 401 body SAP returns). The invoices and purchase orders are invented, NOT SAP data;
field names follow SAP's API_SUPPLIERINVOICE_PROCESS_SRV and API_PURCHASEORDER_PROCESS_SRV as we understand them (unverified against the real services).
  python3 odata_mock.py [port]"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
KEY = "mock-key"
HEADER = os.environ.get("MOCK_KEY_HEADER", "apikey")      # the real sandbox wants `apikey`; set to Authorization to test a client that can only send that
def ms(y, m, d): return "/Date(%d)/" % (int(time.mktime((y, m, d, 0, 0, 0, 0, 0, 0))) * 1000)
INV = [dict(SupplierInvoice="51000%03d" % n, FiscalYear="2026", CompanyCode="1710", DocumentDate=ms(2026, 10, 1 + n % 28), PostingDate=ms(2026, 10, 2 + n % 27),
            InvoicingParty="1000%02d" % (n % 6), DocumentCurrency="USD", InvoiceGrossAmount="%d.00" % (1000 + 137 * n),
            PaymentBlockingReason=("R" if n % 5 == 0 else ""), SupplierInvoiceStatus=("A" if n % 7 else "B"), PurchasingDocument="450000%02d" % (n % 9))
       for n in range(1, 41)]
PO = [dict(PurchaseOrder="450000%02d" % n, CompanyCode="1710", Supplier="1000%02d" % (n % 6), PurchaseOrderDate=ms(2026, 9, 1 + n), DocumentCurrency="USD", PurchasingProcessingStatus="05")
      for n in range(0, 9)]
SETS = {"/s4hanacloud/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice": INV, "/s4hanacloud/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder": PO}
class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if self.headers.get(HEADER) != KEY: return self._send(401, {"fault": {"faultstring": "Failed to resolve API Key variable request.header.apikey", "detail": {"errorcode": "steps.oauth.v2.FailedToResolveAPIKey"}}})
        rows = SETS.get(u.path)
        if rows is None: return self._send(404, {"error": {"code": "005056A509B11EE1B9A8FEA2E10C8E17", "message": {"lang": "en", "value": "Resource not found for the segment"}}})
        top = int(q.get("$top", ["20"])[0]); skip = int(q.get("$skip", ["0"])[0]); page = rows[skip: skip + top]       # SAP pages with $top/$skip and a `__next` link
        d = {"results": [dict(r, __metadata={"type": "API_SUPPLIERINVOICE_PROCESS_SRV.A_SupplierInvoiceType"}) for r in page]}
        if skip + top < len(rows): d["__next"] = "http://%s%s?$skiptoken=%d&$top=%d" % (self.headers.get("Host"), u.path, skip + top, top)
        self._send(200, {"d": d})
    def log_message(self, *a): pass
if __name__ == "__main__": ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8099), H).serve_forever()
