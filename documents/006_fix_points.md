# Swagger UI ログイン/ログアウト機能 修正ポイント

## 概要

`ticket_system`のSwagger UIでベースAPI（`betawallet-dev`）経由のログイン/ログアウト機能を実装する際に発生した問題と、その解決策をまとめます。

## 環境

- **ticket_system**: 拡張APIサーバー（`https://ticket.buxbit.net`）
- **betawallet-dev**: ベースAPIサーバー（`https://linode.buxbit.net`）
- **共有ドメイン**: `.buxbit.net`（サブドメイン間でセッションを共有）

---

## 修正ポイント一覧

### 1. カスタムSwagger UIテンプレートの作成

**問題**: デフォルトの`drf-yasg`テンプレートでは、`apiLogin()`関数がベースAPIのエンドポイントを呼び出すように設定されていない。

**解決策**: `betawallet-dev`と同様のカスタムテンプレートを作成。

**ファイル**: `app/ticket_service/templates/drf-yasg/swagger-ui.html`

```javascript
function apiLogin() {
    var username = window.prompt('Username:');
    if (username === null) { return; }
    var password = window.prompt('Password:');
    if (password === null) { return; }
    var token = getCookie('csrftoken');
    fetch('/api/ext/v1/auth/login', {  // 拡張APIのログインエンドポイント
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': token || ''
        },
        credentials: 'include',
        body: JSON.stringify({ username: username, password: password })
    }).then(function(resp) {
        if (resp.ok) { window.location.reload(); return; }
        // エラー処理
    });
}
```

### 2. INSTALLED_APPSの順序変更

**問題**: `drf_yasg`が`ticket_service`より前に登録されていると、カスタムテンプレートが読み込まれない。

**解決策**: `ticket_service`を`drf_yasg`より前に配置。

**ファイル**: `app/ticket_system/settings.py`

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'ticket_service',  # Must be before drf_yasg to override templates
    'drf_yasg',
]
```

### 3. CSRF免除の認証クラス追加

**問題**: DRFのデフォルト`SessionAuthentication`はCSRFチェックを行うため、APIログイン/ログアウトが失敗する。

**解決策**: CSRF検証をスキップする認証クラスを作成し、認証プロキシAPIに適用。

**ファイル**: `app/ticket_service/views.py`

```python
class CsrfExemptSessionAuthentication(SessionAuthentication):
    """CSRF検証をスキップするSessionAuthentication"""
    def enforce_csrf(self, request):
        return  # CSRFチェックをスキップ


