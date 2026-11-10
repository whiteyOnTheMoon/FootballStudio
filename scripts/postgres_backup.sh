#!/usr/bin/env bash
# Secure PostgreSQL backup through the Compose database service.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
cd "$ROOT"
if (( $# > 1 )); then
  echo "Usage: $0 [backup-directory]" >&2
  exit 2
fi
BACKUP_DIR="${1:-$ROOT/backups}"
mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR="$(cd -- "$BACKUP_DIR" && pwd -P)"
tmp="$(mktemp "$BACKUP_DIR/.footballstudio.XXXXXXXX.tmp")"
trap 'rm -f -- "$tmp"' EXIT

# Credentials and database names stay inside the DB container's environment.
docker compose exec -T db sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "$tmp"

if [[ ! -s "$tmp" ]] || [[ "$(head -c 5 "$tmp")" != "PGDMP" ]]; then
  echo "Backup failed: invalid or empty PostgreSQL custom-format archive." >&2
  exit 1
fi
docker compose exec -T db pg_restore --list < "$tmp" >/dev/null

STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
DEST="$BACKUP_DIR/footballstudio_$STAMP_$$.dump"
if [[ -e "$DEST" ]]; then
  echo "Backup target already exists; refusing to overwrite it." >&2
  exit 1
fi
mv -- "$tmp" "$DEST"
trap - EXIT
chmod 600 "$DEST"
echo "Created PostgreSQL archive ($(wc -c < "$DEST") bytes)." >&2
printf '%s\n' "$DEST"
