# The thinking layer (phase 2 skeleton). Build context is the repository root so the pack catalogue is included:
#   docker build -f addons/thinking-layer/Dockerfile -t thinking-layer .
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home layer
WORKDIR /app
COPY addons/thinking-layer/*.py addons/thinking-layer/contract.json ./
COPY packs/catalogue.json /app/packs/catalogue.json
ENV PACKS_CATALOGUE=/app/packs/catalogue.json PORT=8097
USER 10001
EXPOSE 8097
CMD ["python", "app.py"]
