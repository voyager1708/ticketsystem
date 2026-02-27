#!/bin/bash
set -e

# 本番/開発の明示が必要。docker-compose.yml 単体での起動を防ぐ。
if [ -z "${DEPLOY_ENV}" ]; then
  echo "ERROR: DEPLOY_ENV is not set. Do not run 'docker compose up' alone." >&2
  echo "Use: ./bin/start-dev  or  ./bin/start-prod" >&2
  echo "  (docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d)" >&2
  echo "  (docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d)" >&2
  exit 1
fi

# サーバーのワーカー数を設定、デフォルトは5
WORKERS="${NUM_WORKERS:-5}"
# タイムアウト設定
TIMEOUT="${TIMEOUT:-900}"
MYUID=`/usr/bin/id -u`
MYGID=`/usr/bin/id -G`
MYUSERNAME=`/usr/bin/id -un`

echo "DEPLOY_ENV=[${DEPLOY_ENV}]"
echo "Starting the server UID:[${MYUID}],GID[${MYGID}],USERNAME:[${MYUSERNAME}] with [${WORKERS}] workers, timeout:[${TIMEOUT}]s ..."
echo "Starting the server HOST_UID:[${HOST_UID}],HOST_GID[${HOST_GID}],HOST_USERNAME:[${HOST_USERNAME}] with [${NUM_WORKERS}] workers ..."

# マイグレーションを実行
echo "Running migrations..."
python manage.py migrate --noinput

# デフォルトのTicketDesignを作成（存在しない場合のみ）
echo "Setting up default TicketDesign..."
python manage.py setup_default_ticket_design || echo "TicketDesign setup skipped or failed"

# 静的ファイルを STATIC_ROOT に集約（Swagger UI 等）
echo "Running collectstatic..."
python manage.py collectstatic --noinput --clear 2>/dev/null || true

# サーバーを実行
exec /bin/sh -c "gunicorn ticket_system.wsgi:application --bind 0.0.0.0:8001 --workers $WORKERS --timeout $TIMEOUT"

