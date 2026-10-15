#!/bin/sh
# Real, optional LoRA adapter serving -- closes the "adapter serving" gap flagged in the Server
# repo's own training/README.md (com.omnigate.training's agentic distillation pipeline produces a
# real trained LoRA adapter; nothing wired it into llama-server until this file). Two independent
# ways to supply one, checked in this order (first one found wins):
#
#   1. A runtime-mounted GGUF file at /opt/adapters/lora.gguf (see docker-compose.yml's own
#      `volumes:` comment for how to mount one without rebuilding this image at all -- the real,
#      recommended path for trying a freshly-trained adapter).
#   2. A build-time-baked adapter at /opt/lora.gguf (only present if LORA_GGUF_URL was set as a
#      build arg -- see this Dockerfile's own comment).
#
# Neither present means --lora is simply omitted -- base-model-only inference, unchanged from
# before this file existed. See training/convert_lora_to_gguf.sh (Server repo) for how to turn a
# trained PEFT/Unsloth adapter directory into the GGUF file either path here expects.
set -e

LORA_ARGS=""
# `-s` (non-empty), not `-f` (merely exists) -- the build-time /opt/lora.gguf is always PRESENT
# (see Dockerfile's own comment: an empty 0-byte placeholder when no adapter was baked in), so
# existence alone would always be true; only a genuinely non-empty file means a real adapter.
if [ -s /opt/adapters/lora.gguf ]; then
    echo "llama sidecar: loading LoRA adapter from /opt/adapters/lora.gguf (runtime-mounted)"
    LORA_ARGS="--lora /opt/adapters/lora.gguf"
elif [ -s /opt/lora.gguf ]; then
    echo "llama sidecar: loading LoRA adapter from /opt/lora.gguf (baked in at build time)"
    LORA_ARGS="--lora /opt/lora.gguf"
else
    echo "llama sidecar: no LoRA adapter found -- serving the base model only"
fi

exec ./llama/llama-server -m /opt/model.gguf --port "${LLAMA_PORT}" --host 0.0.0.0 -c 4096 -ngl 0 ${LORA_ARGS}
