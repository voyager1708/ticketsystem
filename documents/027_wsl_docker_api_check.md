# WSL 内で Docker を起動して API 疎通確認（BASE_API_URL）まで

Windows で **WSL の Ubuntu** を使い、Docker でチケットシステムを起動し、**BASE_API_URL**（TICKETSYSTEM / ベースAPI）への疎通確認まで行う手順です。

---

## 前提

- WSL2 + Ubuntu 24.04 が入っていること（`documents/001_setup_v1_start.md` 参照）
- Docker が WSL 内にインストール済みであること（`documents/025_docker_installation.md` 参照）
- プロジェクトを WSL のパスでクローンしていること（例: `/home/<user>/ticketsystem-start`）

---

## 1. WSL の Ubuntu ターミナルを開く

- **Windows ターミナル** または **Cursor のターミナル** で「Ubuntu」を選ぶ  
- または PowerShell で `wsl` と入力して WSL に入る

```powershell
wsl
```

プロジェクトルートに移動します。

```bash
cd /path/to/ticketsystem-start
# 例: cd ~/ticketsystem-start
```

---

## 2. .env の確認

`BASE_API_URL` が設定されていることを確認します。

```bash
grep BASE_API_URL .env
```

例:

```
BASE_API_URL=https://bsvapi01.cds.tohoku.ac.jp
```

必要なら `.env` を編集して保存してください。

---

## 3. Docker でコンテナを起動

プロジェクトルートで、開発用にコンテナを起動します。

```bash
./bin/start-dev
```

または直接:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

初回はビルドに時間がかかります。起動後、コンテナが動いているか確認します。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

`ticket_web` が `Up` になっていれば OK です。

---

## 4. チケットシステム本体の疎通確認（healthz）

拡張API（このプロジェクト）が応答するか確認します。ポートは **8001** です。

```bash
curl -fsS http://localhost:8001/healthz
```

`200` やレスポンスが返れば、Docker 内のアプリは起動できています。

ブラウザで Swagger も確認できます。

- http://localhost:8001/swagger/

---

## 5. BASE_API_URL の疎通確認

コンテナ内で、設定されている **BASE_API_URL** へ実際に HTTP リクエストを送り、疎通できるかを確認します。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web python manage.py check_base_api --insecure
```

出力例（疎通できている場合）:

```
BASE_API_URL = https://bsvapi01.cds.tohoku.ac.jp

  GET https://bsvapi01.cds.tohoku.ac.jp  ->  200


If you see status 200 or 404, the host is reachable. Use --insecure for self-signed/internal CA.
```

### SSL 証明書エラーが出る場合

社内・学内の API で自己署名証明書や内部 CA を使っている場合は、`--insecure` を付けて再実行します。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web python manage.py check_base_api --insecure
```

疎通できていれば、同様に `200` や `404` などのステータスが表示されます。

---

## 6. 終了時

コンテナを止めるときは、プロジェクトルートで:

```bash
./bin/stop-dev
```

または:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

---

## まとめ

| 手順 | コマンド |
|------|----------|
| 1. WSL に入る | `wsl`（PowerShell から） |
| 2. プロジェクトへ | `cd ~/ticketsystem-start` |
| 3. 起動 | `./bin/start-dev` |
| 4. 本体確認 | `curl -fsS http://localhost:8001/healthz` |
| 5. BASE_API_URL 確認 | `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web python manage.py check_base_api` |
| 6. 停止 | `./bin/stop-dev` |

`check_base_api` は `.env` の `BASE_API_URL` を読み、その URL と `/api/v1/` などへ GET して疎通結果を表示します。SSL エラー時は `--insecure` を試してください。
