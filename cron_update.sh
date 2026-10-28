#!/bin/bash
# ==============================================================================
# 台股大盤 + 自選個股 Market Regime Dashboard 每日自動更新與 GitHub Pages 同步腳本
# 供 macOS crontab 定時呼叫（已補齊非互動環境所需的 Node/npm/Git PATH 與 UTF-8 語系）
# ==============================================================================
set -euo pipefail

export HOME="/Users/ryanyang"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="Asia/Taipei"
export PATH="/Users/ryanyang/.hermes/node/bin:/Users/ryanyang/.pyenv/shims:/Users/ryanyang/.pyenv/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_DIR="/Users/ryanyang/my_code/code/Projects/TW stock dashboard 2"
LOG_FILE="${PROJECT_DIR}/cron_sync.log"
LOCK_DIR="/tmp/tw_stock_regime_dashboard_sync.lock"

# 防止重入：若鎖存在超過 30 分鐘視為異常殘留並清除
if [ -d "${LOCK_DIR}" ]; then
  if [ "$(find "${LOCK_DIR}" -mmin +30 2>/dev/null | wc -l)" -gt 0 ]; then
    rm -rf "${LOCK_DIR}"
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已有同步程序執行中，略過本次排程。" >> "${LOG_FILE}"
    exit 0
  fi
fi

mkdir -p "${LOCK_DIR}"
trap 'rm -rf "${LOCK_DIR}"' EXIT

# 控制 log 檔案大小（保留最近 2000 行）
if [ -f "${LOG_FILE}" ] && [ "$(wc -l < "${LOG_FILE}")" -gt 2500 ]; then
  tail -n 2000 "${LOG_FILE}" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
fi

{
  echo ""
  echo "==================== [$(date '+%Y-%m-%d %H:%M:%S %Z')] CRON SYNC START ===================="
  cd "${PROJECT_DIR}"
  "${PROJECT_DIR}/backend/.venv/bin/python" "${PROJECT_DIR}/sync_github.py"
  echo "==================== [$(date '+%Y-%m-%d %H:%M:%S %Z')] CRON SYNC DONE ====================="
} >> "${LOG_FILE}" 2>&1
