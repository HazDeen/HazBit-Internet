#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_file=${1:-"$project_root/deploy/.env.production"}
compose_file="$project_root/compose.prod.yml"

if [ ! -f "$env_file" ]; then
    echo "Production environment file not found: $env_file" >&2
    echo "Copy deploy/.env.production.example and fill every required value." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required." >&2
    exit 1
fi

if grep -Eq 'example\.com|change-this|replace-with|local-only|local-replace' "$env_file"; then
    echo "Production environment still contains placeholder values." >&2
    exit 1
fi

compose() {
    HAZBIT_ENV_FILE="$env_file" docker compose \
        --env-file "$env_file" \
        -f "$compose_file" \
        "$@"
}

echo "[1/7] Validating Docker Compose configuration"
compose config --quiet

echo "[2/7] Building production images"
compose build platform remnawave-adapter caddy

echo "[3/7] Validating production application settings"
compose run --rm --no-deps --entrypoint python platform \
    -c "from app.core.config import Settings; Settings(); print('Production settings are valid')"
compose run --rm --no-deps --entrypoint python remnawave-adapter \
    -c "from remnawave_adapter.config import Settings; Settings(); print('Adapter settings are valid')"

echo "[4/8] Starting the production stack"
compose up -d

echo "[5/8] Verifying launch readiness"
compose exec -T platform python -m app.operations.cli preflight

if [ "${HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS:-true}" = "true" ] && [ "${HAZBIT_FEATURES__TELEGRAM_BOTS:-true}" = "true" ]; then
    echo "[6/8] Configuring Telegram bot webhooks"
    compose exec -T platform python -m app.workers.setup_telegram_bots
else
    echo "[6/8] Skipping Telegram webhook configuration"
fi

echo "[7/8] Verifying Telegram bot identities and webhooks"
compose exec -T platform python -m app.workers.check_telegram_bots

echo "[8/8] Sending SMTP delivery test to the first super admin"
compose exec -T platform python -m app.operations.cli test-email
compose ps

echo "Hazbit launch completed. Verify /health/ready and confirm receipt of the test email."
