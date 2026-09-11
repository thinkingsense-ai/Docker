# Free edition: a completely self-contained recipe -- this Dockerfile does NOT build from source
# and does NOT need the private Server repo at all. It downloads the pre-compiled, already-shaded
# omnigate.jar and the pre-built web UI (web-dist.tar.gz) from this repo's own public GitHub
# Release, same distribution model any public "here's how to run our closed-source product"
# Docker repo uses: customers get a runnable JVM artifact, never the source that produced it.
#
# Pin OMNIGATE_RELEASE_TAG to a specific published release; override at build time with
# `docker build --build-arg OMNIGATE_RELEASE_TAG=vX.Y.Z .` to pick up a newer one without editing
# this file.
ARG OMNIGATE_RELEASE_TAG=v0.3.0

# Semantic Reasoning Engine: a real, bundled local model + llama-server binary, so
# OMNIGATE_LLM_MODE=local-only/local-first (see the Server repo's LlmMode) work out of the box
# with zero external configuration -- the "runs privately, out of the box" story for this free/dev
# image specifically. Real license diligence, not guessed: Microsoft's own MIT-licensed
# Phi-3.5-mini-instruct was the initial candidate and would have been the safer default for a
# commercially-licensed image, but this free/developer image is explicitly non-commercial-use --
# per that scope, Qwen2.5-3B-Instruct is used instead (Alibaba's own "Qwen RESEARCH LICENSE
# AGREEMENT" -- non-commercial only; the required attribution notice is shipped alongside it, see
# NOTICE-qwen.txt below). Confirmed live before pinning: the real llama.cpp b10809 release build
# needs a newer glibc/libstdc++ than Ubuntu 22.04 ("jammy") ships -- this is why the base image
# below is "noble" (24.04), not jammy; verified end-to-end with a real container (model loads,
# real /v1/chat/completions inference returns a correct answer) before committing to this image.
ARG LLAMA_CPP_TAG=b10809
ARG LOCAL_MODEL_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf

# Semantic Router's "fast tier" model (com.omnigate.nl2sql.SemanticRoutingNl2SqlProvider,
# SemanticTier.FAST) -- a second, smaller/faster model for short single-fact lookups ("how many
# X", "what is Y"), separate from the assistant model above which stays the default for everything
# else. Real license diligence, not guessed: confirmed live via the Hugging Face API before
# pinning -- HuggingFaceTB/SmolLM3-3B itself and unsloth/SmolLM3-3B-GGUF's own Q4_K_M quant are
# both real Apache-2.0, genuinely redistributable (no non-commercial restriction the way the
# assistant model above has). Bundled into the image but NOT enabled by default -- see
# OMNIGATE_FAST_ASSISTANT_MODEL_PATH being unset in this repo's own compose files: running a
# second full model instance simultaneously needs real memory headroom beyond the single-model
# assistant-only default (confirmed live this session: a ~7-8GB host already needed a workaround to
# run just the ONE assistant model alongside its own embedding instance -- see this repo's README).
# An operator with a bigger host sets OMNIGATE_FAST_ASSISTANT_MODEL_PATH=/opt/omnigate/fast-model.gguf
# to turn this on.
ARG FAST_MODEL_URL=https://huggingface.co/unsloth/SmolLM3-3B-GGUF/resolve/main/SmolLM3-3B-Q4_K_M.gguf

FROM eclipse-temurin:17-jre-noble AS fetch
ARG OMNIGATE_RELEASE_TAG
ARG LLAMA_CPP_TAG
ARG LOCAL_MODEL_URL
ARG FAST_MODEL_URL
ARG TARGETARCH
WORKDIR /fetch
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o omnigate.jar \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/omnigate.jar" \
    && curl -fsSL -o web-dist.tar.gz \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/web-dist.tar.gz" \
    && mkdir -p web/dist && tar -xzf web-dist.tar.gz -C web/dist && rm web-dist.tar.gz
