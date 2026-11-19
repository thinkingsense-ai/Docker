# Gemma 4 E4B, thinking off — Treasury, OCI VM.Standard.E6.Flex (16 OCPU, 128 GB), 2026-11-19

`llama-server` started with `--reasoning off` (Gemma 4 thinks by default under `--jinja`). One run, app v0.10.21, local-only mode, judged by Haiku against same-day reference rows.

| | Score | Median s | p90 s | Median output tokens |
|---|---|---|---|---|
| thinking off (this run) | 8 of 24 | 30.8 | 61.5 | 587 |
| thinking on (the default; files lost with their node) | 9 of 24 | 118 | 278 | about 2,700 |

Thinking added no accuracy (one question apart, within noise) and cost about four times the time. Qwen3-4B scored 8 of 24 on the same pack. `calls_*.jsonl` holds the logged model calls (scanned: no key-shaped strings).
