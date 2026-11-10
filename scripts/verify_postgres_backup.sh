#!/usr/bin/env bash
# Restore into an isolated disposable database; NEVER modify application DB.
set -Eeuo pipefail
if (( $# < 1 || $# > 3 )); then
  echo "Usage: $0 <archive.dump> [table=django_migrations] [min_rows=1]" >&2
  exit 2
fi
ARCHIVE="$1"
TABLE="${2:-django_migrations}"
MIN_ROWS="${3:-1}"
if [[ ! -f "$ARCHIVE" || ! -r "$ARCHIVE" || "$(head -c 5 "$ARCHIVE")" != "PGDMP" ]]; then
  echo "Not a readable PostgreSQL custom-format archive." >&2
  exit 2
fi
if [[ ! "$TABLE" =~ ^[a-z][a-z0-9_]*$ ]] || [[ ! "$MIN_ROWS" =~ ^[0-9]+$ ]]; then
  echo "Invalid table identifier or row count." >&2
  exit 2
fi

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
ARCHIVE="$(cd -- "$(dirname -- "$ARCHIVE")" && pwd -P)/$(basename -- "$ARCHIVE")"
cd "$ROOT"
TEST_DB="fs_restore_$(date -u +'%s')_${RANDOM}_${RANDOM}"
CREATED=0
cleanup() {
  if (( CREATED )); then
    if ! docker compose exec -T db sh -c \
        'exec dropdb --if-exists -U "$POSTGRES_USER" "$1"' sh "$TEST_DB" >/dev/null; then
      echo "WARNING: disposable database $TEST_DB needs manual removal." >&2
    fi
  fi
}
trap cleanup EXIT

docker compose exec -T db pg_restore --list < "$ARCHIVE" > /dev/null
docker compose exec -T db sh -c \
  'exec createdb -U "$POSTGRES_USER" --template=template0 "$1"' sh "$TEST_DB"
CREATED=1
docker compose exec -T db sh -c \
  'exec pg_restore -U "$POSTGRES_USER" --dbname="$1" --no-owner --no-acl --single-transaction --exit-on-error' \
  sh "$TEST_DB" < "$ARCHIVE"

public_count="$(docker compose exec -T db sh -c \
  'exec psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"' \
  sh "$TEST_DB" "SELECT COUNT(*) FROM pg_catalog.pg_tables WHERE schemaname='public';")"
rows="$(docker compose exec -T db sh -c \
  'exec psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"' \
  sh "$TEST_DB" "SELECT COUNT(*) FROM public.$TABLE;")"

if [[ ! "$public_count" =~ ^[0-9]+$ || ! "$rows" =~ ^[0-9]+$ ]] \
   || (( public_count < 1 || rows < MIN_ROWS )); then
  echo "Restore check failed: missing public tables or required rows." >&2
  exit 1
fi
echo "Restore verified in disposable DB: $public_count public tables, $rows rows in $TABLE."
