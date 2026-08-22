#!/bin/sh
set -eu

attempt=1
max_attempts="${HAZBIT_MIGRATION_MAX_ATTEMPTS:-30}"

until alembic upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Database migration failed after $attempt attempts" >&2
        exit 1
    fi
    echo "Database is not ready; migration retry $attempt/$max_attempts" >&2
    attempt=$((attempt + 1))
    sleep 2
done

if [ "${HAZBIT_CONFIGURE_TELEGRAM_WEBHOOKS:-true}" = "true" ]; then
    if ! python -m app.workers.setup_telegram_bots; then
        echo "Telegram webhook setup failed; API and workers will still start" >&2
    fi
fi

exec "$@"
