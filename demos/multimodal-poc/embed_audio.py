#!/usr/bin/env python3
"""Embed every cached recording with CLAP (audio and text in one space) and score zero-shot labelling against the manifest.
Writes out/embeddings.npz and prints accuracy. Needs: torch transformers soundfile scipy numpy."""
import csv, os, sys, numpy as np, soundfile as sf, torch
from scipy.signal import resample_poly
from transformers import ClapModel, ClapProcessor
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
MODEL = os.environ.get("CLAP_MODEL", "laion/clap-htsat-unfused"); SR = 48000; SECS = 10
rows = list(csv.DictReader(open(os.path.join(HERE, "manifest/recordings.csv"))))
dev = "mps" if torch.backends.mps.is_available() else "cpu"
proc = ClapProcessor.from_pretrained(MODEL); model = ClapModel.from_pretrained(MODEL).to(dev).eval()

def load(rid, ext):
    x, sr = sf.read(os.path.join(HERE, "cache/audio", rid + ext), dtype="float32", always_2d=True); x = x.mean(1)
    if sr != SR: g = np.gcd(sr, SR); x = resample_poly(x, SR // g, sr // g).astype("float32")
    return x[: SR * SECS]

A, ids = [], []
for r in rows:
    ext = ".mp3" if r["group"] == "bird" else ".wav"
    try: a = load(r["recording_id"], ext)
    except Exception as e: print("skip", r["recording_id"], e, file=sys.stderr); continue
    with torch.no_grad():
        inp = proc(audio=[a], sampling_rate=SR, return_tensors="pt").to(dev)
        e = model.get_audio_features(**inp)
    e = e if isinstance(e, torch.Tensor) else e.pooler_output
    A.append(torch.nn.functional.normalize(e, dim=-1).cpu().numpy()[0]); ids.append(r["recording_id"])
A = np.stack(A); byid = {r["recording_id"]: r for r in rows}

def text(prompts):
    with torch.no_grad():
        t = model.get_text_features(**proc(text=prompts, return_tensors="pt", padding=True).to(dev))
    t = t if isinstance(t, torch.Tensor) else t.pooler_output
    return torch.nn.functional.normalize(t, dim=-1).cpu().numpy()

def zeroshot(labels, prompt, truth):
    T = text([prompt.format(l) for l in labels]); pred = (A @ T.T).argmax(1)
    ok = [labels[p] == truth(i) for p, i in zip(pred, ids)]; return pred, np.array(ok)

grp = lambda i: "bird" if byid[i]["group"] == "bird" else "fish"
_, ok = zeroshot(["bird", "fish"], "the sound of a {}", grp); print("group (bird vs fish): %.0f%% of %d" % (100 * ok.mean(), len(ok)))
birds = [i for i in ids if byid[i]["group"] == "bird"]; sp = sorted({byid[i]["species"] for i in birds})
common = {r["species"]: (r["common_name"] or r["species"]) for r in rows if r["group"] == "bird"}
Tb = text(["the song of a %s" % common[s] for s in sp]); Ab = np.stack([A[ids.index(i)] for i in birds])
pred = (Ab @ Tb.T).argmax(1); acc = np.mean([sp[p] == byid[i]["species"] for p, i in zip(pred, birds)])
print("bird species zero-shot (%d-way, chance %.0f%%): %.0f%% of %d" % (len(sp), 100 / len(sp), 100 * acc, len(birds)))
# nearest-neighbour: is the closest other recording the same species?
S = A @ A.T; np.fill_diagonal(S, -1); nn = S.argmax(1)
for g in ("bird", "fish"):
    idx = [k for k, i in enumerate(ids) if byid[i]["group"] == g]
    print("nearest recording has same species (%s): %.0f%%" % (g, 100 * np.mean([byid[ids[nn[k]]]["species"] == byid[ids[k]]["species"] for k in idx])))
np.savez(os.path.join(OUT, "embeddings.npz"), ids=np.array(ids), emb=A)
print("embedded", len(ids), "recordings with", MODEL, "on", dev)
