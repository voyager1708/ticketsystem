# ハンズオンで利用する API（Ordinal-X / ベースAPI）

この資料は、`handson/v1-start` でチケットシステムが**呼び出す先**となる API（ベースAPI）の説明です。  
ハンズオンで「どの外部APIを、いつ使うか」を把握するときに参照してください。

## 読み方

- 必須3API（アカウント作成・チケット生成・チェックイン）を実装する際に、**ベースAPIのどのエンドポイントが使われるか**を確認する
- 認証や環境変数で詰まったときは `020_swagger_auth_troubleshooting.md` と `028_session_auth_reference.md` を併用する
- 実装詳細は `022_architecture_reference.md` および `app/ticket_service/services/base_api_client.py` を参照

---

## 1. 概要

### ベースAPIとは

- **役割**: ウォレット・NFT の作成・取得・メタデータ更新、認証（サインアップ・ログイン）を提供する API サーバー
- **本ハンズオンでの呼び名**: ベースAPI / Ordinal-X 関連 API
- **ticket_system との関係**: ticket_system（拡張API）は、チケット画像生成・チェックインなどの**チケット固有処理**を行い、NFT の作成・取得・更新は **ベースAPI を呼び出して**行う

### 通信の流れ（イメージ）

```
クライアント（Swagger/ブラウザ）
    → ticket_system（Django）
        → ベースAPI（Ordinal-X）
```

- クライアントは ticket_system にだけリクエストを送る
- ticket_system が、必要に応じてベースAPI に **セッションクッキーを付けて** 転送・中継する

---

## 2. 環境・認証

### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `BASE_API_URL` | ベースAPI のベース URL（末尾スラッシュなし） | `https://api.example.com` または `http://localhost:8000` |

- 未設定だと `BaseAPIClient` 初期化時にエラーになる
- 接続確認: `python manage.py check_base_api`（`--insecure` で SSL エラーを無視可能）

### 認証（セッションクッキー）

- ベースAPI は **セッションクッキー**（`sessionid`, `csrftoken` など）で認証する
- ユーザーが ticket_system の **`POST /api/ext/v1/auth/login`** でログインすると、ticket_system がベースAPI にログインし、返ってきたクッキーを **Django セッションに保存**（`base_api_cookies`）する
- チケット作成・チェックイン・画像取得などでは、この保存済みクッキーをベースAPI に付けて呼び出す  
  → 詳しくは `028_session_auth_reference.md`

---

## 3. ハンズオンで利用するベースAPI一覧

以下は、ticket_system のコード（`base_api_client.py` および views）から**実際に呼ばれている**エンドポイントです。

### 3.1 認証

| メソッド | パス | 用途（ハンズオンでの使われ方） |
|----------|------|--------------------------------|
| POST | `/api/v1/auth/sign-up` | アカウント作成。`POST /api/accounts/create` または `POST /api/ext/v1/auth/sign-up` が中継 |
| POST | `/api/v1/auth/login` | ログイン。`POST /api/ext/v1/auth/login` が中継し、返却クッキーをセッションに保存 |
| GET  | `/api/v1/auth/logout` | ログアウト。拡張API の logout が中継 |
| GET  | `/api/v1/user/info`   | ログインユーザー情報。プロキシや権限判定で利用 |

### 3.2 NFT

| メソッド | パス | 用途（ハンズオンでの使われ方） |
|----------|------|--------------------------------|
| POST | `/api/v1/nft/create` | チケットNFT作成（Step 3）。画像 + メタデータを送り、NFT を発行する |
| GET  | `/api/v1/nft/data/{nft_origin}` | NFT データ取得（画像配布・表示）。`?data_format=base64` で JSON 取得 |
| GET  | `/api/v1/nft/meta/{nft_origin}` | メタデータ取得。チェックイン状態の参照など |
| PATCH| `/api/v1/nft/meta/{nft_origin}` | メタデータ更新。チェックイン済みフラグの更新（Step 4）に利用 |
| GET  | `/api/v1/user/nfts/info` | ユーザー所持 NFT 一覧。特定 NFT の取得や権限判定に利用 |

### 3.3 その他（発展で利用）

| メソッド | パス | 用途 |
|----------|------|------|
| POST | `/api/v1/nft/create` | チェックイン報酬 NFT 作成（`create_reward_nft`） |
| GET  | `/api/v1/admin/nft/data/{nft_origin}` | 管理者用 NFT データ取得（認証不要） |

---

## 4. 必須3APIとベースAPIの対応

| Step | 拡張API（ticket_system） | 利用するベースAPI |
|------|---------------------------|-------------------|
| Step 2 アカウント作成 | `POST /api/accounts/create` | `POST /api/v1/auth/sign-up` に転送 |
| Step 3 チケット生成 | `POST /tickets/create`（実パス: `/api/ext/v1/ticket/create`） | 画像生成後、`POST /api/v1/nft/create` で NFT 作成 |
| Step 4 チェックイン | `POST /tickets/{id}/checkin`（実パス: `/api/ext/v1/ticket/checkin`） | `GET /api/v1/nft/meta/{nft_origin}` で状態取得、`PATCH /api/v1/nft/meta/{nft_origin}` で更新 |

---

## 5. 主要パラメータ（参照用）

### POST /api/v1/nft/create（チケットNFT作成で使用）

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| file | File | Yes | NFT 用画像（例: チケット PNG） |
| app | string | Yes | アプリ名（例: "Ticket System"） |
| name | string | Yes | NFT 名 |
| additional_info | string | No | JSON 文字列のメタデータ（subTypeData 等に格納） |
| recipient_paymail | string | No | 受領者 paymail（省略時は自分） |

- 認証: セッションクッキー必須。CSRF のため `X-CSRFToken` と `Referer` を付与する実装になっている

---

## 6. 関連ドキュメント

| 資料 | 内容 |
|------|------|
| `011_goal_steps_ai_pairing.md` | 実行ステップと必須3API |
| `021_ticket_create_api_spec.md` | チケット作成API仕様（ベースAPIとの整合性含む） |
| `022_architecture_reference.md` | 拡張API・ベースAPI のアーキテクチャ |
| `028_session_auth_reference.md` | セッション認証とベースAPI クッキーの扱い |
| `020_swagger_auth_troubleshooting.md` | Swagger から認証付きで試すときのトラブルシュート |
