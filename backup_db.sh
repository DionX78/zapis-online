#!/bin/bash
# Бэкап SQLite через .backup + gzip + ротация 30 дней.
# Запуск: cron (см. ниже) или вручную: ./backup_db.sh

set -euo pipefail

PROJECT_DIR="/var/www/max_booking_bot"
DB_FILE="$PROJECT_DIR/booking.db"
BACKUP_DIR="$PROJECT_DIR/backups"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

TS=$(date +%Y-%m-%d_%H-%M)
OUT="$BACKUP_DIR/booking_${TS}.db"

# Консистентный снимок WAL-БД
sqlite3 "$DB_FILE" ".backup '$OUT'"

# Сжать
gzip -f "$OUT"

# Удалить старые
find "$BACKUP_DIR" -name "booking_*.db.gz" -mtime "+$KEEP_DAYS" -delete

echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup OK: $OUT.gz"