# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS python-build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --upgrade pip && pip install .

FROM node:22-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PM2_HOME=/tmp/pm2

RUN npm install --global pm2@6 && \
    useradd --create-home --uid 10001 --shell /usr/sbin/nologin hazbit

COPY --from=python-build /usr/local /usr/local
COPY --from=python-build /opt/venv /opt/venv

WORKDIR /app/backend
COPY --chown=hazbit:hazbit backend ./
COPY --chown=hazbit:hazbit database /app/database
COPY --chown=hazbit:hazbit deploy/ecosystem.config.cjs /app/deploy/ecosystem.config.cjs
COPY --chown=hazbit:hazbit deploy/backend-entrypoint.sh /app/deploy/backend-entrypoint.sh
RUN chmod 0555 /app/deploy/backend-entrypoint.sh

USER hazbit
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]

ENTRYPOINT ["/app/deploy/backend-entrypoint.sh"]
CMD ["pm2-runtime", "/app/deploy/ecosystem.config.cjs"]
