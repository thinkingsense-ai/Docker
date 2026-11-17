# The thinking layer and the Agency UI. Build context is the repository root (it needs packs/ and agency/web/):
#   docker build -f addons/thinking-layer/Dockerfile -t thinking-layer .
FROM node:20-alpine AS web
WORKDIR /web
COPY agency/web/package.json agency/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY agency/web/ ./
RUN npm run build

FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home layer
WORKDIR /app
COPY addons/thinking-layer/*.py addons/thinking-layer/contract.json ./
COPY packs/catalogue.json /app/packs/catalogue.json
COPY --from=web /web/dist /app/web
ENV PACKS_CATALOGUE=/app/packs/catalogue.json AGENCY_WEB_DIST=/app/web PORT=8097
USER 10001
EXPOSE 8097
CMD ["python", "app.py"]
