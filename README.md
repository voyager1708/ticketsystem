# チケットシステム マイクロサービス

このプロジェクトは、BETAWALLET-DEVのベースAPIを拡張する独立したマイクロサービスです。チケットNFTの画像生成とチェックイン処理を提供します。

## 概要

- **ベースAPI**: 変更なし
- **拡張API**: ticket_system（このプロジェクト）
- **認証**: セッション認証（ベースAPIと共有）
- **データベース**: SQLite（デフォルト。`.env` で `USE_SQLITE=True`）。本番・PostgreSQL 連携時は `USE_SQLITE` を外して PostgreSQL を利用可能

## プロジェクト構造

```
/mnt/extra/ticket_system/
├── app/                          # Djangoアプリケーション
│   ├── Dockerfile                # Djangoコンテナ用
│   ├── entrypoint.sh             # Gunicorn起動スクリプト
│   ├── manage.py
│   ├── requirements.txt          # Python依存関係
│   ├── ticket_service/           # チケットサービスアプリ
│   │   ├── models.py             # TicketDesignモデル
│   │   ├── views.py              # APIエンドポイント
│   │   ├── admin.py              # Django Admin設定
│   │   ├── urls.py               # URLルーティング
│   │   └── services/
│   │       ├── base_api_client.py    # ベースAPI呼び出しクライアント
│   │       └── ticket_service.py     # チケット画像生成ロジック
│   ├── ticket_system/            # Djangoプロジェクト設定
│   │   ├── settings.py           # Django設定
│   │   └── urls.py               # ルートURL設定
│   ├── static/                   # 静的ファイル
│   ├── media/                    # メディアファイル
│   └── logs/                     # ログファイル
├── nginx/                        # Nginx設定
│   ├── Dockerfile                # Nginxコンテナ用
│   └── nginx.conf                 # Nginx設定ファイル
├── docker-compose.yml            # Docker Compose設定
├── .env.example                  # 環境変数テンプレート
└── README.md                     # このファイル
```

## サービス構成

### サービス名（重複回避）
- `ticket_web`: Djangoアプリケーション（ポート: 8001）。デフォルトでは **SQLite**（`db.sqlite3`）を使用
- `ticket_nginx`: Nginxリバースプロキシ（ポート: 1338, 5443）（docker-compose ではコメントアウト）
- `ticket_db`: PostgreSQL（ポート: 5433）。**オプション**。`USE_SQLITE` を無効にした場合に利用（docker-compose ではコメントアウト）

### ポート番号（BETAWALLET-DEVと重複回避）
- `8001`: Djangoアプリケーション（BETAWALLET-DEVの`8000`に対応）
- `1338`: Nginx HTTP（BETAWALLET-DEVの`1337`に対応）
- `5443`: Nginx HTTPS（BETAWALLET-DEVの`443`に対応）
- `5433`: PostgreSQL（BETAWALLET-DEVの`5432`に対応）

## セットアップ

### 0. プロジェクトの取得（Git）

Git が未導入の場合は先にインストールしてください（例: Ubuntu なら `sudo apt install -y git`）。

```bash
git clone https://github.com/voyager1708/ticketsystem-start.git
cd ticketsystem-start
```

### 1. 環境変数の設定

`.env.example`をコピーして`.env`を作成し、必要な値を設定してください。

```bash
cp .env.example .env
```

主な設定項目:
- `SECRET_KEY`: Djangoのシークレットキー
- `USE_SQLITE`: `True` のとき **SQLite** を使用（ハンズオン・開発向け）。`False` または未設定で PostgreSQL を使用する場合は `SQL_*` を設定
- `SQL_*`: PostgreSQL を使う場合の接続情報（`SQL_HOST`, `SQL_PORT`, `SQL_DATABASE`, `SQL_USER`, `SQL_PASSWORD`）
- `BASE_API_URL`: ベースAPIのURL
- `HOST_UID`, `HOST_GID`: コンテナ内のユーザーID/GID

### 2. Docker Composeで起動

```bash
docker compose up -d
```

### 3. データベースマイグレーション

```bash
docker compose exec ticket_web python manage.py migrate
```

### 4. スーパーユーザーの作成（オプション）

