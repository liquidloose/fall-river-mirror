#!/usr/bin/env bash
set -euo pipefail

DEST="/home/ron/development/rivedge-wordpress/04-fr-mirror/app/db_backups"
REMOTE="do-fall-river-mirror:/home/ron/fall-river-mirror/app/data/fr-mirror.db"
STAMP="$(date +%Y%m%d)"
LOG="$DEST/backup.log"

mkdir -p "$DEST"
echo "$(date -Is) starting backup" >> "$LOG"
rsync -av "$REMOTE" "$DEST/fr-mirror-${STAMP}.db" >> "$LOG" 2>&1
echo "$(date -Is) done" >> "$LOG"