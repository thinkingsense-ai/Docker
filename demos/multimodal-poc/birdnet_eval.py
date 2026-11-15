#!/usr/bin/env python3
"""Score BirdNET on the 48 bird recordings against the manifest species (the same clips and species as embed_audio.py's CLAP test).
Open set: BirdNET picks from all its species. Closed set: restricted to the 8 candidate species (comparable to CLAP's 8-way test).
Needs: pip install birdnet (models are CC BY-NC-SA 4.0: research and other non-commercial use). Run as a script (it starts worker processes)."""
import csv, glob, os, sys, collections
import birdnet
HERE = os.path.dirname(os.path.abspath(__file__)); VER = os.environ.get("BIRDNET_VERSION", "3.0")
def main():
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "manifest/recordings.csv"))) if r["group"] == "bird"]
    truth = {r["recording_id"]: r["species"] for r in rows}; sp = sorted(set(truth.values()))
    files = [os.path.join(HERE, "cache/audio", i + ".mp3") for i in truth]
    model = (birdnet.load("acoustic", VER, "onnx") if VER == "3.0" else birdnet.load("acoustic", VER, "tf", library="litert"))
    out = {}
    names = {s.split("_")[0]: s for s in model.species_list}   # the model writes "Genus species_Common name"
    closed = [names[s] for s in sp]
    for mode, kw in (("open", {}), ("closed", {"custom_species_list": closed})):
        res = model.predict(files, top_k=3, n_workers=1, default_confidence_threshold=0.01, **kw)
        df = res.to_dataframe()
        if mode == "open": print(list(df.columns), len(df), file=sys.stderr)
        scol = next(c for c in df.columns if "species" in c.lower()); ccol = next(c for c in df.columns if "conf" in c.lower()); icol = next(c for c in df.columns if "input" in c.lower() or "file" in c.lower())
        best = {}
        for _, r in df.iterrows():
            rid = os.path.splitext(os.path.basename(str(r[icol])))[0]; name = str(r[scol]).split("_")[0]
            if rid not in best or r[ccol] > best[rid][1]: best[rid] = (str(r[scol]), float(r[ccol]))
        out[mode] = best
    for mode, best in out.items():
        hit = sum(1 for i, t in truth.items() if i in best and t.lower() in best[i][0].lower())
        det = sum(1 for i in truth if i in best)
        print("%s set: species right for %d of %d clips (%d had any detection); chance for closed 8-way is 12%%" % (mode, hit, len(truth), det))
    # a few examples
    for i in list(truth)[:6]: print(i, truth[i], "->", out["open"].get(i), "|", out["closed"].get(i))
    # per-species
    per = collections.defaultdict(lambda: [0, 0])
    for i, t in truth.items():
        per[t][1] += 1; per[t][0] += int(i in out["closed"] and t.lower() in out["closed"][i][0].lower())
    print({k: "%d/%d" % tuple(v) for k, v in per.items()})
if __name__ == "__main__": main()
