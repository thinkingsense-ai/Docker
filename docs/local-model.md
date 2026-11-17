# A fully private option: the bundled local model

The quick-start compose file runs a real local model (Qwen3-4B-Instruct-2507, quantised, about 2.5 GB) in its own sidecar container (`qwen-model`),
next to a real `llama-server` ([llama.cpp](https://github.com/ggml-org/llama.cpp)); the sidecar image downloads the model when you build it. The app image itself
holds no model. Set `OMNIGATE_LLM_MODE=local-only` and ThinkingSense answers questions with **no API key and no data leaving your machine**.

Three other modes exist if you want a mix of local and cloud: `local-first`, `cloud-first`,
`customer-model-only`.

## Licence

Qwen3-4B-Instruct-2507 is released by Alibaba's Qwen team under the **Apache License 2.0**, and so is the quantised GGUF file we download (Unsloth's conversion), so there is no
non-commercial restriction on the model. The fast-tier model, SmolLM3-3B, is Apache-2.0 too. Both are listed, with their sources, in `NOTICE-qwen.txt`.

The quick-start used to run Qwen2.5-3B-Instruct, which is under Alibaba's own "Qwen RESEARCH LICENSE AGREEMENT" (non-commercial use only); it was replaced for that reason.
If you still have that model's sidecar image or a LoRA adapter trained on it, note that an adapter only works with the base model it was trained on, so it has to be trained again on the new one.

The sidecar build checks the downloaded file against a pinned SHA-256 (`MODEL_SHA256` in `docker-compose.yml`), because the file comes from a third party's repository.
To use another model, change `MODEL_URL` (and `MODEL_SHA256`, or leave it empty to skip the check), or point `OMNIGATE_ASSISTANT_MODEL_PATH` and `OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH` at your own files.
You can also use `OMNIGATE_LLM_MODE=cloud-first` or `customer-model-only` and run no local model at all.

## Memory

Running two local models at once (one for question-answering, one for embeddings — see
`OMNIGATE_EMBEDDING_MODEL_PATH` to point the embeddings role at a smaller model) needs real
headroom. Confirmed live: a host with only ~7-8GB of memory available was not enough — the kernel
killed the question-answering process under load while the embeddings process was also running.
Give Docker at least 8GB, ideally more, or point `OMNIGATE_EMBEDDING_MODEL_PATH` at a genuinely
small dedicated embeddings model to reduce the combined footprint.
