# Free edition: a completely self-contained recipe -- this Dockerfile does NOT build from source
# and does NOT need the private Server repo at all. It downloads the pre-compiled, already-shaded
# omnigate.jar and the pre-built web UI (web-dist.tar.gz) from this repo's own public GitHub
# Release, same distribution model any public "here's how to run our closed-source product"
# Docker repo uses: customers get a runnable JVM artifact, never the source that produced it.
#
# Pin OMNIGATE_RELEASE_TAG to a specific published release; override at build time with
# `docker build --build-arg OMNIGATE_RELEASE_TAG=vX.Y.Z .` to pick up a newer one without editing
# this file.
ARG OMNIGATE_RELEASE_TAG=v0.1.0

FROM eclipse-temurin:17-jre-jammy AS fetch
ARG OMNIGATE_RELEASE_TAG
WORKDIR /fetch
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o omnigate.jar \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/omnigate.jar" \
    && curl -fsSL -o web-dist.tar.gz \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/web-dist.tar.gz" \
    && mkdir -p web/dist && tar -xzf web-dist.tar.gz -C web/dist && rm web-dist.tar.gz

# Free, local NL2SQL model -- Qwen2.5-1.5B-Instruct (Apache-2.0), the same default the admin
# console's LLM Settings page suggests for "Local (llama-server)" mode. Downloaded here (not at
# container start) so `docker compose up` doesn't re-fetch ~1GB on every restart.
RUN curl -fsSL -o qwen2.5-1.5b-instruct-q4_k_m.gguf \
      "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

# Builds llama-server (llama.cpp) from source so the binary's architecture always matches this
# image's own platform (no guessing which prebuilt release asset fits arm64 vs amd64). Base image
# matches the final stage's Ubuntu version (jammy) so the built binary is ABI-compatible with it.
FROM ubuntu:22.04 AS llama-build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /llama.cpp
WORKDIR /llama.cpp
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_OPENMP=OFF \
    && cmake --build build --target llama-server --config Release -j"$(nproc)"

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=fetch /fetch/omnigate.jar omnigate.jar
COPY --from=fetch /fetch/web/dist ./web/dist
ENV OMNIGATE_WEB_DIST_DIR=/app/web/dist

# Local llama-server, used ONLY for ontology embeddings/vector-search (schema retrieval) --
# NL2SQL answer generation itself now always goes through the hosted provider configured in the
# admin console's LLM Settings, with no local fallback. Deliberately NOT setting
# OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH/MODEL_PATH/PORT: GatewayComponents only spins up the
# "assistant" generation process (and NL2SQL's local-model fallback) when those are set, and only
# derives an embedding process from them as a convenience default when OMNIGATE_EMBEDDING_* is
# absent. Setting OMNIGATE_EMBEDDING_* explicitly instead keeps vector search working without ever
# starting that generation/fallback process.
COPY --from=llama-build /llama.cpp/build/bin/ /opt/llama.cpp/
COPY --from=fetch /fetch/qwen2.5-1.5b-instruct-q4_k_m.gguf /opt/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
# llama-server links against its sibling libllama*.so/libggml*.so but has no rpath pointing at its
# own directory, so the dynamic linker needs to be told where to find them explicitly.
ENV LD_LIBRARY_PATH=/opt/llama.cpp
ENV OMNIGATE_EMBEDDING_LLAMA_SERVER_PATH=/opt/llama.cpp/llama-server
ENV OMNIGATE_EMBEDDING_MODEL_PATH=/opt/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
ENV OMNIGATE_EMBEDDING_PORT=8091

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
