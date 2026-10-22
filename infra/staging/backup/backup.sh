#!/bin/sh
set -eu
umask 077
export PGPASSWORD="$(cat /run/secrets/db_password)"
backup() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  # Separate dump and encryption commands: any pg_dump failure is fatal.
  pg_dump -Fc --no-owner --no-acl -f /tmp/agn.dump
  pg_restore --list /tmp/agn.dump >/dev/null
  gpg --batch --yes --pinentry-mode loopback --passphrase-file /run/secrets/backup_passphrase --symmetric --cipher-algo AES256 --output "/backups/agn-$stamp.dump.gpg.tmp" /tmp/agn.dump
  mv "/backups/agn-$stamp.dump.gpg.tmp" "/backups/agn-$stamp.dump.gpg"
  rm /tmp/agn.dump
  echo "Encrypted backup completed: $stamp"
}
if [ "${1:-}" = '--once' ]; then backup; exit; fi
while :; do backup; sleep 86400; done
