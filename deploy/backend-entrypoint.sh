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

python -m app.operations.cli bootstrap
python -m app.operations.cli preflight

# Webhooks are configured by deploy/scripts/launch.sh after this container is
# healthy. Calling Telegram before Uvicorn starts lets Telegram deliver an
# update to an API that is not listening yet, which produces a transient 502.

exec "$@"
