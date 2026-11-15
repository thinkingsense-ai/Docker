#!/usr/bin/env python3
"""Run BirdNET on the 48 bird recordings and write manifest/birdnet_annotations.csv: the model's top 3 species per recording, in two modes.
  open    BirdNET chooses from all its species (no prior knowledge).
  closed  restricted to the species expected for the place and season (here: the 8 candidate species).
One row per recording, mode and rank, with the model's confidence (max over the clip's 3 s windows). Labels are model output: they sit beside the curated
species in the recordings table and never replace it. Needs: pip install birdnet (models CC BY-NC-SA 4.0). Run as a script (it starts worker processes)."""
import csv, os, sys
import birdnet
HERE = os.path.dirname(os.path.abspath(__file__)); VER = os.environ.get("BIRDNET_VERSION", "3.0")
def main():
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "manifest/recordings.csv"))) if r["group"] == "bird"]
    ids = [r["recording_id"] for r in rows]; sp = sorted({r["species"] for r in rows})
    files = [os.path.join(HERE, "cache/audio", i + ".mp3") for i in ids]
    model = birdnet.load("acoustic", VER, "onnx")
    names = {s.split("_")[0]: s for s in model.species_list}   # the model writes "Genus species_Common name"
    closed = [names[s] for s in sp]
    out = []
    for mode, kw in (("open", {}), ("closed", {"custom_species_list": closed})):
        df = model.predict(files, top_k=5, n_workers=1, default_confidence_threshold=0.01, **kw).to_dataframe()
        scol = next(c for c in df.columns if "species" in c.lower()); ccol = next(c for c in df.columns if "conf" in c.lower())
        icol = next(c for c in df.columns if "input" in c.lower() or "file" in c.lower())
        best = {}                                   # (recording, species label) -> max confidence over windows
        for _, r in df.iterrows():
            k = (os.path.splitext(os.path.basename(str(r[icol])))[0], str(r[scol])); best[k] = max(best.get(k, 0.0), float(r[ccol]))
        for rid in ids:
            cand = sorted(((c, lab) for (i, lab), c in best.items() if i == rid), reverse=True)[:3]
            for rank, (c, lab) in enumerate(cand, 1):
                sci, _, common = lab.partition("_")
                out.append(dict(recording_id=rid, model="BirdNET", model_version=VER, mode=mode, rank=rank, scientific_name=sci, common_name=common, confidence=round(c, 4)))
    path = os.path.join(HERE, "manifest/birdnet_annotations.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(len(out), "rows ->", path, file=sys.stderr)
if __name__ == "__main__": main()
