# One Python package, three targets:
#   test    what CI runs the tests and the lint in (test-docker mounts the checkout at /src)
#   worker  the job worker (published as memoir-worker)
#   api     the API, the default target (published as memoir-api)

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# ffmpeg normalises recordings to MP3 (app/capture/audio.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1000 --create-home memoir
WORKDIR /src/api

# test: the package installed editable at /src/api, so the checkout mounted over /src is what
# runs. PostgreSQL's server binaries let the tests start a throwaway database of their own.
FROM base AS test
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e ".[test]"
COPY . .
# initdb refuses to run as root.
USER memoir

FROM base AS runtime
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN mkdir -p /data/blobs && chown memoir:memoir /data /data/blobs
USER memoir
VOLUME /data

FROM runtime AS worker
# Healthy while this container's worker has been seen in the last minute.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD memoir-cli worker-alive || exit 1
CMD ["memoir-cli", "worker"]

FROM runtime AS api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["memoir-cli", "serve"]
