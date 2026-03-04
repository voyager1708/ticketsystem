#!/usr/bin/env bash
set -euo pipefail

# ticketsystem-dev -> ticketsystem installer
#
# What this does:
# - Sync repo contents into INSTALL_ROOT (default: /mnt/extra/ticketsystem)
# - Preserve runtime data directories (app/logs, app/media) during sync
# - If .env exists and SECRET_KEY is empty or placeholder, generate a random one
# - Ensure Python venv exists and install Python deps
# - Optionally build Tailwind assets (theme/static_src) if present, and run collectstatic
#
# Notes:
# - This repo is NOT ansible-based.
# - Django loads env from INSTALL_ROOT/.env (and optional INSTALL_ROOT/env.local).

INSTALL_ROOT="${INSTALL_ROOT:-/mnt/extra/ticketsystem}"
REPO_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RECREATE_VENV="${RECREATE_VENV:-0}"
SKIP_VENV="${SKIP_VENV:-0}"
SKIP_NPM="${SKIP_NPM:-0}"
SKIP_COLLECTSTATIC="${SKIP_COLLECTSTATIC:-0}"
SKIP_RSYNC="${SKIP_RSYNC:-0}"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --recreate-venv Recreate venv/ at destination (DANGEROUS: reinstalls deps)
  --skip-venv     Do not create/install Python venv
  --skip-npm      Do not build Tailwind assets (npm)
  --skip-collectstatic Do not run Django collectstatic
  --skip-rsync    Do not rsync code into INSTALL_ROOT
  -h, --help      Show this help

Environment variables:
  INSTALL_ROOT        Install destination (default: /mnt/extra/ticketsystem)
  RECREATE_VENV       1 to recreate venv (same as --recreate-venv)
  SKIP_VENV           1 to skip venv setup (same as --skip-venv)
  SKIP_NPM            1 to skip npm build (same as --skip-npm)
  SKIP_COLLECTSTATIC  1 to skip collectstatic (same as --skip-collectstatic)
  SKIP_RSYNC          1 to skip rsync (same as --skip-rsync)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate-venv)
      RECREATE_VENV=1
      shift
      ;;
    --skip-venv)
      SKIP_VENV=1
      shift
      ;;
    --skip-npm)
      SKIP_NPM=1
      shift
      ;;
    --skip-collectstatic)
      SKIP_COLLECTSTATIC=1
      shift
      ;;
    --skip-rsync)
      SKIP_RSYNC=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[install] ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[install] ERROR: missing command: $1" >&2
    exit 1
  }
}

# Bootstrap pip when ensurepip is disabled (e.g. Debian/Ubuntu system Python).
bootstrap_pip() {
  local venv_py="$1"
  local get_pip="/tmp/get-pip-$$.py"
  python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '${get_pip}')" || {
    echo "[install] ERROR: failed to download get-pip.py (network required)" >&2
    rm -f "${get_pip}"
    exit 1
  }
  "${venv_py}" "${get_pip}"
  rm -f "${get_pip}"
}

pick_sudo() {
  # Use sudo only if needed (mkdir/chown under /mnt/extra or INSTALL_ROOT)
  if mkdir -p "${INSTALL_ROOT}" >/dev/null 2>&1; then
    echo ""
    return
  fi
  if sudo -n true >/dev/null 2>&1; then
    echo "sudo -n"
    return
  fi
  echo "[install] ERROR: cannot create ${INSTALL_ROOT} without sudo, and sudo -n is not available." >&2
  echo "[install]        Run as a user who can write to ${INSTALL_ROOT}, or configure passwordless sudo." >&2
  exit 1
}

echo "[install] repo: ${REPO_SRC_DIR}"
echo "[install] install root: ${INSTALL_ROOT}"
if [[ "${RECREATE_VENV}" == "1" ]]; then
  echo "[install] WARNING: --recreate-venv enabled (venv will be deleted and recreated)"
fi

need_cmd rsync
need_cmd realpath
need_cmd python3

SUDO="$(pick_sudo)"

echo "[install] ensuring directories..."
if [[ -n "${SUDO}" ]]; then
  ${SUDO} mkdir -p /mnt/extra "${INSTALL_ROOT}"
  ${SUDO} chown -R "${USER}:${USER}" "${INSTALL_ROOT}" || true
else
  mkdir -p /mnt/extra "${INSTALL_ROOT}"
fi

