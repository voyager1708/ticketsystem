import logging
import requests
from django import forms
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from ticket_service.models import Account
from ticket_service.services.base_api_client import BaseAPIClient

logger = logging.getLogger('ticket_service.views')

# 認証未提供時の共通メッセージ（DRF と同様）
UNAUTHENTICATED_DETAIL = "Authentication credentials were not provided."


def _has_session_credentials(request) -> bool:
    """リクエストにベースAPI用のセッション（Cookie または Django セッション）があるか"""
    if request.COOKIES.get('sessionid'):
        return True
    if request.session.get('base_api_cookies'):
        return True
    return False


def _get_proxy_cookies(request) -> dict:
    """
    プロキシでベースAPIに送るクッキーを取得。
    Django セッションの base_api_cookies を優先し、
    なければ request.COOKIES の sessionid/csrftoken を使う。
    """
    base_api_cookies = request.session.get('base_api_cookies', {})
    if base_api_cookies:
        return base_api_cookies
    cookies = {}
    if request.COOKIES.get('sessionid'):
        cookies['sessionid'] = request.COOKIES.get('sessionid')
    if request.COOKIES.get('csrftoken'):
        cookies['csrftoken'] = request.COOKIES.get('csrftoken')
    return cookies


class LoginForm(forms.Form):
    username = forms.CharField(label='Username')
    password = forms.CharField(label='Password', widget=forms.PasswordInput)


