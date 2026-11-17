FROM python:3.12-slim
WORKDIR /app
COPY tables.py adapter.py server.py ./
USER 10001
EXPOSE 8091
CMD ["python", "server.py", "8091"]