class AuthLoginProxyAPIView(BaseAPIProxyMixin, APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    # ...

class AuthLogoutProxyAPIView(BaseAPIProxyMixin, APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    # ...

class AuthUserProxyAPIView(BaseAPIProxyMixin, APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    # ...
```

### 4. クッキードメインの設定（.envから読み込み）

**問題**: `sessionid`と`csrftoken`のクッキーが`ticket.buxbit.net`のみに設定され、サブドメイン間で共有されない。

**解決策**: `.env`から`SESSION_COOKIE_DOMAIN`を読み込み、`.buxbit.net`ドメインでクッキーを設定。

**ファイル**: `.env`

```env
# Cookie Settings for cross-subdomain sharing
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_DOMAIN=.buxbit.net
CSRF_COOKIE_DOMAIN=.buxbit.net
```

**ファイル**: `app/ticket_system/settings.py`

```python
SESSION_COOKIE_DOMAIN = os.environ.get('SESSION_COOKIE_DOMAIN', None)
CSRF_COOKIE_DOMAIN = os.environ.get('CSRF_COOKIE_DOMAIN', None)
```

### 5. レスポンスクッキーのドメイン設定

**問題**: ベースAPIから返されたクッキーをそのまま設定すると、ドメインが異なるためブラウザで認識されない。

**解決策**: `_copy_response_cookies()`関数で`sessionid`と`csrftoken`に共有ドメインを設定。

**ファイル**: `app/ticket_service/views.py`

```python
def _copy_response_cookies(source_response: requests.Response, target_response: HttpResponse) -> None:
    shared_cookie_domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    cookie_secure = getattr(settings, 'SESSION_COOKIE_SECURE', True)
    cookie_samesite = getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax')
    
    for cookie in source_response.cookies:
        # sessionid と csrftoken は SESSION_COOKIE_DOMAIN で共有
        if cookie.name in ('sessionid', 'csrftoken') and shared_cookie_domain:
            cookie_domain = shared_cookie_domain
        else:
            cookie_domain = cookie.domain if cookie.domain_specified else None
        target_response.set_cookie(
            cookie.name,
            cookie.value,
            # ...
            domain=cookie_domain,
            secure=cookie_secure,
            # ...
        )
```

### 6. SESSION_COOKIE_SECURE=True の設定

**問題**: HTTPS環境で`Secure`フラグがないクッキーはブラウザで設定されない。

**解決策**: `.env`で`SESSION_COOKIE_SECURE=True`を設定。

```env
SESSION_COOKIE_SECURE=True
```

### 7. Djangoセッションへの認証情報保存

**問題**: ベースAPIでログインしても、`ticket_system`のDjangoは`request.user.is_authenticated`を`False`と認識する。

**解決策**: ログイン成功時にDjangoセッションに認証情報を保存。

**ファイル**: `app/ticket_service/views.py`

```python
class AuthLoginProxyAPIView(BaseAPIProxyMixin, APIView):
    def post(self, request):
        response = self._proxy_request(request, "POST", "/api/v1/auth/login")
        
        # ログイン成功時にDjangoセッションにも情報を保存
        if response.status_code == 200:
            try:
                data = json.loads(response.content)
                if data.get('status') == 'success' or data.get('user'):
                    request.session['base_api_authenticated'] = True
                    request.session['base_api_user_info'] = data.get('user', {})
                    request.session.save()
            except Exception as e:
                logger.warning(f"Failed to save session info after login: {e}")
        
        return response
```

### 8. Swagger UIテンプレートでのセッションチェック

**問題**: Swagger UIが`request.user.is_authenticated`のみをチェックしており、ベースAPI経由のログインを認識しない。

**解決策**: `request.session.base_api_authenticated`もチェックするようにテンプレートを修正。

**ファイル**: `app/ticket_service/templates/drf-yasg/swagger-ui.html`

```django
{% if request.user.is_authenticated or request.session.base_api_authenticated %}
    <div class="hello">
        <span class="django-session">Django</span> <span
            class="label label-primary">{% if request.user.is_authenticated %}{{ request.user }}{% else %}{{ request.session.base_api_user_info.username|default:"API User" }}{% endif %}</span>
    </div>
{% endif %}

{% if request.user.is_authenticated or request.session.base_api_authenticated %}
    <a id="auth" class="header__btn" href="{{ LOGOUT_URL }}?next={{ request.path }}">
        Django Logout
    </a>
{% else %}
    <button id="auth" class="header__btn" type="button" onclick="apiLogin()">
        API Login
    </button>
{% endif %}
```

### 9. ログアウト時のセッションクリアとクッキー削除

**問題**: ログアウト時にDjangoセッションがクリアされず、クッキーも正しく削除されない。

**解決策**: `LogoutRedirectView`でセッションをフラッシュし、ドメインを指定してクッキーを削除。

**ファイル**: `app/ticket_service/views.py`

```python
class LogoutRedirectView(View):
    def get(self, request):
        # ベースAPI経由でログアウト
        # ...
        
        # Djangoセッションの認証情報をクリア
        try:
            request.session.pop('base_api_authenticated', None)
            request.session.pop('base_api_user_info', None)
            request.session.flush()  # セッション全体をクリア
        except Exception as e:
            logger.warning(f"Failed to clear session: {e}")
        
        response = redirect(next_url)
        
        # クッキーを削除（ドメインを指定）
        shared_cookie_domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
        response.delete_cookie('sessionid', domain=shared_cookie_domain)
        response.delete_cookie('csrftoken', domain=shared_cookie_domain)
        # ドメインなしでも削除（念のため）
        response.delete_cookie('sessionid')
        response.delete_cookie('csrftoken')
        return response
```

### 10. ログアウトプロキシAPIでのセッションクリア

**問題**: Swagger UIの「Try it out」機能でログアウトAPIを呼び出した場合、Djangoセッションがクリアされない。

**解決策**: `AuthLogoutProxyAPIView`でもセッションをクリア。

**ファイル**: `app/ticket_service/views.py`

```python
class AuthLogoutProxyAPIView(BaseAPIProxyMixin, APIView):
    def get(self, request):
        response = self._proxy_request(request, "GET", "/api/v1/auth/logout")
        
        # ログアウト時にDjangoセッションもクリア
        if response.status_code == 200:
            try:
                request.session.pop('base_api_authenticated', None)
                request.session.pop('base_api_user_info', None)
                request.session.save()
            except Exception as e:
                logger.warning(f"Failed to clear session info after logout: {e}")
        
        return response
```

---

## 設定ファイルのまとめ

### .env

```env
# Cookie Settings for cross-subdomain sharing
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_DOMAIN=.buxbit.net
CSRF_COOKIE_DOMAIN=.buxbit.net
```

### app/ticket_system/settings.py

```python
# Session settings
SESSION_COOKIE_DOMAIN = os.environ.get('SESSION_COOKIE_DOMAIN', None)
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True') == 'True'

# CSRF settings
CSRF_COOKIE_DOMAIN = os.environ.get('CSRF_COOKIE_DOMAIN', None)
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'True') == 'True'

# Swagger settings
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {},
    'LOGOUT_URL': '/accounts/logout/',
    'USE_SESSION_AUTH': True,
}

LOGIN_URL = '/accounts/login/'
```

---

## 注意事項

1. **ローカル開発環境**: `SESSION_COOKIE_DOMAIN`を設定しない（または空にする）ことで、デフォルトの動作になります。

2. **HTTPS必須**: 本番環境では`SESSION_COOKIE_SECURE=True`が必要です。HTTPでは`Secure`フラグ付きのクッキーは設定されません。

3. **サブドメイン共有**: `.buxbit.net`のように先頭にドットを付けることで、すべてのサブドメインでクッキーが共有されます。

4. **Swagger UIの制限**: 「Try it out」機能でAPIを呼び出す場合、クッキーが正しく送信されない場合があります。「Django Logout」リンクを使用することを推奨します。

