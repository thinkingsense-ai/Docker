"""The workflow decision record, for audit (docs/agency-risk-register-plan.md, section 8, step 8g). Reads the worker's hash-chained decision file (demos/payment-workflow/decisions.py: one JSON line per
finished run, {"prev", "body", "hash"}, hash = sha256(prev + json(body, sorted keys))), verifies the chain, summarises each run, filters, and writes an export. Standard library only, no I/O except reading the file.

What this is NOT: a signed export. A signature that an auditor can trust has to come from the Server (a key the layer does not hold); until that exists (the S2 design note) an export carries the
hash chain and the chain head, so any later change to an exported line is detectable against the file, but nobody has SIGNED it. Whether a person may read this record is decided by the layer's
AGENCY_AUDIT_USERS list, a convenience and not a Server-enforced control (the read-only audit grant does not exist yet: S1)."""
import hashlib, json
from datetime import datetime, timezone

OUTCOMES = ("approved", "declined", "expired", "escalated")


def entry_hash(prev, body): return hashlib.sha256((prev + json.dumps(body, sort_keys=True, default=str)).encode()).hexdigest()


def read(path):
    with open(path, encoding="utf-8") as f: return [json.loads(l) for l in f if l.strip()]


def verify(entries):
    """(ok, first bad entry number (1-based) or None, head hash). A line is bad when its prev is not the hash before it, or its hash does not match its content."""
    prev = "genesis"
    for i, e in enumerate(entries, 1):
        if e.get("prev") != prev or e.get("hash") != entry_hash(prev, e.get("body")): return False, i, prev
        prev = e["hash"]
    return True, None, prev


def definition_of(body):
    if body.get("definition"): return body["definition"]
    return "payment-exception" if "payment_id" in body else "unknown"


def outcome_of(body):
    """approved, declined, expired or escalated. Read from the record's structure first (a rejection, approvals), the outcome text only for the two endings that carry no structure."""
    o = (body.get("outcome") or "").lower()
    if o.startswith("escalated"): return "escalated"
    if o.startswith("no decision"): return "expired"
    if isinstance(body.get("rejection"), dict) or o.startswith(("rejected", "declined", "not recorded as major")): return "declined"
    if body.get("approvals"): return "approved"
    return "approved" if " approved by " in o or o.startswith("recorded as major by") else "declined"


def controls_of(body):
    """The controls or categories a record is about, where the facts say so: the control that owns a root condition (incident brief), the register category (risk assessment), the regulators (major incident)."""
    out = []
    f = body.get("facts") or {}
    for c in f.get("controls") or []:
        if isinstance(c, dict) and c.get("owning_control"): out.append(str(c["owning_control"]))
    p = (body.get("rules") or {}).get("proposal")
    if isinstance(p, dict) and p.get("category"): out.append(str(p["category"]))
    for r in (body.get("rules") or {}).get("regimes") or []: out.append(str(r))
    return sorted(set(out))


def summarize(n, entry):
    b = entry["body"]; ap = [a.get("approver") for a in b.get("approvals") or [] if isinstance(a, dict)]
    rj = b.get("rejection") if isinstance(b.get("rejection"), dict) else None
    times = [b.get("started_at")] + [a.get("at") for a in b.get("approvals") or [] if isinstance(a, dict)] + ([rj.get("at")] if rj else [])
    wb = b.get("write_back") if isinstance(b.get("write_back"), dict) else None
    act = b.get("action") if isinstance(b.get("action"), dict) else None
    return {"n": n, "runId": b.get("decision_id"), "definition": definition_of(b), "outcome": outcome_of(b), "outcomeText": b.get("outcome"), "startedAt": b.get("started_at"),
            "decidedAt": max((t for t in times if t), default=None), "approvers": ap, "rejectedBy": rj.get("approver") if rj else None, "rejectionReason": rj.get("reason") if rj else None,
            "action": act.get("type") if act else None, "controls": controls_of(b), "writeBack": ({"mode": wb.get("mode"), "call": ((wb.get("would_send") or wb.get("sent") or {}).get("path")), "note": wb.get("note")} if wb else None),
            "recommendation": (b.get("recommendation") or {}).get("recommendation") if isinstance(b.get("recommendation"), dict) else None,
            "rulesBlocked": list((b.get("rules") or {}).get("blocks") or []), "hash": entry["hash"], "prev": entry["prev"],
            "evidenceDigest": (act or {}).get("proposal_digest") or (act or {}).get("brief_digest") or (act or {}).get("payload_hash")}


def _day(s):
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except ValueError: return None


def select(rows, definition=None, actor=None, outcome=None, control=None, run=None, since=None, until=None):
    """Filters summaries. actor matches an approver or the rejector (case-insensitive); control is a substring; since and until are dates (YYYY-MM-DD, inclusive) on when it was decided."""
    out = []
    for r in rows:
        if definition and r["definition"] != definition: continue
        if outcome and r["outcome"] != outcome: continue
        if run and r["runId"] != run: continue
        if actor and actor.lower() not in {x.lower() for x in r["approvers"] + ([r["rejectedBy"]] if r["rejectedBy"] else []) if x}: continue
        if control and not any(control.lower() in c.lower() for c in r["controls"]): continue
        d = _day(r["decidedAt"]) if (since or until) else None
        if (since or until) and not d: continue
        if since and d < since: continue
        if until and d > until: continue
        out.append(r)
    return out


def view(path, **filters):
    """The whole record with its chain verdict, and the filtered rows. total is the number of runs in the file."""
    entries = read(path); ok, bad, head = verify(entries)
    rows = [summarize(i, e) for i, e in enumerate(entries, 1)]
    return {"chainValid": ok, "firstBadEntry": bad, "head": head, "total": len(entries), "rows": select(rows, **filters),
            "definitions": sorted({r["definition"] for r in rows}), "controls": sorted({c for r in rows for c in r["controls"]})}


def export(path, **filters):
    """JSON lines: a header line, then each selected entry exactly as stored ({"prev","body","hash"}) with its entry number. The header records the filter, the verdict on the WHOLE chain at the time,
    the chain head, whether the selection is a contiguous run of entries (then it links to itself), and that it is NOT signed."""
    entries = read(path); ok, bad, head = verify(entries)
    keep = {r["n"] for r in select([summarize(i, e) for i, e in enumerate(entries, 1)], **filters)}
    ns = sorted(keep); contiguous = all(b - a == 1 for a, b in zip(ns, ns[1:]))
    header = {"export": "workflow-decision-record", "format": 1, "exportedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "filters": {k: v for k, v in filters.items() if v},
              "entries": len(ns), "totalInFile": len(entries), "chainValidAtExport": ok, "firstBadEntry": bad, "chainHead": head, "selectionContiguous": contiguous,
              "firstEntryPrev": entries[ns[0] - 1]["prev"] if ns else None, "signature": None,
              "how_to_check": "For each entry, sha256(prev + json.dumps(body, sort_keys=True, default=str)) must equal hash, and prev must equal the previous entry's hash (the first entry's prev is in firstEntryPrev). Compare chainHead with the head the operator holds. There is NO signature: it has to come from the Server."}
    return "\n".join([json.dumps(header, sort_keys=True)] + [json.dumps(dict(n=n, **entries[n - 1]), sort_keys=True, default=str) for n in ns]) + "\n"