# Real bug found live: TARGETARCH is only auto-populated by a buildx/multi-platform build --
# a plain `docker build` (confirmed live: this environment doesn't even have buildx installed)
# leaves it empty, which silently fell through to the x64 asset on a native arm64 build machine,
# producing an image whose llama-server binary only ran under qemu emulation (and then failed
# outright -- "Could not open '/lib64/ld-linux-x86-64.so.2'", no 32/64-bit compat layer in this
# base image at all). `uname -m` reflects the architecture this RUN step is actually executing on,
# which is what a plain single-platform `docker build` needs; TARGETARCH is still honored first
# for a genuine cross-compiled buildx build, where it's the authoritative signal instead.
RUN ARCH="${TARGETARCH:-$(uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')}" \
    && LLAMA_ARCH=$([ "$ARCH" = "arm64" ] && echo "ubuntu-arm64" || echo "ubuntu-x64") \
    && curl -fsSL -o llama.tar.gz \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_TAG}/llama-${LLAMA_CPP_TAG}-bin-${LLAMA_ARCH}.tar.gz" \
    && mkdir -p llama && tar -xzf llama.tar.gz -C llama --strip-components=1 && rm llama.tar.gz \
    && curl -fsSL -o model.gguf "${LOCAL_MODEL_URL}" \
    && curl -fsSL -o fast-model.gguf "${FAST_MODEL_URL}"

FROM eclipse-temurin:17-jre-noble
WORKDIR /app
COPY --from=fetch /fetch/omnigate.jar omnigate.jar
COPY --from=fetch /fetch/web/dist ./web/dist
ENV OMNIGATE_WEB_DIST_DIR=/app/web/dist

# libgomp1 (OpenMP runtime) -- confirmed live this is the one runtime library llama-server needs
# that isn't already bundled in its own release tarball; everything else it links against
# (libc/libstdc++/libm) comes from the base image itself.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=fetch /fetch/llama ./llama
COPY --from=fetch /fetch/model.gguf /opt/omnigate/model.gguf
COPY --from=fetch /fetch/fast-model.gguf /opt/omnigate/fast-model.gguf
COPY NOTICE-qwen.txt /opt/omnigate/NOTICE-qwen.txt
ENV OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH=/app/llama/llama-server
ENV OMNIGATE_ASSISTANT_MODEL_PATH=/opt/omnigate/model.gguf
# OMNIGATE_FAST_ASSISTANT_MODEL_PATH is deliberately NOT set here -- bundled (/opt/omnigate/fast-model.gguf,
# SmolLM3-3B) but off by default, see this file's own comment on FAST_MODEL_URL above for why. Set
# it (plus OMNIGATE_FAST_ASSISTANT_LLAMA_SERVER_PATH=/app/llama/llama-server, same binary serves
# both) on a host with enough memory headroom to turn on Semantic Router's fast tier.

# Edition.current() reads this before ever looking at OMNIGATE_EDITION -- see that class's javadoc.
# This is what makes the free edition's cap resistant to a plain `docker run -e
# OMNIGATE_EDITION=commercial` override -- the marker file wins over the env var by design.
RUN mkdir -p /opt/omnigate && printf 'free' > /opt/omnigate/EDITION

# Default ConfigStore location: a file-backed embedded HSQLDB instance under this path unless
# OMNIGATE_CONFIG_DB points at an external database (Postgres, for a larger deployment). Mount a
# volume here to persist config across container restarts; without one, config still works for the
# container's lifetime, just doesn't survive a `docker rm`.
ENV OMNIGATE_DATA_DIR=/var/lib/omnigate/data
RUN mkdir -p /var/lib/omnigate/data
VOLUME ["/var/lib/omnigate/data"]

# Oracle wire, Postgres wire, MySQL wire, native gRPC driver, TCPS (TLS), HTTP admin console/API,
# HTTPS admin console/API. The free edition isn't feature-limited, only capped on scale (100
# concurrent connections total, 2 named backends).
EXPOSE 1521 5433 3306 7070 2484 8080 8443

# Required only when OMNIGATE_CLUSTER_ENABLED=true -- Apache Ignite 2.x reflectively accesses
# internal JDK APIs (e.g. java.nio.Buffer.address) that JDK 17's module system blocks by default;
# a harmless no-op for every other deployment that never sets OMNIGATE_CLUSTER_ENABLED.
ENV JDK_JAVA_OPTIONS="--add-opens=jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/jdk.internal.access=ALL-UNNAMED --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/sun.util.calendar=ALL-UNNAMED --add-opens=java.management/com.sun.jmx.mbeanserver=ALL-UNNAMED --add-opens=jdk.internal.jvmstat/sun.jvmstat.monitor=ALL-UNNAMED --add-opens=java.base/sun.reflect.generics.reflectiveObjects=ALL-UNNAMED --add-opens=java.base/java.io=ALL-UNNAMED --add-opens=java.base/java.net=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.util.concurrent=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.locks=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED"

ENTRYPOINT ["java", "-jar", "omnigate.jar"]
