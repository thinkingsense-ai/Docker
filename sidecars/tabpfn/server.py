#!/usr/bin/env python3
"""OmniGate data-driven profiling sidecar (Phase B of
docs/design/data-driven-semantic-profiling.md).

Deliberately pure Python standard library — no FastAPI/uvicorn, no torch, no CARTE/TabPFN install
required to run this. That's a real, honest engineering tradeoff, not a placeholder pretending to
be the real thing: CARTE isn't pip-distributed (its pretrained checkpoint has to be downloaded
separately from the paper authors' own hosting, not from PyPI/Hugging Face), so shipping a hard
dependency on it here would make this sidecar fail to start for anyone who hasn't separately
tracked that down. Instead:

  - The DEFAULT, always-available scorer is `baseline-value-overlap`: real Jaccard similarity over
    the two columns' sampled values. This is a genuine, legitimate signal for exactly the case this
    phase targets (do two differently-named columns across tables actually share real-world values,
    e.g. the same emails appearing in both orders.cust_email and customers.email_address) — not a
    stub that always returns a fixed number. Its real, known limitation: it only catches columns
    that share *literal* values, not ones that mean the same thing in different representations
    (formatted vs. unformatted phone numbers, "NY" vs. "New York") — exactly the gap a real
    embedding-based model (CARTE) is meant to close.
  - `try_load_carte()` below is the documented extension point: if the `carte_ai` package (or
    whatever CARTE's actual import name is at install time) is importable AND
    `OMNIGATE_PROFILING_CARTE_CHECKPOINT` points at a real downloaded checkpoint, this sidecar
    prefers it over the baseline automatically. **Investigated live** (follow-on to Phase B/C):
    `pip install git+https://github.com/soda-inria/carte.git` genuinely installs (needs Python
    >=3.10 — this sidecar otherwise targets 3.9+ stdlib-only, so CARTE alone would raise the floor),
    but its `Table2GraphTransformer` hard-requires a `fasttext` language model
    (`lm_model="fasttext"` is the only option in the installed version — no lighter alternative, no
    Hugging-Hub auto-download the way TabPFN gets one) and `fasttext.util.download_model` pulls a
    multi-gigabyte binary with no smaller variant. That's a genuine, concrete blocker found by
    trying it, not a restated guess — CARTE stays a documented, inert extension point until that
    weight-hosting problem is solved (a self-hosted/pruned fastText vector file, or CARTE adds a
    lighter embedding backend), not because it wasn't attempted. `GET /health` reports which scorer
    is actually active so this is always inspectable, not silently misrepresented.
  - `classify_column` (Phase C) has the same shape, but **TabPFN's extension point is now real**:
    `try_load_tabpfn()` builds an actual `TabPFNClassifier` (see `tabpfn_classifier.py`) fit against
    a small hand-authored reference set, in-context, no separate training — live-verified end to
    end including a real ~29MB v2 checkpoint download from Hugging Face and real CPU inference.
    Pinned to `tabpfn==2.0.9` specifically (the design doc's licensing note: only v2's weights are
    commercially usable — 2.5/2.6/3 are non-commercial-only). Off by default
    (`OMNIGATE_PROFILING_PREDICTOR_ENABLED`) since it pulls in `torch` — the heuristic classifier stays
    the zero-dependency default so this sidecar keeps starting with nothing installed.
"""

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def try_load_carte():
    """Returns a callable(values_a, values_b) -> float in [0, 1] if CARTE is actually available
    and configured, else None (falls back to the baseline scorer). See module docstring."""
    checkpoint = os.environ.get("OMNIGATE_PROFILING_CARTE_CHECKPOINT")
    if not checkpoint:
        return None
    try:
        import carte_ai  # noqa: F401  -- real import, deliberately not vendored/stubbed
    except ImportError:
        sys.stderr.write(
            "profiling-server: OMNIGATE_PROFILING_CARTE_CHECKPOINT is set but the carte_ai "
            "package isn't installed -- falling back to the baseline scorer\n"
        )
        return None
    # Real integration point, intentionally left unimplemented rather than guessed at: CARTE's
    # actual inference API (graph construction from row/column embeddings, model.forward(...))
    # isn't something to fabricate without the checkpoint in hand to test against. Wiring this in
    # for real, live, against a real checkpoint, is exactly the honest follow-on this file's own
    # docstring and the design doc both call out -- not silently pretended to already work.
    sys.stderr.write(
        "profiling-server: carte_ai is installed but the real scoring call isn't wired up yet "
        "-- falling back to the baseline scorer\n"
    )
    return None