class CustomLoginView(View):
    """HTMLフォームを表示するログインビュー（ベースAPI経由で認証）"""
    template_name = 'registration/login.html'

    def get(self, request):
        form = LoginForm()
        context = {"form": form, "next": request.GET.get('next', '')}
        return render(request, self.template_name, context)

    def post(self, request):
        # CSRFトークンのデバッグ
        csrf_token_from_post = request.POST.get('csrfmiddlewaretoken')
        csrf_token_from_cookie = request.COOKIES.get('csrftoken')
        logger.info(f"Login attempt - CSRF token from POST: {csrf_token_from_post[:20] if csrf_token_from_post else 'None'}...")
        logger.info(f"Login attempt - CSRF token from cookie: {csrf_token_from_cookie[:20] if csrf_token_from_cookie else 'None'}...")
        logger.info(f"Login attempt - All cookies: {list(request.COOKIES.keys())}")
        logger.info(f"Login attempt - POST data keys: {list(request.POST.keys())}")
        
        form = LoginForm(request.POST)
        next_url = request.POST.get('next') or getattr(settings, 'LOGIN_REDIRECT_URL', '/') or '/'
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "next": next_url})

        username = form.cleaned_data['username']
        password = form.cleaned_data['password']

        # ベースAPI経由でログイン
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/login"
        
        session = requests.Session()
        # CSRFトークンを取得
        csrf_token = request.COOKIES.get('csrftoken')
        if csrf_token:
            session.cookies.set('csrftoken', csrf_token)
        
        headers = {'Content-Type': 'application/json'}
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        
        try:
            response = session.post(
                url,
                json={'username': username, 'password': password},
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                # セッションクッキーを辞書に保存（後でユーザー情報取得に使用）
                session_cookies = {}
                for cookie in response.cookies:
                    if cookie.name in ('sessionid', 'csrftoken'):
                        session_cookies[cookie.name] = cookie.value
                
                # ベースAPIのユーザー情報を取得してセッションに保存（オプション）
                # 注意: ticket_systemにはユーザーモデルがないため、セッションにユーザー情報を保存するだけ
                if session_cookies.get('sessionid'):
                    try:
                        user_info = api_client.get_user_info(session_cookies)
                        if user_info:
                            # ユーザー情報をセッションに保存（認証状態の確認用）
                            request.session['base_api_user_info'] = user_info
                            request.session['base_api_authenticated'] = True
                    except Exception as e:
                        logger.warning(f"Failed to get user info after login: {e}")
                
                # セッションクッキーをコピー（SESSION_COOKIE_DOMAINで共有できるように設定）
                # ベースAPIと同じようにシンプルにredirect()を使用
                django_response = redirect(next_url)
                
                # settings から共有ドメイン設定を取得
                shared_cookie_domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
                cookie_secure = getattr(settings, 'SESSION_COOKIE_SECURE', True)
                cookie_samesite = getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax')
                
                # セッションクッキーを設定
                for cookie in response.cookies:
                    # セッションクッキー（sessionid）とCSRFトークン（csrftoken）を共有ドメインで設定
                    if cookie.name in ('sessionid', 'csrftoken') and shared_cookie_domain:
                        cookie_domain = shared_cookie_domain
                    else:
                        # その他のクッキーは元のドメイン設定を維持
                        cookie_domain = cookie.domain if cookie.domain_specified else None
                    
                    django_response.set_cookie(
                        cookie.name,
                        cookie.value,
                        expires=cookie.expires,
                        path=cookie.path if cookie.path_specified else '/',
                        domain=cookie_domain,
                        secure=cookie_secure,
                        httponly=bool(cookie._rest.get("HttpOnly") or cookie._rest.get("httponly")),
                        samesite=cookie._rest.get("SameSite") or cookie._rest.get("samesite") or cookie_samesite,
                    )
                
                return django_response
            else:
                # エラーメッセージを取得
                try:
                    data = response.json()
                    error_message = data.get('message') or data.get('error') or 'Login failed.'
                except:
                    error_message = 'Login failed.'
        except requests.RequestException as e:
            logger.error(f"Login request failed: {e}")
            error_message = 'Login request failed. Please try again.'

        form.add_error(None, error_message)
        return render(request, self.template_name, {"form": form, "next": next_url})


class LogoutRedirectView(View):
    """ログアウトビュー"""
    def get(self, request):
        # ベースAPI経由でログアウト
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/logout"
        
        session = requests.Session()
        for cookie_name, cookie_value in request.COOKIES.items():
            session.cookies.set(cookie_name, cookie_value)
        
        try:
            session.get(url, timeout=10)
        except requests.RequestException as e:
            logger.error(f"Logout request failed: {e}")
        
        # Djangoセッションの認証情報をクリア
        try:
            request.session.pop('base_api_authenticated', None)
            request.session.pop('base_api_user_info', None)
            request.session.flush()  # セッション全体をクリア
        except Exception as e:
            logger.warning(f"Failed to clear session: {e}")
        
        # ローカルのセッションもクリア
        next_url = request.GET.get('next') or getattr(settings, 'LOGOUT_REDIRECT_URL', '/') or '/'
        response = redirect(next_url)
        
        # クッキーを削除（ドメインを指定）
        shared_cookie_domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
        response.delete_cookie('sessionid', domain=shared_cookie_domain)
        response.delete_cookie('csrftoken', domain=shared_cookie_domain)
        # ドメインなしでも削除（念のため）
        response.delete_cookie('sessionid')
        response.delete_cookie('csrftoken')
        return response

    def post(self, request):
        return self.get(request)


def _copy_response_cookies(source_response: requests.Response, target_response: HttpResponse) -> None:
    """Copy cookies from upstream response to Django response.
    
    Uses SESSION_COOKIE_DOMAIN from settings for sessionid/csrftoken cookies
    to enable cross-subdomain sharing.
    """
    shared_cookie_domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    cookie_secure = getattr(settings, 'SESSION_COOKIE_SECURE', True)
    cookie_samesite = getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax')
    
    for cookie in source_response.cookies:
        rest = cookie._rest or {}
        same_site = rest.get("SameSite") or rest.get("samesite") or cookie_samesite
        # sessionid と csrftoken は SESSION_COOKIE_DOMAIN で共有
        if cookie.name in ('sessionid', 'csrftoken') and shared_cookie_domain:
            cookie_domain = shared_cookie_domain
        else:
            cookie_domain = cookie.domain if cookie.domain_specified else None
        target_response.set_cookie(
            cookie.name,
            cookie.value,
            expires=cookie.expires,
            path=cookie.path if cookie.path_specified else '/',
            domain=cookie_domain,
            secure=cookie_secure,
            httponly=bool(rest.get("HttpOnly") or rest.get("httponly")),
            samesite=same_site,
        )


class BaseAPIProxyMixin:
    def _proxy_request(self, request, method: str, path: str) -> HttpResponse:
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}{path}"
        logger.info("Auth proxy: %s %s (verify=%s)", method, url, getattr(settings, "BASE_API_VERIFY_SSL", True))
        session = requests.Session()
        # /ticket/create と同様に Django セッションの base_api_cookies を優先してベースAPIに送る
        proxy_cookies = _get_proxy_cookies(request)
        logger.debug(f"Proxy request to {url}, cookies: {list(proxy_cookies.keys())}")
        for cookie_name, cookie_value in proxy_cookies.items():
            session.cookies.set(cookie_name, cookie_value)

        headers = {}
        csrf_token = proxy_cookies.get('csrftoken') or request.headers.get('X-CSRFToken')
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        if request.headers.get('Accept'):
            headers['Accept'] = request.headers.get('Accept')
        if request.content_type and "application/json" not in request.content_type:
            headers['Content-Type'] = request.content_type

        kwargs = {"headers": headers, "timeout": 15, "verify": getattr(settings, "BASE_API_VERIFY_SSL", True)}
        if request.query_params:
            kwargs["params"] = request.query_params
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            if request.content_type and "application/json" in request.content_type:
                kwargs["json"] = request.data
            else:
                kwargs["data"] = request.data

        try:
            upstream_response = session.request(method.upper(), url, **kwargs)
        except requests.RequestException as exc:
            logger.error("Auth proxy request failed: %s", exc)
            return JsonResponse({"error": "Upstream request failed"}, status=502)

        content_type = upstream_response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = upstream_response.json()
                response = JsonResponse(
                    payload,
                    status=upstream_response.status_code,
                    safe=isinstance(payload, dict),
                )
            except ValueError:
                response = HttpResponse(
                    upstream_response.content,
                    status=upstream_response.status_code,
                    content_type=content_type or None,
                )
        else:
            response = HttpResponse(
                upstream_response.content,
                status=upstream_response.status_code,
                content_type=content_type or None,
            )

        _copy_response_cookies(upstream_response, response)
        return response


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """CSRF検証をスキップするSessionAuthentication"""
    def enforce_csrf(self, request):
        return  # CSRFチェックをスキップ


