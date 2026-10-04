#!/bin/sh
# Restore Memoir from a backup: a database dump into a database container, and the backed-up
# blobs into a blob directory. Stop memoir-api and memoir-worker first (docs/RUNBOOK.md).
#
#   restore.sh DUMP BLOB_BACKUP [DB_CONTAINER] [BLOB_DIR]
#
# Refuses a database that already holds Memoir's tables unless MEMOIR_RESTORE_OVERWRITE=yes, so
# the drill on a scratch database can never land on the real one by mistake.
set -eu

if [ "$#" -lt 2 ]; then
	echo "usage: $0 DUMP BLOB_BACKUP [DB_CONTAINER] [BLOB_DIR]" >&2
	exit 2
fi
dump="$1"
backup="$2"
db="${3:-memoir-db}"
blobs="${4:-/docker/memoir/blobs}"

[ -s "$dump" ] || { echo "no dump at $dump" >&2; exit 1; }
[ -d "$backup" ] || { echo "no blob backup at $backup" >&2; exit 1; }

tables="$(docker exec "$db" psql -U memoir -d memoir -Atc \
	"SELECT count(*) FROM information_schema.tables WHERE table_name = 'memories'")"
if [ "$tables" != "0" ] && [ "${MEMOIR_RESTORE_OVERWRITE:-}" != "yes" ]; then
	echo "$db already holds a Memoir database. Set MEMOIR_RESTORE_OVERWRITE=yes to replace it." >&2
	exit 1
fi

docker exec -i "$db" pg_restore -U memoir -d memoir --clean --if-exists --no-owner <"$dump"
mkdir -p "$blobs"
rsync -a "$backup/" "$blobs/"
chown -R 1000:1000 "$blobs"
echo "restored $(basename "$dump") into $db and $blobs"
