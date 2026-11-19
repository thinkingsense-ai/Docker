# Gemma 4 E4B (text + image) behind llama.cpp's own llama-server. Both files are pinned by revision and SHA-256 (they come from a third party's repository);
# the build FAILS if a hash differs. The model is not in the app image. Source of the pins: demos/benchmark/local-models/models.json.
FROM python:3.12-slim AS fetch
ARG REPO=ggml-org/gemma-4-E4B-it-GGUF
ARG REVISION=8903cb408c7df39cde2ed15fac397e6d7be92951
ARG MAIN=gemma-4-E4B-it-Q4_0.gguf
ARG MAIN_SHA256=a555b900214b477d8880e7832e0b8925e139b0159640036b09fe472b6f2097f2
ARG MMPROJ=mmproj-gemma-4-E4B-it-Q8_0.gguf
ARG MMPROJ_SHA256=9257f21a0f5358204b4a612cff83fad2e56412f4f607f0049331ce60c0cf9d34
COPY fetch.py /fetch.py
RUN python3 /fetch.py "$REPO" "$REVISION" "$MAIN" "$MAIN_SHA256" "$MMPROJ" "$MMPROJ_SHA256"

FROM ghcr.io/ggml-org/llama.cpp:server
COPY --from=fetch /models /models
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=20 CMD ["curl", "-fsS", "http://127.0.0.1:8090/health"]
ENTRYPOINT ["/app/llama-server"]
CMD ["-m", "/models/gemma-4-E4B-it-Q4_0.gguf", "--mmproj", "/models/mmproj-gemma-4-E4B-it-Q8_0.gguf", "--host", "0.0.0.0", "--port", "8090", "-c", "4096", "--parallel", "1", "--jinja", "--reasoning", "off"]
