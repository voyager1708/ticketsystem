# Dockerfile / .env / 実際のディレクトリ所有者 UID 比較表

## 1. Dockerfile で指定しているユーザ・UID（ビルド引数）

| 項目 | 値 | 出典 |
|------|-----|------|
| ARG（ビルド時引数） | UID, GID, USERNAME, NUM_WORKERS | app/Dockerfile 43–46行目 |
| コンテナ内ユーザ作成 | `addgroup --gid $GID $USERNAME` / `adduser --uid $UID --gid $GID $USERNAME` | 65–67行目 |
| 実行ユーザ | `USER ${USERNAME}` | 90行目 |
| APP_HOME の chown | `chown -R ${USERNAME}:$GID $APP_HOME` | 86–87行目 |

※コンテナ内の UID/GID はビルド時に渡された `UID` / `GID` で決定される。

---

## 2. .env の設定値（ビルド引数に渡す元）

| 項目 | .env 変数名 | 設定値 | Dockerfile の ARG への対応 |
|------|-------------|--------|----------------------------|
| ホスト UID | HOST_UID | 1000 | → UID |
| ホスト GID | HOST_GID | 1000 | → GID |
| コンテナ内ユーザ名 | CONTAINER_USERNAME | app | → USERNAME |

※docker-compose.yml の `build.args`: `UID: ${HOST_UID}`, `GID: ${HOST_GID}`, `USERNAME: ${CONTAINER_USERNAME}`

---

## 3. 実際のディレクトリ・ファイルのオーナ（UID/GID）

| パス | UID | GID | 備考 |
|------|-----|-----|------|
| プロジェクトルート `./` | 1001 | 1002 | `ls -lan .` の所有者 |
| `./app` | 1001 | 1002 | マウント元（コンテナ内は `/home/app/web`） |
| `./.env` | 1001 | 1002 | マウント元（コンテナ内は `/home/app/.env`） |

※取得日時のコマンド: `ls -lan .` / `ls -lan app` / `ls -lan .env`

---

## 4. 整合性一覧表（Dockerfile / .env / 実際のディレクトリ）

| 比較項目 | Dockerfile（ビルド時の UID/GID） | .env の設定 | 実際のディレクトリ所有者 | 整合 |
|----------|----------------------------------|-------------|--------------------------|------|
| UID | ビルド引数 UID で決定 | HOST_UID=**1000** | **1001** | ❌ 不一致 |
| GID | ビルド引数 GID で決定 | HOST_GID=**1000** | **1002** | ❌ 不一致 |
| ユーザ名 | USERNAME（コンテナ内） | CONTAINER_USERNAME=**app** | — | — |

---

## 5. 結論と対応方針

- **現状**: .env は UID=1000, GID=1000 で、実際のディレクトリ所有者は UID=1001, GID=1002。
- **影響**: コンテナは UID=1000 で動作するため、マウントされた `./app`（所有者 1001）への書き込みで権限エラーになる可能性がある。
- **対応案**: `.env` の `HOST_UID` / `HOST_GID` を **1001 / 1002** に合わせ、`docker compose build --no-cache` でイメージを再ビルドする。

```bash
# .env の変更例
HOST_UID=1001
HOST_GID=1002
```

---

*このドキュメントは `docs/docker-user-uid-matrix.md` として保存されています。*