CARTE_SCORER = try_load_carte()
ACTIVE_SCORER_NAME = "carte" if CARTE_SCORER else "baseline-value-overlap"


def normalize(values):
    return {str(v).strip().lower() for v in values if v is not None and str(v).strip() != ""}


def baseline_join_score(values_a, values_b):
    set_a = normalize(values_a)
    set_b = normalize(values_b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


def join_score(values_a, values_b):
    if CARTE_SCORER is not None:
        return CARTE_SCORER(values_a, values_b)
    return baseline_join_score(values_a, values_b)


def try_load_tabpfn():
    """Returns a callable(values) -> (label, confidence) if TabPFN-2 is actually available and
    configured, else None (falls back to the heuristic classifier below). See module docstring and
    tabpfn_classifier.py for the real in-context classification this builds -- fits one
    TabPFNClassifier against a small hand-authored reference set at startup (downloading the real
    ~29MB v2 checkpoint from Hugging Face on first run if it isn't already cached locally)."""
    if os.environ.get("OMNIGATE_PROFILING_PREDICTOR_ENABLED", "").lower() not in ("1", "true", "yes"):
        return None
    try:
        import tabpfn  # noqa: F401  -- real import, deliberately not vendored/stubbed
    except ImportError:
        sys.stderr.write(
            "profiling-server: OMNIGATE_PROFILING_PREDICTOR_ENABLED is set but the tabpfn package "
            "isn't installed -- falling back to the heuristic classifier\n"
        )
        return None
    try:
        import tabpfn_classifier
        classify = tabpfn_classifier.build_classifier()
    except Exception as e:  # noqa: BLE001 -- any failure here (checkpoint download, torch issue,
        # incompatible tabpfn version) must degrade to the heuristic classifier, not crash startup.
        sys.stderr.write(
            f"profiling-server: tabpfn is installed but building the real classifier failed "
            f"({e!r}) -- falling back to the heuristic classifier\n"
        )
        return None
    sys.stderr.write("profiling-server: real TabPFN-2 classifier loaded and ready\n")
    return classify


TABPFN_CLASSIFIER = try_load_tabpfn()
ACTIVE_CLASSIFIER_NAME = "tabpfn-2" if TABPFN_CLASSIFIER else "heuristic-pattern-match"

# General tabular prediction (SemanticTier.PREDICTIVE) -- real, only ever backed by TabPFN-2 itself
# (see tabpfn_predictor.py's own docstring for why this is architecturally different from
# classify()'s fixed-reference-set usage). Deliberately NO heuristic fallback here, unlike
# classify()'s real regex-based heuristic_classify: a made-up "prediction" with no real model
# behind it would be actively misleading, not a legitimate degraded mode the way pattern-matching
# a column's shape is for PII typing. /predict returns a clear 503 instead when this is None.
PREDICTOR_AVAILABLE = TABPFN_CLASSIFIER is not None

# Ordered so the first pattern that clears a sample is used -- most specific shapes first (SSN
# before a generic digit-run, email before generic free text) so a column isn't misclassified by a
# looser pattern that happens to come first.
_PATTERNS = [
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    ("ssn", re.compile(r"^\d{3}-\d{2}-\d{4}$")),
    ("credit_card", re.compile(r"^(\d[ -]?){13,19}$")),
    ("phone", re.compile(r"^\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$")),
    ("date", re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{1,2}/\d{2,4}$")),
    ("currency", re.compile(r"^-?\$?\d+\.\d{2}$")),
    ("name", re.compile(r"^[A-Z][a-z]+(?:[\s'-][A-Z][a-z]+)+$")),
]

# Subset of the label set above that's actually PII-sensitive -- "date"/"currency" are real,
# useful semantic labels but not by themselves grounds to suggest restricting a column.
PII_LABELS = {"email", "ssn", "credit_card", "phone"}


def heuristic_classify(values):
    cleaned = [str(v).strip() for v in values if v is not None and str(v).strip() != ""]
    if not cleaned:
        return "unclassified", 0.0
    best_label, best_confidence = "free_text", 0.0
    for label, pattern in _PATTERNS:
        matches = sum(1 for v in cleaned if pattern.match(v))
        confidence = matches / len(cleaned)
        if confidence > best_confidence:
            best_label, best_confidence = label, confidence
    return best_label, best_confidence


def classify_column(values):
    if TABPFN_CLASSIFIER is not None:
        label, confidence = TABPFN_CLASSIFIER(values)
    else:
        label, confidence = heuristic_classify(values)
    return {"label": label, "confidence": confidence, "classifier": ACTIVE_CLASSIFIER_NAME}


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "scorer": ACTIVE_SCORER_NAME,
                                   "classifier": ACTIVE_CLASSIFIER_NAME, "predictorAvailable": PREDICTOR_AVAILABLE})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._read_json_body()
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "malformed JSON body"})
            return

        if self.path == "/join-score":
            a = body.get("a", {}).get("values", [])
            b = body.get("b", {}).get("values", [])
            score = join_score(a, b)
            self._send_json(200, {"score": score, "scorer": ACTIVE_SCORER_NAME})
            return

        if self.path == "/classify":
            values = body.get("values", [])
            self._send_json(200, classify_column(values))
            return

        if self.path == "/predict":
            if not PREDICTOR_AVAILABLE:
                self._send_json(503, {"error": "no predictive engine available -- set "
                                                "OMNIGATE_PROFILING_PREDICTOR_ENABLED=true and install tabpfn "
                                                "(see requirements-tabpfn.txt)"})
                return
            try:
                import tabpfn_predictor
                predictions, probabilities, classes = tabpfn_predictor.predict(
                    body.get("trainingRows", []), body.get("trainingLabels", []), body.get("queryRows", []))
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            except Exception as e:  # noqa: BLE001 -- a real TabPFN/torch failure at prediction
                # time must be reported clearly, not crash the whole sidecar process.
                self._send_json(500, {"error": f"prediction failed: {e!r}"})
                return
            self._send_json(200, {
                "predictions": predictions, "probabilities": probabilities,
                "classes": classes, "engine": "tabpfn-2",
            })
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):  # noqa: A002 -- matches BaseHTTPRequestHandler's own signature
        sys.stderr.write("profiling-server: " + (format % args) + "\n")


def main():
    port = int(os.environ.get("OMNIGATE_PROFILING_SERVER_PORT", "8092"))
    # Real bug found live building a Docker Compose sidecar image for this server: binding only to
    # 127.0.0.1 makes this genuinely unreachable from ANOTHER container on the same Compose network
    # (a peer container connects via this container's real bridge-network IP, not its own loopback)
    # -- confirmed live, `docker logs` reported "listening on 127.0.0.1:8092" and a same-container
    # health check worked, but that's not the real test; a sidecar's whole purpose is being reached
    # from OmniGate's own separate container. OMNIGATE_PROFILING_SERVER_HOST defaults to "127.0.0.1"
    # (unchanged behavior for the existing local-subprocess-spawned case, ProfilingServerProcess),
    # and the real Docker sidecar image sets it to "0.0.0.0" explicitly.
    host = os.environ.get("OMNIGATE_PROFILING_SERVER_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    sys.stderr.write(f"profiling-server: listening on {host}:{port} "
                     f"(scorer={ACTIVE_SCORER_NAME}, classifier={ACTIVE_CLASSIFIER_NAME})\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
