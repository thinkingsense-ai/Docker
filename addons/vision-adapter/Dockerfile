# Build context is addons/ (see docker-compose.vision.yml) so the image adapter's decoder is shared, not copied by hand.
FROM python:3.12-slim
WORKDIR /app
COPY vision-adapter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY image-adapter/images.py ./
COPY vision-adapter/adapter.py vision-adapter/server.py ./
USER 10001
EXPOSE 8095
CMD ["python", "server.py", "8095"]
