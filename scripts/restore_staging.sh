#!/bin/sh
# Restore ONLY into a NEW disposable database container. Never touches live PG data.
set -eu
[ "$#" -eq 1 ] || { echo 'Usage: restore_staging.sh encrypted-backup.dump.gpg'; exit 2; }
cd "$(dirname "$0")/../infra/staging"
case "$1" in /*) archive=$1 ;; *) echo 'Use an absolute backup path'; exit 2 ;; esac
[ -f "$archive" ] || exit 2
target="agn-restore-check-$(date +%s)"
cleanup() { docker rm -f "$target" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
docker run -d --name "$target" --network none --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine >/dev/null
tries=0
until docker exec "$target" pg_isready -U postgres >/dev/null 2>&1; do
  tries=$((tries+1)); [ "$tries" -lt 60 ] || exit 1; sleep 1
done
# Decrypt to a private temporary file, checking GPG before restoring.
umask 077
tmp=$(mktemp)
trap 'rm -f "$tmp"; cleanup' EXIT INT TERM
docker compose -f compose.yml run --rm --no-deps --entrypoint gpg -v "$archive:/restore.gpg:ro" backup --batch --pinentry-mode loopback --passphrase-file /run/secrets/backup_passphrase --decrypt /restore.gpg > "$tmp"
docker exec -i "$target" pg_restore -U postgres -d postgres --exit-on-error --no-owner --no-acl < "$tmp"
docker exec "$target" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'SELECT count(*) AS editions FROM editions;'
echo 'Restore into disposable PostgreSQL succeeded; disposable database removed on exit.'
