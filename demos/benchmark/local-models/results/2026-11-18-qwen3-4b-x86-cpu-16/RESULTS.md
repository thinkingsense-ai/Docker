# Baseline: Qwen3-4B-Instruct-2507 (Q4_K_M) on OCI VM.Standard.E6.Flex, 16 OCPU / 125 GB, CPU only

Treasury pack, 24 free-form questions, question bank off, app v0.10.21 in `local-only` mode, judged by Haiku 5.5 against same-day reference rows (`ref_treasury.json`).
Run on 2026-11-18 with `run_local.sh qwen3-4b-q4km x86-cpu-16 treasury 3` (`meta_*.json` has the command, file hashes and image id).

| | |
|---|---|
| Score per run | 8, 8, 8 of 24 (identical every run: 8 right every time, 0 sometimes, 16 never) |
| Time per question | median 28.6 s, 90th percentile 45.9 s, slowest 92.9 s |
| Run length | about 12.5 minutes |
| Tokens per question (median) | about 6,157 in, 469 out |
| Serving speed (short prompt, measured separately) | decode about 35.7 tokens/s, prefill about 256 tokens/s |
| Run errors | none (all 72 answers returned) |

For comparison, the earlier Haiku 5.5 run of the same pack with no table comments (app 0.10.17, README of `demos/benchmark/`) scored 12, 10, 13 (mean 11.7; 9 right every run).
Different app version and model, so the gap is indicative, not a controlled difference.

**What the 16 misses look like** (judge reasons, run 1): about half are wrong logic (a consolidated cash total of 21.9 billion against 136.7 million; per-account
balances instead of the latest balance; unmatched counts and amounts that differ), the rest are near misses on shape (right figures but a missing entity column, one row
instead of the two the reference gives, the threshold not applied).

**Not measured here:** the escalation threshold. The Server's answer stream does not carry the pre-execution confidence score, so `report.py calibrate` has nothing to read
(it says so). `context_report.py` also assumes Anthropic-style request logs, so its "tables offered" lines (0 of 24) are not meaningful for this run.
Temperature behaviour made the three runs identical, so three runs add no information for this model; run-to-run spread needs a higher-temperature variant.
