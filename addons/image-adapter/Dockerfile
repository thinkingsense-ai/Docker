FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY images.py adapter.py server.py ./
USER 10001
EXPOSE 8093
CMD ["python", "server.py", "8093"]
