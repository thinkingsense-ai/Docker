# A fully private option: the bundled local model

This image bundles a real local model (Qwen2.5-3B-Instruct, quantized, ~2GB) plus a real
`llama-server` binary ([llama.cpp](https://github.com/ggml-org/llama.cpp)), wired up
automatically. Set `OMNIGATE_LLM_MODE=local-only` and ThinkingSense answers questions with **zero
external configuration and zero data ever leaving the container** — no API key, no outbound calls
at all.

Three other modes exist if you want a mix of local and cloud: `local-first`, `cloud-first`,
`customer-model-only`.

## License — read before using this beyond evaluation

Qwen2.5-3B-Instruct is distributed under Alibaba's own "Qwen RESEARCH LICENSE AGREEMENT" —
**non-commercial use only**. This free/developer image is exactly that use case. For a
*commercial* deployment, either:

- bring your own commercially-licensed model (point `OMNIGATE_ASSISTANT_MODEL_PATH`/
  `OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH` at it — Microsoft's MIT-licensed Phi-3.5-mini-instruct
  and Apache-2.0-licensed Qwen2.5-1.5B/7B-Instruct are real, verified alternatives in a similar
  size class), or
- use `OMNIGATE_LLM_MODE=cloud-first` or `customer-model-only` instead.

The required attribution notice ships as `NOTICE-qwen.txt` in the image and this repo.

## Memory

Running two local models at once (one for question-answering, one for embeddings — see
`OMNIGATE_EMBEDDING_MODEL_PATH` to point the embeddings role at a smaller model) needs real
headroom. Confirmed live: a host with only ~7-8GB of memory available was not enough — the kernel
killed the question-answering process under load while the embeddings process was also running.
Give Docker at least 8GB, ideally more, or point `OMNIGATE_EMBEDDING_MODEL_PATH` at a genuinely
small dedicated embeddings model to reduce the combined footprint.
