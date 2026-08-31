# Free edition: same jar, same code, as Dockerfile (commercial) — the only difference is the
# baked-in edition marker file below. ARCHITECTURE.md §9 / com.omnigate.core.Edition: this is what
# makes the cap resistant to a plain `docker run -e OMNIGATE_EDITION=commercial` override — the
# marker file wins over the env var by design, not by accident.
# Web UI — same web-build stage as Dockerfile (commercial); see SpaResourceHandler's javadoc.
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ .
RUN npm run build

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -q -B dependency:go-offline || true
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=build /build/target/omnigate.jar omnigate.jar
COPY --from=web-build /web/dist ./web/dist
ENV OMNIGATE_WEB_DIST_DIR=/app/web/dist

# Edition.current() reads this before ever looking at OMNIGATE_EDITION — see that class's javadoc.
RUN mkdir -p /opt/omnigate && printf 'free' > /opt/omnigate/EDITION

# ARCHITECTURE.md §57 -- default ConfigStore location: a file-backed embedded HSQLDB instance
# under this path unless OMNIGATE_CONFIG_DB points at an external database (Postgres, for a
# larger deployment). Mount a volume here to persist config across container restarts; without
# one, config still works for the container's lifetime, just doesn't survive a `docker rm`.
ENV OMNIGATE_DATA_DIR=/var/lib/omnigate/data
RUN mkdir -p /var/lib/omnigate/data
VOLUME ["/var/lib/omnigate/data"]

# Same protocol surface as the commercial image — the free edition isn't feature-limited, only
# capped on scale (100 concurrent connections total, 2 named backends). See ARCHITECTURE.md §9.
EXPOSE 1521 5433 3306 7070 2484 8080 8443

# Required only when OMNIGATE_CLUSTER_ENABLED=true (ARCHITECTURE.md §12) — see Dockerfile
# (commercial) for the full explanation; identical here since it's the same jar/code.
ENV JDK_JAVA_OPTIONS="--add-opens=jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/jdk.internal.access=ALL-UNNAMED --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/sun.util.calendar=ALL-UNNAMED --add-opens=java.management/com.sun.jmx.mbeanserver=ALL-UNNAMED --add-opens=jdk.internal.jvmstat/sun.jvmstat.monitor=ALL-UNNAMED --add-opens=java.base/sun.reflect.generics.reflectiveObjects=ALL-UNNAMED --add-opens=java.base/java.io=ALL-UNNAMED --add-opens=java.base/java.net=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.util.concurrent=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.locks=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED"

ENTRYPOINT ["java", "-jar", "omnigate.jar"]
