# Real Docker Compose sidecar for a local reasoning model -- a standalone llama-server + model
# container OmniGate connects to over the network (OMNIGATE_ASSISTANT_REMOTE_HOST=<service name>
# or OMNIGATE_FAST_ASSISTANT_REMOTE_HOST=<service name>), the same pattern Postgres already has in
# this repo's compose fixtures, instead of OmniGate spawning the model subprocess itself. One
# image, parameterized by MODEL_URL, used for BOTH the agentic-tier model (Qwen2.5-3B-Instruct)
# and the fast-tier model (SmolLM3-3B) -- they're structurally identical containers (one
# llama-server binary + one model file), just different build-arg values in docker-compose.yml.
#
# Real license diligence per model, not guessed (see the root Dockerfile's own comments, which
# this file's fetch logic is copied from): Qwen2.5-3B-Instruct-GGUF is Alibaba's own "Qwen
# RESEARCH LICENSE AGREEMENT" (non-commercial only, required attribution -- see NOTICE-qwen.txt);
# SmolLM3-3B/unsloth's own GGUF quant are both real Apache-2.0, no non-commercial restriction.
ARG LLAMA_CPP_TAG=b10809
ARG MODEL_URL
# Optional -- a pre-converted GGUF LoRA adapter to bake into this image (see
# training/convert_lora_to_gguf.sh in the Server repo for producing one from a trained PEFT/
# Unsloth adapter directory). Leave unset for base-model-only inference, unchanged from before
# this arg existed. A runtime-mounted adapter (see entrypoint.sh's own comment) takes precedence
# over this build-time one either way, so baking one in is only useful for a from-scratch image
# build that should always serve that adapter with no extra runtime config.
ARG LORA_GGUF_URL

FROM eclipse-temurin:17-jre-noble AS fetch
ARG LLAMA_CPP_TAG
ARG MODEL_URL
ARG LORA_GGUF_URL
ARG TARGETARCH
WORKDIR /fetch
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Real bug found live building the main OmniGate image, same fix reused verbatim here: TARGETARCH
# is only auto-populated by a buildx/multi-platform build -- a plain `docker build` leaves it
# empty, silently falling through to the x64 asset on a native arm64 build machine. `uname -m`
# reflects the architecture this RUN step actually executes on, which is what a plain
# single-platform `docker build` needs; TARGETARCH is still honored first for a genuine
# cross-compiled buildx build.
RUN ARCH="${TARGETARCH:-$(uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')}" \
    && LLAMA_ARCH=$([ "$ARCH" = "arm64" ] && echo "ubuntu-arm64" || echo "ubuntu-x64") \
    && curl -fsSL -o llama.tar.gz \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_TAG}/llama-${LLAMA_CPP_TAG}-bin-${LLAMA_ARCH}.tar.gz" \
    && mkdir -p llama && tar -xzf llama.tar.gz -C llama --strip-components=1 && rm llama.tar.gz \
    && curl -fsSL -o model.gguf "${MODEL_URL}" \
    && if [ -n "${LORA_GGUF_URL}" ]; then curl -fsSL -o lora.gguf "${LORA_GGUF_URL}"; else touch lora.gguf; fi

FROM eclipse-temurin:17-jre-noble
WORKDIR /app
# libgomp1 (OpenMP runtime) -- confirmed live (same finding as the root Dockerfile) this is the
# one runtime library llama-server needs that isn't already bundled in its own release tarball.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=fetch /fetch/llama ./llama
COPY --from=fetch /fetch/model.gguf /opt/model.gguf
# Real, optional LoRA adapter -- see entrypoint.sh's own comment for the full precedence order
# (a runtime-mounted /opt/adapters/lora.gguf always wins over this build-time-baked one). The
# fetch stage above always creates lora.gguf (a real, empty 0-byte placeholder when
# LORA_GGUF_URL wasn't set -- a plain COPY of a literal path that doesn't exist FAILS the build in
# this builder, so an always-present placeholder is the reliable "optional file" approach here);
# entrypoint.sh checks the file is genuinely non-empty (`-s`, not just `-f`) before using it.
COPY --from=fetch /fetch/lora.gguf /opt/lora.gguf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
# Required attribution text for the Qwen RESEARCH LICENSE AGREEMENT, per the root Dockerfile's own
# NOTICE-qwen.txt -- harmless to include even when this image is built with MODEL_URL pointing at
# the (Apache-2.0, no attribution required) SmolLM3 model instead.
COPY NOTICE-qwen.txt /opt/NOTICE-qwen.txt

ENV LLAMA_PORT=8090
EXPOSE 8090

# Same /health endpoint com.omnigate.assistant.LocalLlamaProcess.remote already polls -- real
# health check Docker Compose's own depends_on/condition:service_healthy keys off of.
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=20 \
    CMD curl -fsS "http://127.0.0.1:${LLAMA_PORT}/health" || exit 1

# CPU-only inference (-ngl 0), same real, deliberate choice the root Dockerfile's own bundled
# model already makes -- no GPU dependency, works identically on any host. --host 0.0.0.0 (not
# 127.0.0.1) is the one real, necessary difference from a locally-spawned instance: a sidecar
# container must accept connections from OTHER containers on the Compose network, not just itself.
# See entrypoint.sh's own comment for the real, optional LoRA-adapter-loading logic this delegates to.
ENTRYPOINT ["/app/entrypoint.sh"]
