#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd "${REPO_DIR}/app" && pwd)"

cd "${PROJECT_DIR}"

if [[ ! -f "manage.py" ]]; then
  echo "manage.py not found in ${PROJECT_DIR}" >&2
  exit 1
fi

DEFAULT_EVENT_NAME="Test Event"
DEFAULT_EVENT_DATE="2026-02-01T18:00:00+09:00"
DEFAULT_VENUE="Test Venue"
DEFAULT_SEAT="A-1"

has_flag() {
  local flag="$1"
  shift
  for arg in "$@"; do
    if [[ "$arg" == "$flag" ]]; then
      return 0
    fi
  done
  return 1
}

# オプション:
# --username / --password（デフォルトで指定のテストアカウント）
# --recipient-paymail
# --ticket-design-id
# --ticket-design-name
# --ticket-design-layout
# --template-image
# --checkin-reward-image
# --public-url
# --event-name
# --event-date
# --venue
# --seat
# --ticket-design-layout '{"text": {"x": 40, "y": 40}, "qr": {"x": 500, "y": 40, "size": 200}}'

ARGS=("$@")
if ! has_flag "--event-name" "${ARGS[@]}"; then
  ARGS+=(--event-name "${DEFAULT_EVENT_NAME}")
fi
if ! has_flag "--event-date" "${ARGS[@]}"; then
  ARGS+=(--event-date "${DEFAULT_EVENT_DATE}")
fi
if ! has_flag "--venue" "${ARGS[@]}"; then
  ARGS+=(--venue "${DEFAULT_VENUE}")
fi
if ! has_flag "--seat" "${ARGS[@]}"; then
  ARGS+=(--seat "${DEFAULT_SEAT}")
fi

PYTHON_BIN="python"
if [[ -x "${REPO_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
elif [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
elif [[ -x "${PROJECT_DIR}/venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/venv/bin/python"
fi

# ローカル実行用DB接続設定（Docker外からの接続）
export SQL_HOST="${SQL_HOST:-localhost}"
export SQL_PORT="${SQL_PORT:-5434}"

"${PYTHON_BIN}" manage.py create_ticket "${ARGS[@]}"

