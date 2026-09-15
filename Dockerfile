# Free edition: a completely self-contained recipe -- this Dockerfile does NOT build from source
# and does NOT need the private Server repo at all. It downloads the pre-compiled, already-shaded
# omnigate.jar and the pre-built web UI (web-dist.tar.gz) from this repo's own public GitHub
# Release, same distribution model any public "here's how to run our closed-source product"
# Docker repo uses: customers get a runnable JVM artifact, never the source that produced it.
#
# Pin OMNIGATE_RELEASE_TAG to a specific published release; override at build time with
# `docker build --build-arg OMNIGATE_RELEASE_TAG=vX.Y.Z .` to pick up a newer one without editing
# this file.
ARG OMNIGATE_RELEASE_TAG=v0.6.0

FROM eclipse-temurin:17-jre-noble AS fetch
ARG OMNIGATE_RELEASE_TAG
WORKDIR /fetch
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o omnigate.jar \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/omnigate.jar" \
    && curl -fsSL -o web-dist.tar.gz \
      "https://github.com/thinkingsense-ai/Docker/releases/download/${OMNIGATE_RELEASE_TAG}/web-dist.tar.gz" \
    && mkdir -p web/dist && tar -xzf web-dist.tar.gz -C web/dist && rm web-dist.tar.gz

FROM eclipse-temurin:17-jre-noble
WORKDIR /app
COPY --from=fetch /fetch/omnigate.jar omnigate.jar
COPY --from=fetch /fetch/web/dist ./web/dist
ENV OMNIGATE_WEB_DIST_DIR=/app/web/dist

# Real architecture decision, changed from this image's own earlier version: the local reasoning
# model(s) (Qwen2.5-3B-Instruct for the agentic tier, SmolLM3-3B for Semantic Router's fast tier)
# and the TabPFN predictive-intelligence sidecar are NO LONGER bundled into this image -- each is
# its own real Docker Compose sidecar container now (see sidecars/llama/Dockerfile and
# sidecars/tabpfn/Dockerfile), the same pattern this repo's own Postgres service already
# establishes. Real, deliberate tradeoffs of this change, stated plainly:
#   - This image is now genuinely smaller (no ~2GB Qwen model, no SmolLM3 model, no llama-server
#     binary bundled here at all) -- faster to pull, faster to rebuild on an unrelated code change.
#   - "Runs privately, out of the box, zero configuration" (this image's own earlier framing) is
#     now "runs privately, out of the box, with the sidecar compose file" instead -- a real,
#     honest change in what "out of the box" means, not a silent regression: see the compose
#     fixtures under fixtures/*/docker-compose.yml, which wire OMNIGATE_ASSISTANT_REMOTE_HOST/
#     OMNIGATE_FAST_ASSISTANT_REMOTE_HOST/OMNIGATE_PROFILING_SERVER_REMOTE_HOST at the already-
#     established Qwen/SmolLM3/TabPFN sidecar Compose service names.
#   - OMNIGATE_ASSISTANT_LLAMA_SERVER_PATH/OMNIGATE_ASSISTANT_MODEL_PATH (spawn a local subprocess
#     inside THIS container) still work unchanged, for anyone who'd rather bind-mount a model file
#     in instead of running a sidecar -- this is additive, not a breaking removal of that mode (see
#     the Server repo's own GatewayComponents#remoteLlamaOrNull, which checks the new
#     _REMOTE_HOST env var first and falls through to that exact same existing local-spawn code
#     path when it's unset).
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
