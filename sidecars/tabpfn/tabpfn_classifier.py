"""Real TabPFN-2 integration for column semantic/PII typing (Phase C follow-on).

TabPFN is an *in-context* tabular classifier: it never needs a separate training phase against our
data. Instead you `fit()` it once against a small labeled reference set, and it predicts new rows
by attending over that reference set at inference time — a genuine, intended use of the model, not
a workaround. So the design here is:

1. Turn each sampled column value into a small vector of cheap, real shape/content features
   (length, digit ratio, has "@", has "-", etc.) — `extract_features`.
2. A hand-authored reference set (`REFERENCE_EXAMPLES`) of a few real examples per label
   (email/ssn/credit_card/phone/date/currency/name/free_text), run through the same feature
   extractor.
3. Fit one `TabPFNClassifier` against that reference set at sidecar startup (cheap — in-context,
   not gradient training), reused for every `/classify` request after that.
4. Classifying a column: extract features for every sampled value, `predict_proba` all of them at
   once, take the label with the highest *mean* probability across the column's values (not just a
   majority vote of per-value argmaxes — a column that's consistently "pretty confident it's an
   SSN" should win over one that's split evenly between two labels), and report that mean
   probability as the confidence.

Pinned to TabPFN v2 specifically (`tabpfn==2.0.9`, not whatever `pip install tabpfn` resolves to
latest) per the design doc's own licensing note: v2's weights are the Prior Labs License
(Apache-2.0 + attribution, usable commercially); 2.5/2.6/3's weights are non-commercial-only.
"""

import re

_DIGIT_RE = re.compile(r"\d")
_ALPHA_RE = re.compile(r"[A-Za-z]")
_UPPER_RE = re.compile(r"[A-Z]")

LABELS = ["email", "ssn", "credit_card", "phone", "date", "currency", "name", "free_text"]

# A handful of real, hand-authored examples per label -- this IS the "training" TabPFN needs, used
# entirely in-context at inference time, not persisted anywhere durable and never derived from real
# customer data (these are synthetic/canonical examples, not sampled column values).
REFERENCE_EXAMPLES = {
    "email": ["alice@example.com", "bob.smith@company.org", "j.doe123@mail.co"],
    "ssn": ["123-45-6789", "987-65-4321", "555-12-3456"],
    "credit_card": ["4111111111111111", "5500-0000-0000-0004", "3400 0000 0000 009"],
    "phone": ["555-123-4567", "(212) 555-0100", "+1 415 555 0198"],
    "date": ["2024-01-15", "2023-12-31", "07/04/2022"],
    "currency": ["19.99", "$1200.00", "-45.50"],
    "name": ["Alice Johnson", "Bob Smith", "Carol White"],
    "free_text": ["some notes about this row", "customer requested a callback", "N/A"],
}


def extract_features(value):
    """A value -> an 11-dim real-valued feature vector describing its shape (never its raw
    content beyond these coarse statistics) -- this is what's actually fed to TabPFN, not the raw
    string, so the model reasons about shape/format the same way the heuristic regexes do, just
    learned from the reference set instead of hand-picked regexes."""
    s = str(value).strip()
    length = len(s)
    if length == 0:
        return [0.0] * 11
    digit_count = len(_DIGIT_RE.findall(s))
    alpha_count = len(_ALPHA_RE.findall(s))
    upper_count = len(_UPPER_RE.findall(s))
    return [
        float(length),
        digit_count / length,
        alpha_count / length,
        upper_count / length,
        1.0 if "@" in s else 0.0,
        s.count("-") / length,
        s.count(".") / length,
        1.0 if "/" in s else 0.0,
        1.0 if "$" in s else 0.0,
        s.count(" ") / length,
        1.0 if s.replace(",", "").replace(".", "").replace("-", "").isdigit() else 0.0,
    ]


def build_classifier():
    """Fits one real TabPFNClassifier against REFERENCE_EXAMPLES, once. Returns a
    callable(values) -> (label, confidence). Raises if tabpfn/torch aren't actually importable or
    the checkpoint can't be obtained -- the caller (server.py's try_load_tabpfn) is what decides to
    fall back to the heuristic classifier on failure, this function doesn't hide errors."""
    import numpy as np
    from tabpfn import TabPFNClassifier

    x_train = []
    y_train = []
    for label, examples in REFERENCE_EXAMPLES.items():
        for example in examples:
            x_train.append(extract_features(example))
            y_train.append(label)

    classifier = TabPFNClassifier(device="cpu")
    classifier.fit(np.array(x_train), np.array(y_train))

    def classify(values):
        cleaned = [v for v in values if v is not None and str(v).strip() != ""]
        if not cleaned:
            return "unclassified", 0.0
        x_query = np.array([extract_features(v) for v in cleaned])
        proba = classifier.predict_proba(x_query)
        mean_proba = proba.mean(axis=0)
        best_index = int(mean_proba.argmax())
        return classifier.classes_[best_index], float(mean_proba[best_index])

    return classify
