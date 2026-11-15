#!/usr/bin/env python3
"""Embed the 72 spectrogram images with CLIP (image and text in one space) and measure what the vectors know (use case 6).
Writes out/image_embeddings.npz. Needs: torch transformers pillow numpy; out/embeddings.npz from embed_audio.py for the fusion test.
Tests: same-species nearest neighbour, bird vs fish, whether the image vectors add anything to the audio vectors, and what is just how each source draws its images."""
import csv, os, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
HERE = os.path.dirname(os.path.abspath(__file__)); MODEL = os.environ.get("CLIP_MODEL", "openai/clip-vit-base-patch32")
rows = list(csv.DictReader(open(os.path.join(HERE, "manifest/recordings.csv")))); byid = {r["recording_id"]: r for r in rows}
dev = "mps" if torch.backends.mps.is_available() else "cpu"
proc = CLIPProcessor.from_pretrained(MODEL); model = CLIPModel.from_pretrained(MODEL).to(dev).eval()
norm = lambda t: torch.nn.functional.normalize(t if isinstance(t, torch.Tensor) else t.pooler_output, dim=-1).cpu().numpy()
def embed(im, mode):
    """crop: CLIP's default centre crop (a wide strip loses almost all of it). squash: whole image resized to a square. tiles: the image cut into square-ish tiles, vectors averaged."""
    if mode == "squash": ims = [im.resize((224, 224))]
    elif mode == "tiles":
        w, h = im.size; n = max(1, round(w / h)); n = min(n, 24); ims = [im.crop((int(k * w / n), 0, int((k + 1) * w / n), h)).resize((224, 224)) for k in range(n)]
    else: ims = [im]
    with torch.no_grad(): v = norm(model.get_image_features(**proc(images=ims, return_tensors="pt").to(dev)))
    v = v.mean(0); return v / np.linalg.norm(v)
MODES = ("crop", "squash", "tiles"); ids, size, EM = [], {}, {m: [] for m in MODES}
for r in rows:
    im = Image.open(os.path.join(HERE, "cache/image", r["recording_id"] + ".png")).convert("RGB"); size[r["recording_id"]] = im.size; ids.append(r["recording_id"])
    for m in MODES: EM[m].append(embed(im, m))
EM = {m: np.stack(v) for m, v in EM.items()}
grp = np.array([byid[i]["group"] for i in ids]); spc = np.array([byid[i]["species"] for i in ids])
def nn_rate(S, mask, k=1):
    S = S.copy(); np.fill_diagonal(S, -9); idx = np.where(mask)[0]
    return np.mean([np.mean(spc[np.argsort(-S[i])[:k]] == spc[i]) for i in idx])
for m in MODES:
    X = EM[m]; Sm = X @ X.T; g = np.array([byid[i]["group"] for i in ids]); sp = np.array([byid[i]["species"] for i in ids])
    print("preprocessing %-6s image->image same species, nearest: birds top1 %.0f%% top5 %.0f%%; fish top1 %.0f%%" % (m, 100 * nn_rate(Sm, g == "bird"), 100 * nn_rate(Sm, g == "bird", 5), 100 * nn_rate(Sm, g == "fish")))
best = os.environ.get("IMG_MODE", "tiles"); E = EM[best]; np.savez(os.path.join(HERE, "out/image_embeddings.npz"), ids=np.array(ids), emb=E); print("using", best, "for the rest")
Si = E @ E.T
print("image->image same species among nearest: birds top1 %.0f%% top5 %.0f%%; fish top1 %.0f%%" % (100 * nn_rate(Si, grp == "bird"), 100 * nn_rate(Si, grp == "bird", 5), 100 * nn_rate(Si, grp == "fish")))
# the source draws its images in its own style: can the image vectors tell bird from fish without any sound in them?
with torch.no_grad(): T = norm(model.get_text_features(**proc(text=["a spectrogram of a bird song", "a spectrogram of a fish sound"], return_tensors="pt", padding=True).to(dev)))
print("zero-shot bird vs fish from the picture: %.0f%% of 72 (chance 50%%)" % (100 * np.mean(np.array(["bird", "fish"])[(E @ T.T).argmax(1)] == grp)))
c = E[grp == "bird"].mean(0), E[grp == "fish"].mean(0)
print("a nearest-centroid bird/fish rule on the image vectors: %.0f%%; image sizes birds %s fish %s (first of each)" % (100 * np.mean(np.array(["bird", "fish"])[np.argmax(np.stack([E @ c[0], E @ c[1]], 1), 1)] == grp), size[ids[0]] if grp[0] == "bird" else "-", sorted({size[i] for i in ids if byid[i]["group"] == "fish"})[:1]))
# fusion with the audio vectors
d = np.load(os.path.join(HERE, "out/embeddings.npz")); assert list(d["ids"]) == ids; Sa = d["emb"] @ d["emb"].T
for name, S in (("audio only (CLAP)", Sa), ("image only (CLIP)", Si), ("audio + image, equal weight", (Sa + Si) / 2), ("audio + image, image weighted 0.25", 0.75 * Sa + 0.25 * Si)):
    print("%-38s same species among nearest: birds top1 %.0f%% top5 %.0f%%; fish top1 %.0f%%" % (name, 100 * nn_rate(S, grp == "bird"), 100 * nn_rate(S, grp == "bird", 5), 100 * nn_rate(S, grp == "fish")))
# do images of the same recordist look alike (a confound: the same person's setup and settings)?
rec = np.array([byid[i]["recordist"] for i in ids]); S = Si.copy(); np.fill_diagonal(S, -9)
b = np.where(grp == "bird")[0]; print("nearest image has the same recordist (birds): %.0f%%" % (100 * np.mean([rec[np.argmax(S[i])] == rec[i] for i in b])))