class CsrfExemptSessionAuthExtension(OpenApiAuthenticationExtension):
    """drf-spectacular の警告解消: CsrfExemptSessionAuthentication をセッション認証として記載"""
    target_class = "ticket_service.views.CsrfExemptSessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": "Session authentication (CSRF exempt for proxy).",
        }


class AuthLoginProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのログインを中継"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login (proxy)",
        description="拡張API経由でベースAPIのログインを中継",
        tags=["auth"],
        request=inline_serializer(
            name="AuthLoginRequest",
            fields={
                "username": serializers.CharField(help_text="User's username"),
                "password": serializers.CharField(help_text="User's password"),
            },
        ),
        responses={
            200: inline_serializer(
                name="AuthLoginSuccess",
                fields={"message": serializers.CharField()},
            ),
            400: inline_serializer(
                name="AuthLoginBadRequest",
                fields={"error": serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        # ベースAPIにログインリクエストを送信
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/login"
        logger.info("Auth login proxy: sending POST to %s (verify=%s)", url, getattr(settings, "BASE_API_VERIFY_SSL", True))
        session = requests.Session()
        headers = {'Content-Type': 'application/json'}
        verify = getattr(settings, "BASE_API_VERIFY_SSL", True)
        try:
            upstream_response = session.post(url, json=request.data, headers=headers, timeout=15, verify=verify)
        except requests.RequestException as exc:
            logger.error("Auth proxy request failed: %s", exc)
            return JsonResponse({"error": "Upstream request failed"}, status=502)
        
        # レスポンスを作成
        content_type = upstream_response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = upstream_response.json()
                response = JsonResponse(
                    payload,
                    status=upstream_response.status_code,
                    safe=isinstance(payload, dict),
                )
            except ValueError:
                response = HttpResponse(
                    upstream_response.content,
                    status=upstream_response.status_code,
                    content_type=content_type or None,
                )
        else:
            response = HttpResponse(
                upstream_response.content,
                status=upstream_response.status_code,
                content_type=content_type or None,
            )
        
        # ログイン成功時にベースAPIのセッションクッキーをDjangoセッションに保存
        if upstream_response.status_code == 200:
            try:
                data = upstream_response.json()
                if data.get('status') == 'success' or data.get('user'):
                    request.session['base_api_authenticated'] = True
                    request.session['base_api_user_info'] = data.get('user', {})
                    
                    # ベースAPIのセッションクッキーを保存
                    base_api_cookies = {}
                    for cookie in upstream_response.cookies:
                        base_api_cookies[cookie.name] = cookie.value
                        logger.debug(f"Saving base API cookie: {cookie.name}")
                    request.session['base_api_cookies'] = base_api_cookies
                    request.session.save()
                    logger.info(f"Login successful, saved base API cookies: {list(base_api_cookies.keys())}")
            except Exception as e:
                logger.warning(f"Failed to save session info after login: {e}")
        
        # クッキーをレスポンスにコピー
        _copy_response_cookies(upstream_response, response)
        return response


class AuthSignUpProxyAPIView(APIView):
    """拡張API経由でベースAPIのサインアップ（ユーザー登録）を中継。BASE の /api/v1/auth/sign-up に合わせる。"""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Sign-up (proxy)",
        description="拡張API経由でベースAPIのユーザー登録を中継。username, email, password, group をベースAPIへ転送。",
        tags=["auth"],
        request=inline_serializer(
            name="AuthSignUpRequest",
            fields={
                "username": serializers.CharField(help_text="必須"),
                "email": serializers.EmailField(help_text="必須"),
                "password": serializers.CharField(help_text="必須", write_only=True),
                "group": serializers.CharField(help_text="必須", required=False, allow_blank=True),
            },
        ),
        responses={
            200: None,
            201: None,
            400: inline_serializer(
                name="AuthSignUpBadRequest",
                fields={"status": serializers.CharField(), "message": serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        if not request.data or not isinstance(request.data, dict):
            return Response(
                {"detail": "JSON body required. Send {\"username\", \"email\", \"password\", \"group\"} (group optional)."},
                status=400,
            )
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/sign-up"
        logger.info("Auth sign-up proxy: sending POST to %s (verify=%s)", url, getattr(settings, "BASE_API_VERIFY_SSL", True))
        session = requests.Session()
        headers = {"Content-Type": "application/json"}
        verify = getattr(settings, "BASE_API_VERIFY_SSL", True)
        try:
            upstream_response = session.post(url, json=request.data, headers=headers, timeout=15, verify=verify)
        except requests.RequestException as exc:
            logger.error("Auth sign-up proxy request failed: %s", exc)
            return JsonResponse({"error": "Upstream request failed"}, status=502)
        content_type = upstream_response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = upstream_response.json()
                return Response(payload, status=upstream_response.status_code)
            except ValueError:
                return HttpResponse(
                    upstream_response.content,
                    status=upstream_response.status_code,
                    content_type=content_type or None,
                )
        return HttpResponse(
            upstream_response.content,
            status=upstream_response.status_code,
            content_type=content_type or None,
        )


# --- ローカル + ベースAPI sign-up: POST /api/accounts/create ---


class AccountCreateSerializer(serializers.Serializer):
    """username, password, email 必須。group はベースAPI用（任意）。"""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField()
    group = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("username は必須です。")
        if Account.objects.filter(username=value.strip()).exists():
            raise serializers.ValidationError("この username は既に使われています。")
        return value.strip()

    def create(self, validated_data):
        account = Account(
            username=validated_data["username"],
            email=validated_data.get("email") or "",
        )
        account.set_password(validated_data["password"])
        account.save()
        return account


class AccountCreateAPIView(APIView):
    """
    POST /api/accounts/create: ローカルにユーザーを作成し、同時にベースAPIの sign-up に転送する。
    先にベースAPIで登録し、成功したらローカルに保存。ベースAPIが 400 の場合はローカルは作らない。
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]

    @extend_schema(
        summary="アカウント作成（ローカル + ベースAPI sign-up）",
        description="ベースAPIの sign-up に転送し、成功したらローカルにも Account を作成。username, email, password 必須。group は任意（ベースAPI用）。",
        tags=["accounts"],
        request=inline_serializer(
            name="AccountCreateRequest",
            fields={
                "username": serializers.CharField(help_text="必須"),
                "email": serializers.EmailField(help_text="必須"),
                "password": serializers.CharField(help_text="必須", write_only=True),
                "group": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={
            201: inline_serializer(
                name="AccountCreated",
                fields={
                    "id": serializers.IntegerField(),
                    "username": serializers.CharField(),
                },
            ),
            400: None,
            502: None,
        },
    )
    def post(self, request):
        if not request.data or not isinstance(request.data, dict):
            return Response(
                {"detail": "JSON body required. Send {\"username\", \"email\", \"password\", \"group\"} (group optional)."},
                status=400,
            )
        serializer = AccountCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        # 1) 先にベースAPIの sign-up に転送
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/sign-up"
        body = {
            "username": request.data.get("username", "").strip(),
            "email": request.data.get("email", "").strip(),
            "password": request.data.get("password", ""),
            "group": request.data.get("group", "").strip() or request.data.get("username", "").strip(),
        }
        logger.info("Account create: sending sign-up to %s", url)
        session = requests.Session()
        headers = {"Content-Type": "application/json"}
        verify = getattr(settings, "BASE_API_VERIFY_SSL", True)
        try:
            upstream_response = session.post(url, json=body, headers=headers, timeout=15, verify=verify)
        except requests.RequestException as exc:
            logger.error("Account create (base sign-up) failed: %s", exc)
            return JsonResponse({"error": "Upstream request failed"}, status=502)

        if upstream_response.status_code not in (200, 201):
            content_type = upstream_response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                try:
                    return Response(upstream_response.json(), status=upstream_response.status_code)
                except ValueError:
                    pass
            return HttpResponse(
                upstream_response.content,
                status=upstream_response.status_code,
                content_type=content_type or None,
            )

        # 2) ベースAPI成功時のみローカルに作成
        account = serializer.save()
        return Response(
            {"id": account.id, "username": account.username},
            status=201,
        )


class AuthLogoutProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのログアウトを中継"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Logout (proxy)",
        description="拡張API経由でベースAPIのログアウトを中継",
        tags=["auth"],
        responses={
            200: inline_serializer(
                name="AuthLogoutSuccess",
                fields={"message": serializers.CharField()},
            ),
            401: inline_serializer(
                name="AuthLogoutUnauthorized",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        response = self._proxy_request(request, "GET", "/api/v1/auth/logout")
        
        # ログアウト時にDjangoセッションもクリア（200 でも 401 でもクリアする）
        if response.status_code in (200, 401):
            try:
                request.session.pop('base_api_authenticated', None)
                request.session.pop('base_api_user_info', None)
                request.session.pop('base_api_cookies', None)
                request.session.save()
            except Exception as e:
                logger.warning(f"Failed to clear session info after logout: {e}")
        
        # ベースAPIが 401（未ログイン）を返しても、拡張API側はセッションを消して 200 を返す（冪等）
        if response.status_code == 401:
            return JsonResponse({"message": "Already logged out"}, status=200)
        
        return response


class AuthUserProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのユーザー情報を取得"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="User info (proxy)",
        description="拡張API経由でベースAPIのユーザー情報を取得",
        tags=["auth"],
        responses={
            200: None,
            401: inline_serializer(
                name="AuthUserUnauthorized",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        if not _has_session_credentials(request):
            return JsonResponse({"detail": UNAUTHENTICATED_DETAIL}, status=401)
        return self._proxy_request(request, "GET", "/api/v1/user/info")

