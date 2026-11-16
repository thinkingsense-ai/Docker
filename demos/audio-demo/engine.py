"""The models and the curated data behind the audio demo. identify(samples, sr) -> a JSON-ready dict.
BirdNET (species, with confidence) and CLAP (sounds-alike, and bird versus fish) run in this process; the curated side reads ../multimodal-poc/manifest.
Models: BirdNET is CC BY-NC-SA 4.0 (non-commercial). The recordings are non-commercial too: demo and research use only."""
import csv, os, threading, numpy as np
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); POC = os.environ.get("POC_DIR", os.path.join(HERE, "..", "multimodal-poc"))
CLAP = os.environ.get("CLAP_MODEL", "laion/clap-htsat-unfused"); BIRDNET = os.environ.get("BIRDNET_VERSION", "3.0")
LOCK = threading.Lock(); _S = {}
def rows(name): return list(csv.DictReader(open(os.path.join(POC, "manifest", name))))
def state():
    if _S: return _S
    import torch, birdnet
    from transformers import ClapModel, ClapProcessor
    rec = {r["recording_id"]: r for r in rows("recordings.csv")}; spec = {r["species"]: r for r in rows("usnm_specimens.csv")}
    d = np.load(os.path.join(POC, "out", "embeddings.npz")); ids = [str(i) for i in d["ids"]]
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    proc = ClapProcessor.from_pretrained(CLAP); clap = ClapModel.from_pretrained(CLAP).to(dev).eval()
    bn = birdnet.load("acoustic", BIRDNET, "onnx"); names = {s.split("_")[0]: s for s in bn.species_list}
    birds = sorted({r["species"] for r in rec.values() if r["group"] == "bird"})
    _S.update(rec=rec, spec=spec, ids=ids, A=d["emb"], proc=proc, clap=clap, dev=dev, bn=bn, torch=torch, expected=[names[s] for s in birds], birds=birds)
    T = _text(["the sound of a bird", "the sound of a fish"]); _S["T"] = T
    return _S
def _text(prompts):
    s = _S; torch = s["torch"]
    with torch.no_grad(): t = s["clap"].get_text_features(**s["proc"](text=prompts, return_tensors="pt", padding=True).to(s["dev"]))
    t = t if isinstance(t, torch.Tensor) else t.pooler_output
    return torch.nn.functional.normalize(t, dim=-1).cpu().numpy()
def _embed(x48):
    s = _S; torch = s["torch"]
    with torch.no_grad():
        e = s["clap"].get_audio_features(**s["proc"](audio=[x48[: 48000 * 10]], sampling_rate=48000, return_tensors="pt").to(s["dev"]))
    e = e if isinstance(e, torch.Tensor) else e.pooler_output
    return torch.nn.functional.normalize(e, dim=-1).cpu().numpy()[0]
def resample(x, sr, to):
    from scipy.signal import resample_poly
    if sr == to: return x.astype("float32")
    g = np.gcd(int(sr), to); return resample_poly(x, to // g, int(sr) // g).astype("float32")
def _top(df, k=3):
    if len(df) == 0: return []
    scol = next(c for c in df.columns if "species" in c.lower()); ccol = next(c for c in df.columns if "conf" in c.lower()); best = {}
    for _, r in df.iterrows(): best[str(r[scol])] = max(best.get(str(r[scol]), 0.0), float(r[ccol]))
    out = []
    for lab, c in sorted(best.items(), key=lambda kv: -kv[1])[:k]:
        sci, _, common = lab.partition("_"); out.append({"scientific": sci, "common": common, "confidence": round(c, 3)})
    return out
def identify(x, sr, exclude=None):
    """x: mono float samples. exclude: a pack recording id to leave out of the nearest list (when the clip is itself from the pack)."""
    with LOCK:
        s = state(); x = x.astype("float32"); secs = len(x) / sr
        if secs < 1: return {"error": "The clip is shorter than one second."}
        x48 = resample(x, sr, 48000); e = _embed(x48)
        grp = ["bird", "fish"]; gs = (s["T"] @ e); bird_vs_fish = {"guess": grp[int(gs.argmax())], "margin": round(float(abs(gs[0] - gs[1])), 3)}
        res = {"seconds": round(secs, 1), "group": bird_vs_fish}
        kw = dict(top_k=5, n_workers=1, default_confidence_threshold=0.01)
        res["birdnet_expected"] = _top(s["bn"].predict_arrays((x, sr), custom_species_list=s["expected"], **kw).to_dataframe())
        res["birdnet_all"] = _top(s["bn"].predict_arrays((x, sr), **kw).to_dataframe())
        sim = s["A"] @ e; order = [i for i in np.argsort(-sim) if s["ids"][i] != exclude][:5]
        res["nearest"] = [_card(s, s["ids"][i], float(sim[i])) for i in order]
        top = (res["birdnet_expected"] or [None])[0]
        res["species"] = _species(s, top["scientific"]) if top and top["scientific"] in s["birds"] else None
        return res
def _card(s, rid, sim=None):
    r = s["rec"][rid]
    return {"id": rid, "species": r["species"], "common": r["common_name"], "group": r["group"], "call_type": r["behavior"], "country": r["country"], "recorded_on": r["recorded_on"],
            "recordist": r["recordist"], "license": r["license"], "similarity": None if sim is None else round(sim, 3), "audio": "/audio/" + rid, "image": "/image/" + rid, "source": r["source_ref"]}
def _species(s, sci):
    rs = [r for r in s["rec"].values() if r["species"] == sci]; sp = s["spec"].get(sci)
    return {"scientific": sci, "common": rs[0]["common_name"] if rs else "", "recordings": len(rs), "countries": sorted({r["country"] for r in rs if r["country"]}),
            "call_types": dict(Counter(r["behavior"] or "unspecified" for r in rs)), "licenses": sorted({r["license"] for r in rs}),
            "usnm_specimens": int(sp["usnm_specimens"]) if sp else None, "usnm_with_coordinates": int(sp["usnm_with_coordinates"]) if sp else None,
            "commercial_use": any("NC" not in r["license"] for r in rs)}
def sample_list():
    s = state(); return [{"id": i, "group": s["rec"][i]["group"]} for i in s["ids"]]
def truth(rid):
    s = state(); c = _card(s, rid); return c
