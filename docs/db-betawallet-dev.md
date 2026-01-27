# ticket_system で betawallet-dev の Postgres を使う

ticket_db を使わず、betawallet-dev の Docker db に接続する場合の手順です。

## 1. betawallet-dev 側で ticket_system 用 DB を作成

betawallet-dev の db コンテナが起動している状態で:

```bash
cd /mnt/extra/betawallet-dev
POSTGRES_MULTIPLE_DATABASES="betawallet_dev,betawallet_prod,ticket_system" ./bin/ensure_postgres_databases.sh
```

これで Postgres 内に `ticket_system` データベースが作成されます（所有者は betawallet-dev の `POSTGRES_USER`）。

## 2. ticket_system の .env で DB 接続を指定

ticket_web は Docker 内で動くため、**ホスト**の Postgres に届けるには `host.docker.internal` と**ホスト側のポート**を使います。

betawallet-dev の db は `127.0.0.1:5434:5432` で公開されているので、ticket_system の `.env` には次のように書きます。

```ini
# betawallet-dev の Docker db に接続（ticket_web は Docker 内のため host.docker.internal を使用）
SQL_HOST=host.docker.internal
SQL_PORT=5434
SQL_DATABASE=ticket_system
SQL_USER=yp_dev_user
SQL_PASSWORD=yp_dev_p@ssword
```

- **SQL_USER** / **SQL_PASSWORD** は、betawallet-dev の `.env` の `POSTGRES_USER` / `POSTGRES_PASSWORD` と同じにしてください。（上記は betawallet-dev の例です。）
- betawallet-dev で別のユーザ／パスワードにしている場合は、その値に合わせてください。

## 3. ticket_web から host.docker.internal を解決するため

`docker-compose.yml` の `ticket_web` に `extra_hosts: - "host.docker.internal:host-gateway"` が入っていることを確認してください。これがないとコンテナ内から `host.docker.internal` にアクセスできません。

## まとめ

| 項目 | 値 |
|------|-----|
| SQL_HOST | `host.docker.internal` |
| SQL_PORT | `5434`（betawallet-dev の db のホスト公開ポート） |
| SQL_DATABASE | `ticket_system` |
| SQL_USER | betawallet-dev の `POSTGRES_USER` と同じ |
| SQL_PASSWORD | betawallet-dev の `POSTGRES_PASSWORD` と同じ |

※ ホスト上で Django を直接動かす場合（Docker を使わない）は、`SQL_HOST=127.0.0.1` または `localhost`、`SQL_PORT=5434` にします。
