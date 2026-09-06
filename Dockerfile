# syntax=docker/dockerfile:1
#
# NIDAAN - lightweight production image (SIH submission build)
#
#   Build:  docker build -t nidaan:latest .
#   Run:    docker run --rm -p 8000:8000 nidaan:latest
#
FROM python:3.10-slim

# System deps required by the audio pipeline:
#   libsndfile1  -> soundfile audio-file decoding
#   ffmpeg       -> audio format demux/transcode for file uploads
# Kept to the absolute minimum to hold the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Never run as root inside the container.
RUN useradd --create-home --uid 10001 nidaan
WORKDIR /app

# Install Python deps first (better layer caching than copying the tree first).
COPY requirements.txt ./
# librosa/soundfile are optional accelerators (NumPy fallback covers the demo);
# they are installed here per requirements.txt so the full feature set is available.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application code + static frontend + scenario/config assets.
COPY --chown=nidaan:nidaan . .

EXPOSE 8000

USER nidaan

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/scenarios', timeout=4)"]

# Single worker keeps the in-process SVI session state coherent per stream.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]