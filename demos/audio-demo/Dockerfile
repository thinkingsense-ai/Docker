# Audio demo service: BirdNET + CLAP behind a small web page. Heavy (torch); the data is mounted, not baked in: see docker-compose.yml.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
COPY engine.py server.py index.html ./
ENV POC_DIR=/poc ASK_URL=http://localhost:8080 HF_HOME=/models/hf XDG_DATA_HOME=/models/xdg XDG_CACHE_HOME=/models/cache
EXPOSE 8090
CMD ["python", "server.py", "8090"]
