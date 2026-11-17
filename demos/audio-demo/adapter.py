"""The audio demo seen as a thinking-layer adapter (docs/agency-spec.md section 4): a manifest and a function that turns an identify() result into an ingest record.
No heavy imports here, so it is unit-tested without torch (tests/test_adapter.py)."""
EXTS = [".wav", ".mp3", ".flac", ".ogg"]
MIMES = ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/flac", "audio/ogg"]
MAX_BYTES = 40_000_000
MIN_CONFIDENCE = 0.3     # a demo constant, not a calibrated threshold: below it the page offers no species-specific questions

MANIFEST = {
    "id": "audio-birdnet-clap", "title": "Bird and fish sounds (BirdNET + CLAP)", "kind": "audio", "version": "1",
    "accepts": {"extensions": EXTS, "mime": MIMES}, "maxBytes": MAX_BYTES,
    "nonCommercial": True,
    "licence": "BirdNET weights are CC BY-NC-SA 4.0 and the recordings are non-commercial: demo and research use only.",
    "notes": "First minute of the clip. BirdNET is built for birds; fish clips usually give nothing confident. Nothing here is a measured accuracy for your data.",
}


def accepts(name, mime=None):
    n = (name or "").lower()
    return any(n.endswith(e) for e in EXTS) or (mime or "").split(";")[0].strip().lower() in MIMES


def prompts_ok(exp): return bool(exp) and exp[0]["confidence"] >= MIN_CONFIDENCE


def record(result, name):
    """result is engine.identify()'s dict (or {'error': ...}). Returns {'result', 'notes', 'licence', 'askPrompts'} for the layer."""
    if "error" in result: raise ValueError(result["error"])
    notes = []
    exp, allb = result.get("birdnet_expected") or [], result.get("birdnet_all") or []
    if exp and allb and exp[0]["scientific"] != allb[0]["scientific"]:
        notes.append("The expected-species and unaided answers differ: an unaided answer can be confidently wrong.")
    if not exp: notes.append("BirdNET found nothing confident among the collection's species.")
    elif exp[0]["confidence"] < MIN_CONFIDENCE:
        notes.append("BirdNET's best guess is only %d%%: not confident enough to name a species, so no species questions are offered." % round(exp[0]["confidence"] * 100))
    if result.get("group", {}).get("guess") == "fish": notes.append("The audio vector leans towards fish; BirdNET is not built for fish.")
    sp = result.get("species"); prompts = []
    if sp and exp and exp[0]["confidence"] >= MIN_CONFIDENCE:
        sci = sp["scientific"]
        prompts = ["How many recordings do we have of %s, and from which countries?" % sci,
                   "Which licences cover the recordings of %s?" % sci,
                   "How many Smithsonian specimens of %s have coordinates?" % sci,
                   "Which recordings sound most like the recording %s?" % ((result.get("nearest") or [{}])[0].get("id") or "xc1072993")]
    return {"result": {"seconds": result.get("seconds"), "group": result.get("group"), "expected": exp, "unaided": allb[:1],
                       "nearest": [{k: c.get(k) for k in ("id", "species", "common", "country", "license", "similarity")} for c in result.get("nearest", [])],
                       "species": sp if prompts_ok(exp) else None, "name": name},
            "notes": notes, "licence": MANIFEST["licence"], "askPrompts": prompts}
