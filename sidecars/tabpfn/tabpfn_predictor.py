"""Real TabPFN-2 integration for GENERAL tabular prediction -- the predictive half of the
"Semantic Router" architecture (com.omnigate.nl2sql.SemanticTier.PREDICTIVE), separate from
tabpfn_classifier.py's narrow column-typing use case.

The key real difference from tabpfn_classifier.py, stated plainly: that module fits ONE classifier
once, at sidecar startup, against a small hand-authored reference set reused for every request.
General prediction has no such fixed reference set -- the caller supplies a real, arbitrary
training set (real historical rows with a real target column) and a real query set on EVERY
request. TabPFN's own in-context design makes this the correct, intended usage (no separate
training phase, no persisted model artifact to reuse across requests) -- but it does mean this
module fits a fresh TabPFNClassifier per request rather than once at startup. This is a genuine,
real architectural difference from XGBoost-style train-once/predict-many, not an oversight.

Deliberately narrow scope for this first, spike version: numeric feature matrices only (the caller
is responsible for turning categorical/text columns into numbers before calling this -- see this
package's own real, stated limitation: no feature-encoding pipeline exists here or on the Java
side yet). Both classification (discrete labels) and regression (a continuous numeric target) are
real TabPFN capabilities; this first version only wires up classification (TabPFNClassifier) --
TabPFNRegressor is a real, separate follow-on, not attempted here.
"""


def predict(training_rows, training_labels, query_rows):
    """training_rows: list of list[float]. training_labels: list of str (or anything TabPFN's
    classes_ can hold). query_rows: list of list[float]. Returns (predictions, probabilities,
    classes) where predictions is list[str], probabilities is list[list[float]] (one row per
    query row, one column per class, same order as `classes`), classes is list[str]. Raises if
    tabpfn/torch aren't actually importable, or the inputs are malformed -- the caller (server.py)
    decides how to report that as an HTTP error; this function doesn't hide failures."""
    import numpy as np
    from tabpfn import TabPFNClassifier

    if not training_rows or not training_labels:
        raise ValueError("trainingRows and trainingLabels must both be non-empty")
    if len(training_rows) != len(training_labels):
        raise ValueError(
            f"trainingRows has {len(training_rows)} row(s) but trainingLabels has "
            f"{len(training_labels)} -- they must be the same length")
    if not query_rows:
        raise ValueError("queryRows must be non-empty")

    x_train = np.array(training_rows, dtype=float)
    y_train = np.array(training_labels)
    x_query = np.array(query_rows, dtype=float)

    classifier = TabPFNClassifier(device="cpu")
    classifier.fit(x_train, y_train)

    proba = classifier.predict_proba(x_query)
    classes = [str(c) for c in classifier.classes_]
    predictions = [classes[int(row.argmax())] for row in proba]
    probabilities = [[float(p) for p in row] for row in proba]
    return predictions, probabilities, classes
