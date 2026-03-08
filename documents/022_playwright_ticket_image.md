# チケット画像 API と Playwright（503 対策）

`GET /api/ext/v1/ticket/image/{nft_origin}` は、NFT に保存された HTML を Playwright（Chromium）で PNG に変換して返します。

## 開発環境での venv マウント（イメージ再ビルドを減らす）

開発用 compose（`docker-compose.dev.yml`）では **`./venv` を `/home/app/venv` にマウント**しています。

- **初回起動時**: コンテナの entrypoint が `./venv` が空なら venv を作成し、`pip install -r requirements.txt` で依存をインストールします。**イメージの再ビルドは不要**です。
- **2回目以降**: 既存の venv をそのまま使うため起動が速く、`requirements.txt` を変えたときも「コンテナ内で `pip install -r requirements.txt`」または「`./venv` を消して再起動」で反映できます。
- **ホストで確認**: コンテナは Linux なので、ホストも Linux（WSL2 含む）なら `./venv` にできた venv をそのまま利用できます。
  ```bash
  . venv/bin/activate
  python -c "from playwright.sync_api import sync_playwright; print('OK')"
  ```

本番（`docker-compose.prod.yml`）では venv はマウントしないため、従来どおりイメージに含まれた Python パッケージを使います。

## 503 "Playwright not installed" が出る場合

**原因**: 実行している環境に Playwright が入っていないか、Chromium がインストールされていません。

### Docker 開発環境（venv マウントあり）の場合

1. **初回は起動完了まで待つ**  
   初回は「Creating venv at /home/app/venv and installing dependencies...」が出て数分かかります。完了すると `venv ready.` が出てサーバーが起動します。
2. **既に起動済みなのに 503 のとき**  
   `./venv` を消してから再起動し、venv を再作成させてください。
   ```bash
   rm -rf venv
   ./bin/restart-dev
   ```

### イメージをビルドし直す場合（本番や venv を使わない構成）

**イメージをキャッシュなしで再ビルド**してください。**必ず `--no-cache` を付けて**ビルドし、**完了まで待つ**（数分かかります。途中で Ctrl+C しないこと）。

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache ticket_web
./bin/restart-dev
```

- **`Built 0.0s` と出る場合**（`--no-cache` を付けているのに一瞬で終わる）: BuildKit のキャッシュが別扱いになっている可能性があります。次を試してください。
  1. **詳細ログで何が走っているか確認**  
     `docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache --progress=plain ticket_web`  
     → 各 `RUN` が実行されていれば、その後に「naming」「exporting」だけが 0.0s と表示されているだけかもしれません。
  2. **ベースイメージも含めてやり直す**  
     `docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache --pull ticket_web`
  3. **BuildKit を切ってレガシービルダーで試す**  
     `DOCKER_BUILDKIT=0 docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache ticket_web`
  4. **ビルダーキャッシュを削除してから再ビルド**  
     `docker builder prune -af` のあと、上記の `build --no-cache` を再度実行。

### インストール確認

コンテナが起動している状態で、**exec** して Playwright が使えるか確認できます。開発環境では venv を使うため、**venv の Python を指定**してください。

```bash
# 開発環境（venv マウントあり）: venv の python を使う
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web \
  /home/app/venv/bin/python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True, args=['--no-sandbox']); b.close(); print('OK')"
```

`OK` と出れば利用可能です。`/home/app/venv/bin/python` が無い場合は、初回起動で venv 作成がまだの可能性があります（ログの「venv ready.」を確認）。

スクリプトでまとめて確認する場合:

```bash
./bin/verify-playwright
```

### ローカル（Docker 外）で動かしている場合

```bash
cd app
pip install playwright
playwright install chromium
```

その後、同じ curl で画像 API を叩いて動作を確認してください。