```bash
docker compose exec ticket_web python manage.py createsuperuser
```

### 5. 動作確認

```bash
curl -fsS http://localhost:8001/healthz
```

`200` が返れば起動成功です。ブラウザで `http://localhost:8001/swagger/` を開いて API 仕様を確認できます。

## APIエンドポイント

### Swagger / API仕様

```
GET /swagger/      # Swagger UI
GET /redoc/       # ReDoc
GET /api/schema/  # OpenAPI 3 スキーマ (YAML/JSON)
```

### チケット画像生成

```
GET /api/ext/v1/ticket/image/<nft_origin>
```

ベースAPIからNFT情報を取得し、チケット画像（PNG）を生成して返却します。

**認証**: セッション認証が必要

### チェックイン

```
GET /api/ext/v1/ticket/checkin?token=<token>
POST /api/ext/v1/ticket/checkin
```

QRコードから取得したトークンでチェックインを実行します。

**認証**: セッション認証が必要

## セッション共有設定

### 方法A: 同じドメインで動作（推奨）

ベースAPIと拡張APIを同じドメインで動作させます。セッションクッキーが自動的に共有されます。

```
api.example.com/api/v1/      → ベースAPI
api.example.com/api/ext/v1/ → 拡張API
```

### 方法B: 共有セッションストア

異なるドメインで動作する場合、Redis等の共有セッションストアを使用します。

```python
# settings.py
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',
    }
}
```

## 開発

### ローカル開発環境（venv）

```bash
# 仮想環境の作成（Dockerと共通の依存を使用）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# または
.venv\Scripts\activate  # Windows

# 依存関係のインストール
pip install -r app/requirements.txt

# データベースマイグレーション
python app/manage.py migrate

# 開発サーバーの起動
python app/manage.py runserver 8001
```

Ansible経由で準備する場合は `tools/install_django.yml` が `.venv` を作成し、
`app/requirements.txt` をインストールします。

### WSL での開発（Windows）

WSL の Ubuntu で Docker 起動や環境構築、`BASE_API_URL` 疎通確認の手順は **`documents/001_Setup_v1_start.md`** を参照してください。疎通確認には `python manage.py check_base_api`（オプション: `--insecure`）を使用します。

## 注意事項

1. **ポート競合**: BETAWALLET-DEVと同時に起動する場合、ポート番号が重複しないことを確認してください。
2. **セッション共有**: ベースAPIとセッションを共有する場合、同じドメインまたは共有ストアが必要です。
3. **データベース**: デフォルトは **SQLite**（`app/db.sqlite3`）。`.env` の `USE_SQLITE=True` で明示可能。PostgreSQL を使う場合は `USE_SQLITE` を無効にし、データディレクトリは `/mnt/lib/ticket_postgresql` 等にマウントできます。
4. **環境変数**: `.env`ファイルはgitignoreに追加してください。

## トラブルシューティング

### データベース接続エラー

- **SQLite 利用時**（`USE_SQLITE=True`）: `app/db.sqlite3` が作成されているか確認。未作成なら `python manage.py migrate` を実行。
- **PostgreSQL 利用時**: PostgreSQL コンテナが起動しているか確認（`docker compose ps`）。環境変数 `SQL_HOST` が `ticket_db` 等に設定されているか確認。

### セッション認証エラー

- ベースAPIと拡張APIが同じドメインで動作しているか確認
- セッションクッキーが正しく転送されているか確認

### ベースAPI接続エラー

- 環境変数`BASE_API_URL`が正しく設定されているか確認
- ベースAPIが起動しているか確認

### Git の `commit` で `unknown option 'trailer'` が出る場合

WSL などで Git 2.25 系を使っていると、エディタ経由で `git commit` を実行したときに `--trailer` オプションが渡され、エラーになることがあります。

**対処法（いずれか）:**

- ターミナルでコミットするときは、システムの git を直接使う:
  ```bash
  /usr/bin/git add -A && /usr/bin/git commit -m "メッセージ"
  ```
- 根本対応: Git を 2.29 以上にアップデートする（例: `sudo apt install git` で最新版を入れる）。

## ライセンス

このプロジェクトはBETAWALLET-DEVの拡張機能として開発されています。

