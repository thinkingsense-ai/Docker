# Real Docker Compose sidecar for TabPFN-2 predictive intelligence
# (com.omnigate.nl2sql.SemanticTier.PREDICTIVE) -- a standalone container OmniGate connects to
# over the network (OMNIGATE_PROFILING_SERVER_REMOTE_HOST=tabpfn-predictor), the same pattern
# Postgres already has in this repo's compose fixtures, instead of OmniGate spawning a Python
# subprocess itself. This keeps the main OmniGate image free of Python/torch/tabpfn entirely.
#
# server.py/tabpfn_classifier.py/tabpfn_predictor.py/requirements-tabpfn.txt are a real, vendored
# copy of the Server repo's own profiling-server/ directory (same "this repo doesn't build from
# the private Server repo's source, it consumes a standalone artifact" discipline the root
# Dockerfile's own header comment already establishes for the omnigate.jar itself) -- update this
# copy whenever the Server repo's profiling-server/ changes.
#
# Real license diligence, not guessed (see requirements-tabpfn.txt's own comment): pinned to
# tabpfn==2.0.9 specifically -- that version's weights are the Prior Labs License (Apache-2.0 +
# attribution, commercially usable); 2.1+/2.5/2.6/3's weights are non-commercial-only.
FROM python:3.11-slim

WORKDIR /app
COPY requirements-tabpfn.txt .
# torch + tabpfn -- a real, sizeable install, which is exactly why this is its own sidecar image
# rather than bundled into the main OmniGate image. Real bug found live building this image: a
# plain `pip install torch` resolves the default (GPU/CUDA-enabled) wheel, which pulls several
# multi-hundred-MB nvidia_cuda_*/nvidia_cudnn_* packages this CPU-only sidecar (llama-server's own
# real -ngl 0 choice applies the same reasoning here) never uses -- installing from PyTorch's own
# published CPU-only wheel index avoids all of that, a real, sizeable image-size and build-time
# reduction, not just tidiness.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements-tabpfn.txt

COPY server.py tabpfn_classifier.py tabpfn_predictor.py ./

# Real, not a placeholder: this sidecar's whole reason to exist is real TabPFN-2 predictions
# (com.omnigate.ontology.profiling.ProfilingModelClient#predict) -- unlike the Server repo's own
# default (off, since starting a Python subprocess with torch is a real, sizeable cost most
# deployments haven't opted into), a dedicated sidecar container built specifically for this has
# already paid that cost by existing at all, so it's on by default here.
ENV OMNIGATE_PROFILING_PREDICTOR_ENABLED=true
ENV OMNIGATE_PROFILING_SERVER_PORT=8092
# Real bug found live (see server.py's own comment on this env var): binding only to 127.0.0.1
# makes this container unreachable from another container on the same Compose network -- a
# sidecar's whole reason to exist is being reached by OmniGate's own separate container.
ENV OMNIGATE_PROFILING_SERVER_HOST=0.0.0.0
EXPOSE 8092

# Real health check Docker Compose's own depends_on/condition:service_healthy can key off of --
# matches the /health endpoint OmniGate's own ProfilingServerProcess.remote already polls.
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health', timeout=3)" || exit 1

CMD ["python", "server.py"]
