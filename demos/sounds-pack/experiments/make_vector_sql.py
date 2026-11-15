#!/usr/bin/env python3
"""Writes SQL that adds sounds.recording_embeddings (pgvector, CLAP audio vectors from ../../multimodal-poc/out/embeddings.npz) to the sounds pack.
  python make_vector_sql.py plain   > vectors-plain.sql     comments say only what the column is
  python make_vector_sql.py defined > vectors-defined.sql   comments also say how to use it: which model, what distance means, never select the vector, how to rank by similarity
The extension goes in the sounds schema on purpose: the app connects with currentSchema=sounds, and a pgvector operator (<=>) installed in public is not on that search path
("operator does not exist: public.vector <=> public.vector"), for the model's SQL and for the reference SQL alike.
Run the pack on the pgvector image: docker-compose override `postgres: image: pgvector/pgvector:pg16` (see vectors-override.yml)."""
import os, sys, numpy as np
mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
d = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../multimodal-poc/out/embeddings.npz")); ids, A = d["ids"], d["emb"]
out = ["CREATE EXTENSION IF NOT EXISTS vector SCHEMA sounds;",
       "CREATE TABLE sounds.recording_embeddings (recording_id text NOT NULL REFERENCES sounds.recordings(recording_id), model text NOT NULL, embedding sounds.vector(512) NOT NULL, PRIMARY KEY (recording_id, model));"]
for i, v in zip(ids, A): out.append("INSERT INTO sounds.recording_embeddings VALUES ('%s','clap-htsat-unfused','[%s]');" % (i, ",".join("%.6f" % x for x in v)))
if mode == "plain":
    t = "Audio embedding of each recording."; c = {"recording_id": "Recording id.", "model": "Model that made the embedding.", "embedding": "The embedding vector."}
else:
    t = ("One row per recording with its audio embedding (a vector of 512 numbers made by the CLAP model from the first 10 seconds of sound). Use it only to find recordings that SOUND ALIKE: "
         "order by embedding <=> (SELECT embedding FROM sounds.recording_embeddings WHERE recording_id = '<id>') and take the first rows after the recording itself. "
         "Similar sound does not mean the same species; the species of a recording is recordings.species.")
    c = {"recording_id": "Recording the vector belongs to; joins to recordings.recording_id.", "model": "Model that made the vector. Only compare vectors with the same model.",
         "embedding": "512-number vector. Never select it: it is not readable and returns 512 numbers per row. Compare with the cosine distance operator <=> (smaller means more alike) and order by it; to rank against a recording use a subquery on its own vector."}
out.append("COMMENT ON TABLE sounds.recording_embeddings IS '%s';" % t.replace("'", "''"))
out += ["COMMENT ON COLUMN sounds.recording_embeddings.%s IS '%s';" % (k, v.replace("'", "''")) for k, v in c.items()]
out.append("GRANT SELECT ON sounds.recording_embeddings TO omnigate_ro;")
print("\n".join(out))