if [[ "${SKIP_RSYNC}" == "1" ]]; then
  echo "[install] SKIP_RSYNC=1; skipping rsync"
else
  if [[ "$(realpath "${REPO_SRC_DIR}")" != "$(realpath "${INSTALL_ROOT}")" ]]; then
    echo "[install] syncing code to ${INSTALL_ROOT}..."
    # Preserve runtime directories even with --delete
    rsync -a --delete \
      --exclude ".git/" \
      --exclude ".cursor/" \
      --exclude ".idea/" \
      --exclude ".vscode/" \
      --exclude ".venv/" \
      --exclude ".env" \
      --exclude ".env.*" \
      --exclude "env.local" \
      --exclude "venv/" \
      --exclude "venv_backup*/" \
      --exclude "node_modules/" \
      --exclude "app/theme/static_src/node_modules/" \
      --exclude "app/.venv/" \
      --exclude "app/logs/" \
      --exclude "app/media/" \
      --exclude "**/__pycache__/" \
      --exclude "*.pyc" \
      "${REPO_SRC_DIR}/" "${INSTALL_ROOT}/"
    if [[ -n "${SUDO}" ]]; then
      ${SUDO} chown -R "${USER}:${USER}" "${INSTALL_ROOT}" || true
    fi
  else
    echo "[install] source and destination are the same; skipping rsync"
  fi
fi

echo "[install] checking .env..."
SRC_ENV="${REPO_SRC_DIR}/.env"
DST_ENV="${INSTALL_ROOT}/.env"
if [[ -f "${SRC_ENV}" ]]; then
  if [[ ! -f "${DST_ENV}" ]]; then
    echo "[install] .env does not exist in destination. copying..."
    cp "${SRC_ENV}" "${DST_ENV}"
  elif [[ "${SRC_ENV}" -nt "${DST_ENV}" ]]; then
    echo "[install] source .env is newer than destination. updating..."
    cp "${SRC_ENV}" "${DST_ENV}"
  else
    echo "[install] destination .env is up to date."
  fi
  chmod 600 "${DST_ENV}" || true
else
  echo "[install] NOTE: .env not found in source directory. (OK if you manage env on the server)"
fi

# HOST_UID / HOST_GID を実行ユーザの UID/GID に更新（Docker などで使う）
if [[ -f "${DST_ENV}" ]]; then
  RUN_UID=$(id -u)
  RUN_GID=$(id -g)
  INSTALL_DST_ENV="${DST_ENV}" INSTALL_UID="${RUN_UID}" INSTALL_GID="${RUN_GID}" python3 -c '
import os
path = os.environ["INSTALL_DST_ENV"]
uid = os.environ["INSTALL_UID"]
gid = os.environ["INSTALL_GID"]
lines = open(path).readlines()
out = []
uid_done = gid_done = False
for line in lines:
    s = line.strip()
    if s.startswith("HOST_UID="):
        out.append("HOST_UID=" + uid + "\n")
        uid_done = True
    elif s.startswith("HOST_GID="):
        out.append("HOST_GID=" + gid + "\n")
        gid_done = True
    else:
        out.append(line)
if not uid_done:
    out.append("HOST_UID=" + uid + "\n")
if not gid_done:
    out.append("HOST_GID=" + gid + "\n")
open(path, "w").writelines(out)
'
  echo "[install] HOST_UID=${RUN_UID} HOST_GID=${RUN_GID} (runtime user)"
  if chown "${RUN_UID}:${RUN_GID}" "${DST_ENV}" 2>/dev/null; then
    echo "[install] chown ${RUN_UID}:${RUN_GID} ${DST_ENV}"
  else
    chmod 644 "${DST_ENV}" 2>/dev/null && echo "[install] chmod 644 ${DST_ENV} (chown skipped, need rights)"
  fi
fi

