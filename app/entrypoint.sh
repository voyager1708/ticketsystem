#!/bin/bash

# サーバーのワーカー数を設定、デフォルトは5
WORKERS="${NUM_WORKERS:-5}"
# タイムアウト設定
TIMEOUT="${TIMEOUT:-900}"
MYUID=`/usr/bin/id -u`
MYGID=`/usr/bin/id -G`
MYUSERNAME=`/usr/bin/id -un`

echo "Starting the server UID:[${MYUID}],GID[${MYGID}],USERNAME:[${MYUSERNAME}] with [${WORKERS}] workers, timeout:[${TIMEOUT}]s ..."
echo "Starting the server HOST_UID:[${HOST_UID}],HOST_GID[${HOST_GID}],HOST_USERNAME:[${HOST_USERNAME}] with [${NUM_WORKERS}] workers ..."

# マイグレーションを実行
echo "Running migrations..."
python manage.py migrate --noinput

# デフォルトのTicketDesignを作成（存在しない場合のみ）
echo "Setting up default TicketDesign..."
python manage.py setup_default_ticket_design || echo "TicketDesign setup skipped or failed"

# サーバーを実行
exec /bin/sh -c "gunicorn ticket_config.wsgi:application --bind 0.0.0.0:8001 --workers $WORKERS --timeout $TIMEOUT"

