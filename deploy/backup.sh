#!/bin/sh
# Nightly backup of Memoir: the database, then the blobs. Run on the host from cron as root
# (docs/RUNBOOK.md). Blobs are written before the rows that name them, so copying the blobs after
# the dump catches every file the dump refers to.
#
#   MEMOIR_BACKUP_TARGET      where backups go (default /media/backups/memoir, the ZFS pool)
#   MEMOIR_DB_CONTAINER       the database container (default memoir-db)
#   MEMOIR_BLOBS              the blob directory (default /docker/memoir/blobs)
#   MEMOIR_BACKUP_KEEP_DAYS   how long database dumps are kept (default 30)
set -eu

target="${MEMOIR_BACKUP_TARGET:-/media/backups/memoir}"
db="${MEMOIR_DB_CONTAINER:-memoir-db}"
blobs="${MEMOIR_BLOBS:-/docker/memoir/blobs}"
keep="${MEMOIR_BACKUP_KEEP_DAYS:-30}"
stamp="$(date +%F)"

mkdir -p "$target/db" "$target/blobs"
dump="$target/db/memoir-$stamp.dump"
# Written under a temporary name, so a dump that failed halfway is never taken for a good one.
docker exec "$db" pg_dump -U memoir -d memoir --format=custom >"$dump.partial"
mv "$dump.partial" "$dump"

# A blob never changes once written: copy what is new and never delete, so a file removed by
# a purge stays recoverable from the backup. Unfinished uploads are not worth keeping.
rsync -a --exclude 'uploads/' "$blobs/" "$target/blobs/"

find "$target/db" -name 'memoir-*.dump' -mtime +"$keep" -delete
echo "memoir backup $stamp: database $(du -h "$dump" | cut -f1), blobs $(du -sh "$target/blobs" | cut -f1)"