# SECRET_KEY が空またはプレースホルダーならランダム生成して設定
if [[ -f "${DST_ENV}" ]]; then
  CURRENT_SECRET="$(
    grep -E '^SECRET_KEY=' "${DST_ENV}" 2>/dev/null \
    | cut -d= -f2- \
    | sed -e 's/^["'\'']//' -e 's/["'\'']$//' \
    | tr -d '\n\r' \
    | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  )"
  if [[ -z "${CURRENT_SECRET}" ]] \
     || [[ "${CURRENT_SECRET}" == "your-secret-key-here" ]] \
     || [[ "${CURRENT_SECRET}" == "django-insecure-change-me-in-production" ]]; then
    if ! command -v openssl >/dev/null 2>&1; then
      echo "[install] ERROR: SECRET_KEY is empty/placeholder and openssl is not available. Install openssl or set SECRET_KEY in .env" >&2
      exit 1
    fi
    NEW_SECRET="$(openssl rand -base64 50 | tr -d '\n\r')"
    echo "[install] SECRET_KEY empty or placeholder; generating and setting random value..."
    INSTALL_DST_ENV="${DST_ENV}" INSTALL_NEW_SECRET="${NEW_SECRET}" python3 -c '
import os
path = os.environ["INSTALL_DST_ENV"]
key = os.environ["INSTALL_NEW_SECRET"]
lines = open(path).readlines()
out = []
done = False
for line in lines:
    s = line.strip()
    if s.startswith("SECRET_KEY="):
        out.append("SECRET_KEY=" + key + "\n")
        done = True
    else:
        out.append(line)
if not done:
    out.append("SECRET_KEY=" + key + "\n")
open(path, "w").writelines(out)
'
  fi
fi

echo "[install] ensuring runtime directories..."
mkdir -p "${INSTALL_ROOT}/app/logs" "${INSTALL_ROOT}/app/media"

VENV_DIR="${INSTALL_ROOT}/venv"
VENV_PY="${VENV_DIR}/bin/python"

if [[ "${SKIP_VENV}" == "1" ]]; then
  echo "[install] SKIP_VENV=1; skipping venv setup"
else
  if [[ "${RECREATE_VENV}" == "1" && -d "${VENV_DIR}" ]]; then
    echo "[install] removing existing venv..."
    rm -rf "${VENV_DIR}"
  fi

  if [[ ! -x "${VENV_PY}" ]]; then
    echo "[install] creating venv..."
    if ! python3 -m venv "${VENV_DIR}" 2>/dev/null; then
      echo "[install] venv with ensurepip failed (e.g. Debian/Ubuntu); creating venv without pip..."
      rm -rf "${VENV_DIR}"
      python3 -m venv --without-pip "${VENV_DIR}"
      echo "[install] bootstrapping pip via get-pip.py..."
      bootstrap_pip "${VENV_PY}"
    fi
  fi

  if ! "${VENV_PY}" -m pip --version >/dev/null 2>&1; then
    echo "[install] pip missing in venv; bootstrapping via get-pip.py..."
    bootstrap_pip "${VENV_PY}"
  fi

  echo "[install] installing python deps..."
  "${VENV_PY}" -m pip install --upgrade pip
  "${VENV_PY}" -m pip install -r "${INSTALL_ROOT}/app/requirements.txt"
fi

THEME_DIR="${INSTALL_ROOT}/app/theme/static_src"
if [[ "${SKIP_NPM}" == "1" ]]; then
  echo "[install] SKIP_NPM=1; skipping npm build"
else
  if [[ -d "${THEME_DIR}" ]]; then
    if command -v npm >/dev/null 2>&1; then
      echo "[install] building Tailwind assets (theme)..."
      pushd "${THEME_DIR}" >/dev/null
      if [[ -f package-lock.json ]]; then
        npm ci
      else
        npm install
      fi
      npm run build
      popd >/dev/null
    else
      echo "[install] WARNING: npm not found; skipping Tailwind build (set SKIP_NPM=1 to silence)"
    fi
  else
    echo "[install] NOTE: theme/static_src not found; skipping Tailwind build"
  fi
fi

if [[ "${SKIP_COLLECTSTATIC}" == "1" ]]; then
  echo "[install] SKIP_COLLECTSTATIC=1; skipping collectstatic"
else
  if [[ -x "${VENV_PY}" && -f "${INSTALL_ROOT}/app/manage.py" ]]; then
    if [[ -f "${DST_ENV}" || -f "${INSTALL_ROOT}/env.local" ]]; then
      echo "[install] running collectstatic..."
      pushd "${INSTALL_ROOT}/app" >/dev/null
      "${VENV_PY}" manage.py collectstatic --noinput
      popd >/dev/null
    else
      echo "[install] NOTE: no .env/env.local found in ${INSTALL_ROOT}; skipping collectstatic"
    fi
  else
    echo "[install] NOTE: venv or manage.py missing; skipping collectstatic"
  fi
fi

echo "[install] done."


