#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

CRON_SCHEDULE_JP2="${CRON_SCHEDULE_JP2:-0 2 * * *}"
CRON_SCHEDULE_KR2="${CRON_SCHEDULE_KR2:-0 4 * * *}"
JOB_CMD_JP2="${JOB_CMD_JP2:-python dataset_jp.py && python predict2_jp.py --model /models/model2_jp.pt --seq-len 60 --top-k 20 --save-db}"
JOB_CMD_KR2="${JOB_CMD_KR2:-python dataset_kr.py && python predict2_kr.py --model /models/model2_kr.pt --seq-len 60 --top-k 20 --save-db}"
LOG_DIR_DEFAULT="${CRON_LOG_DIR:-/data/log}"
LOG_PATH="${CRON_LOG_PATH:-${LOG_DIR_DEFAULT}/cron.log}"
LOG_DIR="$(dirname "$LOG_PATH")"
LOG_BASE="$(basename "$LOG_PATH")"
LOG_STEM="${LOG_BASE%.log}"

mkdir -p "${LOG_DIR}"

{
  echo "${CRON_SCHEDULE_JP2} root /bin/bash -lc 'cd /app && ${JOB_CMD_JP2} >> \"${LOG_DIR}/${LOG_STEM}-\$(date +\\%F).log\" 2>&1'"
  echo "${CRON_SCHEDULE_KR2} root /bin/bash -lc 'cd /app && ${JOB_CMD_KR2} >> \"${LOG_DIR}/${LOG_STEM}-\$(date +\\%F).log\" 2>&1'"
} > /etc/cron.d/stocksearcher
chmod 0644 /etc/cron.d/stocksearcher
crontab /etc/cron.d/stocksearcher

touch "${LOG_DIR}/${LOG_STEM}-$(date +%F).log"
echo "cron schedule jp2: ${CRON_SCHEDULE_JP2}"
echo "cron command jp2: ${JOB_CMD_JP2}"
echo "cron schedule kr2: ${CRON_SCHEDULE_KR2}"
echo "cron command kr2: ${JOB_CMD_KR2}"

cron

WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-9999}"
echo "web ui: http://${WEB_HOST}:${WEB_PORT}"
exec python webapp.py
