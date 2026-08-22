#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
env_file="${HAZBIT_ENV_FILE:-$project_dir/deploy/.env.production}"
backup_root="${HAZBIT_BACKUP_DIR:-$project_dir/backups}"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$backup_root/$timestamp"

if [ ! -f "$env_file" ]; then
    echo "Production environment file not found: $env_file" >&2
    exit 1
fi

mkdir -p "$target/objects"
chmod 0700 "$backup_root" "$target"

compose() {
    docker compose --env-file "$env_file" -f "$project_dir/compose.prod.yml" "$@"
}

echo "Writing PostgreSQL backup to $target/database.sql.gz"
compose exec -T postgres sh -ec \
    'pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip -9 > "$target/database.sql.gz"

echo "Mirroring payment evidence to $target/objects"
docker run --rm \
    --network hazbit-vpn_backend \
    --env-file "$env_file" \
    --volume "$target/objects:/backup" \
    --entrypoint /bin/sh \
    minio/mc:latest \
    -ec 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite "local/$HAZBIT_PAYMENT_BUCKET" /backup'

(
    cd "$target"
    sha256sum database.sql.gz
    find objects -type f -exec sha256sum {} \;
) > "$target/SHA256SUMS"
chmod -R go-rwx "$target"

echo "Backup complete: $target"
