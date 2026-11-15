#!/usr/bin/env python3
"""pgvector search over the CLAP audio embeddings, next to the curated metadata (use cases 4 and 5).
Starts a pgvector Postgres, loads the sounds pack seed plus sounds.recording_embeddings (from out/embeddings.npz, made by embed_audio.py),
then checks vector queries against a brute-force numpy answer and measures how good the results are:
  1. audio -> audio: for each recording, are its nearest neighbours the same species?
  2. text -> audio: "the song of a <bird>" retrieves that bird's recordings?
  3. hybrid: a vector search restricted by SQL (licence, country, group) joined to specimen counts, equal to the brute-force answer?
Needs: docker, torch + transformers (for the text embeddings), numpy. Run: python vector_search.py"""
import csv, os, subprocess, sys, numpy as np, torch
from transformers import ClapModel, ClapProcessor
HERE = os.path.dirname(os.path.abspath(__file__)); NAME = "snd-vec"; MODEL = os.environ.get("CLAP_MODEL", "laion/clap-htsat-unfused")
def psql(sql, tuples=True):
    r = subprocess.run(["docker", "exec", "-i", NAME, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-X"] + (["-At", "-F", "|"] if tuples else []), input=sql, capture_output=True, text=True)
    if r.returncode: sys.exit(r.stderr)
    return [l.split("|") for l in r.stdout.strip().splitlines()] if tuples else r.stdout
vec = lambda v: "'[" + ",".join("%.6f" % x for x in v) + "]'::vector"
def main():
    d = np.load(os.path.join(HERE, "out/embeddings.npz")); ids = list(d["ids"]); A = d["emb"]
    rec = {r["recording_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "manifest/recordings.csv")))}
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", NAME, "-e", "POSTGRES_PASSWORD=x", "pgvector/pgvector:pg16"], check=True, capture_output=True)
    while subprocess.run(["docker", "exec", NAME, "pg_isready", "-q"], capture_output=True).returncode: pass
    import time; time.sleep(3)
    psql("CREATE EXTENSION vector;"); psql(open(os.path.join(HERE, "../sounds-pack/seed-sounds.sql")).read())
    psql("CREATE TABLE sounds.recording_embeddings (recording_id text NOT NULL REFERENCES sounds.recordings(recording_id), model text NOT NULL, embedding vector(512) NOT NULL, PRIMARY KEY (recording_id, model));"
         + "".join("INSERT INTO sounds.recording_embeddings VALUES ('%s','clap-htsat-unfused',%s);" % (i, vec(A[k])) for k, i in enumerate(ids)))
    byid = {i: k for k, i in enumerate(ids)}
    # 1. audio -> audio
    S = A @ A.T; np.fill_diagonal(S, -9)
    for g in ("bird", "fish"):
        hit = tot = 0; agree = 0; qs = [i for i in ids if rec[i]["group"] == g]
        for i in qs:
            rows = psql("SELECT e.recording_id FROM sounds.recording_embeddings e WHERE e.recording_id <> '%s' ORDER BY e.embedding <=> (SELECT embedding FROM sounds.recording_embeddings WHERE recording_id='%s') LIMIT 5" % (i, i))
            got = [r[0] for r in rows]; want = [ids[j] for j in np.argsort(-S[byid[i]])[:5]]
            agree += got == want; hit += sum(rec[x]["species"] == rec[i]["species"] for x in got); tot += 5
        print("audio->audio %s: same species among the 5 nearest %.0f%% (%d queries); pgvector top-5 identical to numpy for %d of %d" % (g, 100 * hit / tot, len(qs), agree, len(qs)))
    # 2. text -> audio
    proc = ClapProcessor.from_pretrained(MODEL); model = ClapModel.from_pretrained(MODEL).eval()
    def text(p):
        with torch.no_grad(): t = model.get_text_features(**proc(text=[p], return_tensors="pt", padding=True))
        t = t if isinstance(t, torch.Tensor) else t.pooler_output
        return torch.nn.functional.normalize(t, dim=-1).numpy()[0]
    birds = sorted({(r["species"], r["common_name"]) for r in rec.values() if r["group"] == "bird"}); p5 = []; p1 = 0
    for sp, cn in birds:
        rows = psql("SELECT r.species FROM sounds.recording_embeddings e JOIN sounds.recordings r USING (recording_id) ORDER BY e.embedding <=> %s LIMIT 5" % vec(text("the song of a %s" % cn)))
        p5.append(sum(x[0] == sp for x in rows) / 5); p1 += rows[0][0] == sp
        print("  text 'the song of a %s': %d of 5 nearest are %s" % (cn, sum(x[0] == sp for x in rows), sp))
    print("text->audio: precision@5 %.0f%% (chance %.0f%%), top hit right for %d of %d species" % (100 * np.mean(p5), 100 * 6 / 72, p1, len(birds)))
    # 3. hybrid: vector ranking + SQL filter + join, against brute force
    q = text("a loud alarm call")
    sql = ("SELECT r.recording_id, r.species, r.license, s.usnm_specimens FROM sounds.recording_embeddings e JOIN sounds.recordings r USING (recording_id) "
           "JOIN sounds.licenses l ON l.license = r.license JOIN sounds.species s ON s.species = r.species "
           "WHERE r.group_name = 'bird' AND r.country = 'United States of America' AND l.allows_derivatives ORDER BY e.embedding <=> %s LIMIT 5" % vec(q))
    got = psql(sql); ok = [i for i in ids if rec[i]["group"] == "bird" and rec[i]["country"] == "United States of America" and "-ND" not in rec[i]["license"]]
    want = sorted(ok, key=lambda i: -float(A[byid[i]] @ q))[:5]
    print("hybrid (birds, USA, derivatives allowed, nearest 'a loud alarm call'): pgvector == numpy: %s; rows:" % ([g[0] for g in got] == want))
    for g in got: print("  ", g)
    print("alarm-call share of the 5 nearest to 'a loud alarm call' (all birds): %s" % psql("SELECT count(*) FILTER (WHERE r.call_type='alarm call'), count(*) FROM (SELECT recording_id FROM sounds.recording_embeddings ORDER BY embedding <=> %s LIMIT 5) t JOIN sounds.recordings r USING (recording_id)" % vec(q))[0])
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
if __name__ == "__main__": main()
