#!/bin/sh
# Veritabanı ve yüklenen dosyaların günlük yedeği. 14 günden eski yedekler silinir.
# Yedekler kişisel veri içerir: şifreli bir diske ya da şifreli uzak depoya (ör. restic) aktarın.
set -eu
DEST="${KANAT_BACKUP_DIR:-/var/backups/kanat}"
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$DEST"
umask 077

if command -v docker >/dev/null 2>&1 && docker compose ps db >/dev/null 2>&1; then
  docker compose exec -T db pg_dump -U "${POSTGRES_USER:-kanat}" "${POSTGRES_DB:-kanat}" | gzip > "$DEST/db-$STAMP.sql.gz"
  docker compose cp web:/app/media - | gzip > "$DEST/media-$STAMP.tar.gz"
  docker compose cp web:/app/private_media - | gzip > "$DEST/private-$STAMP.tar.gz"
else
  pg_dump "${POSTGRES_DB:-kanat}" | gzip > "$DEST/db-$STAMP.sql.gz"
  tar -czf "$DEST/files-$STAMP.tar.gz" -C "${KANAT_DIR:-/srv/kanat}" media private_media
fi

find "$DEST" -type f -mtime +14 -delete
echo "Yedek tamam: $DEST ($STAMP)"
