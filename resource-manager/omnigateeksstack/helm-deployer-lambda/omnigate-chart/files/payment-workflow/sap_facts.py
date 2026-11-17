"""Facts for the SAP variant: payment-blocked supplier invoices in SAP's public API sandbox (S/4HANA Cloud sample data, read-only; see ../sap-spike).
Read straight from SAP's OData API with the sandbox key: the app's `/api/query` cannot run against a REST source today (only Ask's own path can), so there is no governed
query path for these yet (Server#102 notes it). Every value that goes into a URL is checked first."""
import gzip, json, os, re, urllib.parse, urllib.request
BASE = os.environ.get("SAP_BASE", "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap").rstrip("/")
SVC = BASE + "/API_SUPPLIERINVOICE_PROCESS_SRV"
HEADER_FIELDS = ("SupplierInvoice,FiscalYear,CompanyCode,InvoicingParty,DocumentCurrency,InvoiceGrossAmount,PaymentBlockingReason,SupplierInvoiceStatus,DocumentDate,PostingDate,"
                 "DueCalculationBaseDate,PaymentTerms,SupplierInvoiceIDByInvcgParty,SupplierInvoiceApprovalStatus,SupplierInvoicePaymentStatus,IsReversed,IsReversal,"
                 "SupplierInvoiceIsCreditMemo,SupplierInvoiceOrigin,InvoiceReference,AccountingDocumentType")
LIST_FIELDS = "SupplierInvoice,FiscalYear,InvoicingParty,DocumentCurrency,InvoiceGrossAmount,PaymentBlockingReason,SupplierInvoiceStatus,DocumentDate"

def _safe(value, pattern):
    if not re.fullmatch(pattern, str(value)): raise ValueError("not a valid SAP key part: %r" % (value,))
    return str(value)

def _get(path_and_query):
    key = os.environ.get("SAP_API_KEY")
    if not key: raise RuntimeError("SAP_API_KEY is not set")
    req = urllib.request.Request(SVC + path_and_query, headers={"apikey": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r: raw = r.read()
    try: raw = gzip.decompress(raw)                      # SAP compresses whether or not it was asked to
    except OSError: pass
    return json.loads(raw)["d"]

def _enc(filter_expr): return urllib.parse.quote(filter_expr, safe="")

def date(sap_date):
    """'/Date(1612396800000)/' -> '2021-02-04'."""
    m = re.search(r"-?\d+", sap_date or "")
    if not m: return None
    import datetime
    return datetime.datetime.fromtimestamp(int(m.group(0)) / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")

_cache = {"at": 0.0, "rows": None}

def pending_invoices():
    """Every payment-blocked invoice (46 in the sandbox, complete because the filter is applied by SAP). Cached for 30 s: the inbox polls, and this is a shared public sandbox."""
    import time
    if _cache["rows"] is not None and time.time() - _cache["at"] < 30: return _cache["rows"]
    rows = _get("/A_SupplierInvoice?$format=json&$top=200&$select=%s&$filter=%s" % (LIST_FIELDS, _enc("PaymentBlockingReason ne ''")))["results"]
    _cache["rows"], _cache["at"] = [{k: v for k, v in r.items() if k != "__metadata"} for r in rows], time.time()
    return _cache["rows"]

def gather(invoice_no, fiscal_year=None):
    n = _safe(invoice_no, r"\d{1,10}")
    if fiscal_year is None:                              # the list view knows the year; find it when only the number is given
        found = _get("/A_SupplierInvoice?$format=json&$top=1&$select=FiscalYear&$filter=%s" % _enc("SupplierInvoice eq '%s'" % n))["results"]
        if not found: raise RuntimeError("SAP has no supplier invoice %s" % n)
        fiscal_year = found[0]["FiscalYear"]
    fy = _safe(fiscal_year, r"\d{4}")
    h = _get("/A_SupplierInvoice(SupplierInvoice='%s',FiscalYear='%s')?$format=json&$select=%s" % (n, fy, HEADER_FIELDS))
    header = {k: v for k, v in h.items() if k != "__metadata"}
    supplier = _safe(header["InvoicingParty"], r"[A-Za-z0-9_\-]{1,20}")
    dups = _get("/A_SupplierInvoice?$format=json&$top=10&$select=SupplierInvoice,FiscalYear,InvoiceGrossAmount,PaymentBlockingReason&$filter=%s" % _enc(
        "InvoicingParty eq '%s' and InvoiceGrossAmount eq %sm and SupplierInvoice ne '%s'" % (supplier, _safe(header["InvoiceGrossAmount"], r"-?\d+(\.\d+)?"), n)))["results"]
    blocked = _get("/A_SupplierInvoice?$format=json&$top=1&$select=SupplierInvoice&$inlinecount=allpages&$filter=%s" % _enc("InvoicingParty eq '%s' and PaymentBlockingReason ne ''" % supplier))
    total = _get("/A_SupplierInvoice?$format=json&$top=1&$select=SupplierInvoice&$inlinecount=allpages&$filter=%s" % _enc("InvoicingParty eq '%s' and FiscalYear eq '%s'" % (supplier, fy)))
    header["DocumentDate"], header["PostingDate"], header["DueCalculationBaseDate"] = date(header.get("DocumentDate")), date(header.get("PostingDate")), date(header.get("DueCalculationBaseDate"))
    return {"system": "sap", "invoice": header,
            "possible_duplicate_invoices": [{k: v for k, v in d.items() if k != "__metadata"} for d in dups],
            "supplier": {"id": supplier, "blocked_invoices": int(blocked.get("__count", 0)), "invoices_in_the_same_fiscal_year": int(total.get("__count", 0))}}
