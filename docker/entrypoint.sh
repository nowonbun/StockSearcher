#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

CRON_SCHEDULE_JP="${CRON_SCHEDULE_JP:-0 2 * * *}"
CRON_SCHEDULE_KR="${CRON_SCHEDULE_KR:-0 4 * * *}"
JOB_CMD_JP="${JOB_CMD_JP:-python dataset_jp.py && python predict_jp.py --model /models/model_jp.pt --seq-len 60 --top-k 20 --save-db}"
JOB_CMD_KR="${JOB_CMD_KR:-python dataset_kr.py && python predict_kr.py --model /models/model_kr.pt --seq-len 60 --top-k 20 --save-db}"
LOG_DIR_DEFAULT="${CRON_LOG_DIR:-/data/log}"
LOG_PATH="${CRON_LOG_PATH:-${LOG_DIR_DEFAULT}/cron.log}"
LOG_DIR="$(dirname "$LOG_PATH")"
LOG_BASE="$(basename "$LOG_PATH")"
LOG_STEM="${LOG_BASE%.log}"

mkdir -p "${LOG_DIR}"

{
  echo "${CRON_SCHEDULE_JP} root /bin/bash -lc 'cd /app && ${JOB_CMD_JP} >> \"${LOG_DIR}/${LOG_STEM}-\$(date +\\%F).log\" 2>&1'"
  echo "${CRON_SCHEDULE_KR} root /bin/bash -lc 'cd /app && ${JOB_CMD_KR} >> \"${LOG_DIR}/${LOG_STEM}-\$(date +\\%F).log\" 2>&1'"
} > /etc/cron.d/stocksearcher
chmod 0644 /etc/cron.d/stocksearcher
crontab /etc/cron.d/stocksearcher

touch "${LOG_DIR}/${LOG_STEM}-$(date +%F).log"
echo "cron schedule jp: ${CRON_SCHEDULE_JP}"
echo "cron command jp: ${JOB_CMD_JP}"
echo "cron schedule kr: ${CRON_SCHEDULE_KR}"
echo "cron command kr: ${JOB_CMD_KR}"

cron

WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-9999}"
echo "web ui: http://${WEB_HOST}:${WEB_PORT}"
exec python webapp.py
