# 007 セッション仕様

チケット拡張API（ticket_system）におけるセッションとベースAPI（betawallet-dev 等）認証の扱いをまとめる。

## 1. 概要

- **拡張API**: ticket_system（例: `https://ticket.buxbit.net`）。チケット画像・チェックイン・NFT作成などを行う。
- **ベースAPI**: betawallet-dev 等（例: `https://linode.buxbit.net`）。認証・ユーザー情報・NFT メタデータなどを提供する。

拡張APIは「自分専用のユーザーテーブル」を持たず、認証はベースAPIのセッションに依存する。そのため次の2つを組み合わせて運用している。

| 種類 | 説明 |
|------|------|
| **Django セッション** | 拡張API側のセッション（DB 保存）。ベースAPIから受け取ったクッキー値やユーザー情報を保持する。 |
| **ベースAPI用クッキー** | ベースAPIが発行する `sessionid` / `csrftoken`。拡張APIがベースAPIを呼ぶ際に必ず付与する。 |

クライアント（ブラウザ等）には、ベースAPIと共通で使えるよう `sessionid` / `csrftoken` を Cookie で返す（クロスサブドメイン用の設定あり）。

## 2. Django セッション（拡張API側）

### 2.1 設定（settings.py）

- **エンジン**: `django.contrib.sessions.backends.db`（DB 保存）
- **Cookie 名**: `sessionid`
- **有効期間**: `SESSION_COOKIE_AGE = 1209600`（2週間）
- **その他**: `SESSION_SAVE_EVERY_REQUEST = True`、HttpOnly / Secure / SameSite は環境に応じて設定。

### 2.2 保存するデータ

拡張APIは Django セッションに次のキーを保存する。

| キー | 設定タイミング | 用途 |
|------|----------------|------|
| `base_api_authenticated` | 拡張API経由ログイン成功時 | 認証済みフラグ |
| `base_api_user_info` | 同上 | ベースAPIのユーザー情報（管理者判定など） |
| `base_api_cookies` | 同上 | ベースAPIの `sessionid` / `csrftoken` の値の辞書 |

ログアウト時（`/accounts/logout/` または `GET /api/ext/v1/auth/logout`）は、上記を削除するかセッション全体を flush する。

## 3. ベースAPI用クッキーの取得順（重要）

認証が必要な処理（`/auth/user` プロキシ、`/ticket/create`、`/ticket/image/<nft_origin>`、`/ticket/checkin`）では、**ベースAPIに送るクッキー**を次の順で決める。

1. **Django セッションの `base_api_cookies`**  
   拡張API経由でログインしたときに保存した `sessionid` / `csrftoken` を優先して使用する。
2. **リクエストの Cookie ヘッダー**  
   `request.COOKIES` の `sessionid` / `csrftoken` をフォールバックとして使用する。

このため、「拡張APIにログインしたあと」は、ブラウザが Cookie を送らないケース（別オリジンやツールの都合など）でも、Django セッションに `base_api_cookies` があればベースAPI呼び出しが成功する。  
実装上の共通処理は次のとおり。

- **プロキシ系**（`/auth/user`, `/auth/logout`）: `_get_proxy_cookies(request)` で上記順にクッキーを取得し、ベースAPIへ転送。
- **チケット系**（create / image / checkin）: 各ビューの `_extract_session_cookies(request)` で同様の順序でクッキーを取得し、ベースAPIクライアントに渡す。

## 4. ログインの流れ

### 4.1 拡張API経由（POST /api/ext/v1/auth/login）

1. クライアントが拡張APIに `username` / `password` を送る。
2. 拡張APIがベースAPIの `/api/v1/auth/login` を呼ぶ。
3. ベースAPIが 200 と Set-Cookie（`sessionid`, `csrftoken`）を返す。
4. 拡張APIは次を行う。
   - Django セッションに `base_api_authenticated` / `base_api_user_info` / `base_api_cookies` を保存。
   - ベースAPIの Set-Cookie をそのままクライアントに転送（`_copy_response_cookies`）。  
     `SESSION_COOKIE_DOMAIN` が設定されていれば、`sessionid` / `csrftoken` はそのドメインで設定し、サブドメイン間で共有する。

クライアントは以降、同じ Cookie で拡張API・ベースAPIの両方に認証付きでアクセスできる（ドメイン設定が同じ場合）。

