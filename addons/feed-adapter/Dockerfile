FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
COPY feeds.json feedreader.py rules.py store.py adapter.py ./
USER 10001
CMD ["python", "adapter.py"]
