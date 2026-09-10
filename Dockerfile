# Free edition: a completely self-contained recipe -- this Dockerfile does NOT build from source
# and does NOT need the private Server repo at all. It downloads the pre-compiled, already-shaded
# omnigate.jar and the pre-built web UI (web-dist.tar.gz) from this repo's own public GitHub
# Release, same distribution model any public "here's how to run our closed-source product"
# Docker repo uses: customers get a runnable JVM artifact, never the source that produced it.
#
# Pin OMNIGATE_RELEASE_TAG to a specific published release; override at build time with
# `docker build --build-arg OMNIGATE_RELEASE_TAG=vX.Y.Z .` to pick up a newer one without editing
# this file.
ARG OMNIGATE_RELEASE_TAG=v0.2.0

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

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=fetch /fetch/omnigate.jar omnigate.jar
COPY --from=fetch /fetch/web/dist ./web/dist
ENV OMNIGATE_WEB_DIST_DIR=/app/web/dist

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
