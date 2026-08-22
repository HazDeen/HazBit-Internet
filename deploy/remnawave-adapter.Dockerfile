# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin hazbit

WORKDIR /app
COPY services/remnawave-adapter/pyproject.toml ./
COPY services/remnawave-adapter/remnawave_adapter ./remnawave_adapter
RUN pip install --upgrade pip && pip install .

USER hazbit
EXPOSE 8010

HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health/live', timeout=3)"]

CMD ["uvicorn", "remnawave_adapter.main:app", "--host", "0.0.0.0", "--port", "8010", "--proxy-headers", "--forwarded-allow-ips", "*"]
