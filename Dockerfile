FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUTOMETA_DATA_DIR=/data \
    AUTOMETA_HOST=0.0.0.0 \
    AUTOMETA_PORT=8016 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY autometa ./autometa

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && useradd --create-home --uid 10001 autometa \
    && mkdir -p /data /tmp/matplotlib \
    && chown -R autometa:autometa /data /tmp/matplotlib

USER autometa
VOLUME ["/data"]
EXPOSE 8016

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8016/api/v1/health', timeout=3)"

CMD ["python", "-m", "autometa", "serve"]
