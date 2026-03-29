# UltraSinger WebUI layered on the official UltraSinger image (CUDA + Python 3.12 + UltraSinger deps).
# Base: https://github.com/rakuri255/UltraSinger/pkgs/container/ultrasinger
FROM ghcr.io/rakuri255/ultrasinger:sha-4155efd

USER root

# Match UltraSinger image: uv was installed for root during base build
ENV PATH="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

WORKDIR /app/webui

COPY requirements.txt .
RUN set -eux; \
    export PATH="/root/.local/bin:$PATH"; \
    if command -v uv >/dev/null 2>&1; then \
      uv pip install --system --python 3.12 --no-cache -r requirements.txt; \
    else \
      python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel; \
      python3.12 -m pip install --no-cache-dir -r requirements.txt; \
    fi

COPY app ./app
COPY static ./static

RUN mkdir -p /data \
    && chown -R 1000:1000 /app/webui /data

ENV PYTHONUNBUFFERED=1 \
    ULTRASINGER_WEBUI_DATA_DIR=/data \
    ULTRASINGER_PY=/app/UltraSinger/UltraSinger.py \
    PYTHON_EXE=python3.12

USER 1000:1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python3.12 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"

CMD ["python3.12", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