### 4.2 HTML フォーム経由（POST /accounts/login/）

1. クライアントが拡張APIの `/accounts/login/` にフォームで `username` / `password` を送る。
2. 拡張APIがベースAPIの `/api/v1/auth/login` を呼ぶ。
3. 成功時、ベースAPIの Set-Cookie をクライアントに転送しつつ、Django セッションに `base_api_user_info` / `base_api_authenticated` のみ保存する。**`base_api_cookies` はこの経路では保存しない**ため、以降のベースAPI呼び出しではクライアントが送る Cookie（`request.COOKIES`）に依存する。

## 5. ログアウトの流れ

### 5.1 拡張API経由（GET /api/ext/v1/auth/logout）

1. 拡張APIが `_get_proxy_cookies(request)` でクッキーを取得し、ベースAPIの `/api/v1/auth/logout` に転送。
2. ベースAPIが 200 または 401 を返す。
3. 拡張APIは **200 でも 401 でも** Django セッションの `base_api_authenticated` / `base_api_user_info` / `base_api_cookies` を削除。
4. ベースAPIが 401（未ログイン）の場合は、拡張APIは **200** で `{"message": "Already logged out"}` を返す（冪等）。

### 5.2 HTML 経由（GET/POST /accounts/logout/）

1. 拡張APIがリクエストの Cookie を使ってベースAPIの `/api/v1/auth/logout` を呼ぶ。
2. Django セッションを flush。
3. クライアントへのレスポンスで `sessionid` / `csrftoken` を削除（`SESSION_COOKIE_DOMAIN` があればそのドメイン指定で削除）。

## 6. クロスサブドメイン（Cookie 共有）

ベースAPIと拡張APIを別サブドメイン（例: `linode.buxbit.net` と `ticket.buxbit.net`）で運用する場合、次の設定で Cookie を共有する。

| 設定 | 説明 | 例 |
|------|------|-----|
| `SESSION_COOKIE_DOMAIN` | セッションCookie のドメイン | `.buxbit.net` |
| `CSRF_COOKIE_DOMAIN` | CSRF Cookie のドメイン | `.buxbit.net` |

拡張APIのレスポンスでベースAPIから受け取った `sessionid` / `csrftoken` を `_copy_response_cookies` により設定する際、`SESSION_COOKIE_DOMAIN` が指定されていればそのドメインで設定するため、同一親ドメインのサブドメイン間で Cookie が共有される。

## 7. 認証エラー時のレスポンス

認証情報（Cookie または Django セッションの `base_api_cookies`）がない場合、次のエンドポイントは拡張API側で **401** を返し、Body に以下を返す。

- `{"detail": "Authentication credentials were not provided."}`

対象例: `/api/ext/v1/auth/user`, `/api/ext/v1/ticket/create`, `/api/ext/v1/ticket/image/<nft_origin>`, `/api/ext/v1/ticket/checkin`（GET/POST）。

ベースAPIに転送した結果の 403 をそのまま返すのではなく、拡張APIで「認証未提供」と判断した場合はこの形式で統一している。

## 8. 設定一覧（環境変数・settings）

| 設定 | 用途 | 例 |
|------|------|-----|
| `SESSION_COOKIE_NAME` | セッションCookie 名 | `sessionid` |
| `SESSION_COOKIE_AGE` | 有効秒数 | `1209600`（2週間） |
| `SESSION_COOKIE_DOMAIN` | サブドメイン共有用 | `.buxbit.net` または未設定 |
| `SESSION_COOKIE_SECURE` | HTTPS のみ送信 | 本番 `True` |
| `SESSION_COOKIE_HTTPONLY` | JS からアクセス不可 | `True` |
| `SESSION_COOKIE_SAMESITE` | CSRF 軽減 | `Lax` |
| `SESSION_SAVE_EVERY_REQUEST` | 毎リクエストで保存 | `True` |
| `SESSION_ENGINE` | 保存先 | `django.contrib.sessions.backends.db` |
| `CSRF_TRUSTED_ORIGINS` | CSRF 許可オリジン | 拡張API・ベースAPIの URL |
| `CSRF_COOKIE_DOMAIN` | CSRF Cookie ドメイン | `.buxbit.net` または未設定 |

以上が、拡張APIにおけるセッションとベースAPI認証の仕様である。
