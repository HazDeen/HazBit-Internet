#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
env_file="${HAZBIT_ENV_FILE:-$project_dir/deploy/.env.production}"
source_dir="${1:-}"

if [ -z "$source_dir" ] || [ ! -f "$source_dir/database.sql.gz" ]; then
    echo "Usage: CONFIRM_RESTORE=hazbit-vpn deploy/scripts/restore.sh /absolute/backup/directory" >&2
    exit 1
fi
if [ "${CONFIRM_RESTORE:-}" != "hazbit-vpn" ]; then
    echo "Restore replaces current database and payment objects; set CONFIRM_RESTORE=hazbit-vpn" >&2
    exit 1
fi
if [ ! -f "$env_file" ]; then
    echo "Production environment file not found: $env_file" >&2
    exit 1
fi

compose() {
    docker compose --env-file "$env_file" -f "$project_dir/compose.prod.yml" "$@"
}

if [ -f "$source_dir/SHA256SUMS" ]; then
    (cd "$source_dir" && sha256sum -c SHA256SUMS)
fi

compose stop caddy platform

cleanup() {
    compose up -d platform caddy
}
trap cleanup EXIT INT TERM

gzip -dc "$source_dir/database.sql.gz" | compose exec -T postgres sh -ec \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'

if [ -d "$source_dir/objects" ]; then
    docker run --rm \
        --network hazbit-vpn_backend \
        --env-file "$env_file" \
        --volume "$source_dir/objects:/restore:ro" \
        --entrypoint /bin/sh \
        minio/mc:latest \
        -ec 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite --remove /restore "local/$HAZBIT_PAYMENT_BUCKET"'
fi

cleanup
trap - EXIT INT TERM
echo "Restore complete: $source_dir"
