# チケットシステム マイクロサービス

このプロジェクトは、BETAWALLET-DEVのベースAPIを拡張する独立したマイクロサービスです。チケットNFTの画像生成とチェックイン処理を提供します。

## 概要

- **ベースAPI**: betawallet-dev（変更なし）
- **拡張API**: ticket_system（このプロジェクト）
- **認証**: セッション認証（ベースAPIと共有）
- **データベース**: PostgreSQL

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
- `ticket_web`: Djangoアプリケーション（ポート: 8001）
- `ticket_nginx`: Nginxリバースプロキシ（ポート: 1338, 5443）
- `ticket_db`: PostgreSQLデータベース（ポート: 5433）

### ポート番号（BETAWALLET-DEVと重複回避）
- `8001`: Djangoアプリケーション（BETAWALLET-DEVの`8000`に対応）
- `1338`: Nginx HTTP（BETAWALLET-DEVの`1337`に対応）
- `5443`: Nginx HTTPS（BETAWALLET-DEVの`443`に対応）
- `5433`: PostgreSQL（BETAWALLET-DEVの`5432`に対応）

## セットアップ

### 1. 環境変数の設定

`.env.example`をコピーして`.env`を作成し、必要な値を設定してください。

```bash
cp .env.example .env
```

主な設定項目:
- `SECRET_KEY`: Djangoのシークレットキー
- `SQL_*`: PostgreSQLの接続情報
- `BASE_API_URL`: ベースAPI（betawallet-dev）のURL
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

## APIエンドポイント

### Swagger / API仕様

```
GET /swagger/
GET /redoc/
GET /swagger.json
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

## 注意事項

1. **ポート競合**: BETAWALLET-DEVと同時に起動する場合、ポート番号が重複しないことを確認してください。
2. **セッション共有**: ベースAPIとセッションを共有する場合、同じドメインまたは共有ストアが必要です。
3. **データベース**: PostgreSQLのデータディレクトリは`/mnt/lib/ticket_postgresql`にマウントされます。
4. **環境変数**: `.env`ファイルはgitignoreに追加してください。

## トラブルシューティング

### データベース接続エラー

- PostgreSQLコンテナが起動しているか確認: `docker compose ps`
- 環境変数`SQL_HOST`が`ticket_db`に設定されているか確認

### セッション認証エラー

- ベースAPIと拡張APIが同じドメインで動作しているか確認
- セッションクッキーが正しく転送されているか確認

### ベースAPI接続エラー

- 環境変数`BASE_API_URL`が正しく設定されているか確認
- ベースAPIが起動しているか確認

## ライセンス

このプロジェクトはBETAWALLET-DEVの拡張機能として開発されています。

