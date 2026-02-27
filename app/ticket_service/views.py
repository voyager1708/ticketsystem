import logging
import requests
from django import forms
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

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
                # betawallet-devと同じようにシンプルにredirect()を使用
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

        kwargs = {"headers": headers, "timeout": 15}
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


class AuthLoginProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのログインを中継"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Login (proxy)",
        operation_description="拡張API経由でベースAPIのログインを中継",
        tags=["auth"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "username": openapi.Schema(type=openapi.TYPE_STRING, description="User's username"),
                "password": openapi.Schema(type=openapi.TYPE_STRING, description="User's password"),
            },
            required=["username", "password"],
        ),
        responses={
            200: openapi.Response(
                "Success",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"message": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            400: openapi.Response(
                "Bad Request",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request):
        # ベースAPIにログインリクエストを送信
        api_client = BaseAPIClient()
        url = f"{api_client.base_url}/api/v1/auth/login"
        
        session = requests.Session()
        headers = {'Content-Type': 'application/json'}
        
        try:
            upstream_response = session.post(url, json=request.data, headers=headers, timeout=15)
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


class AuthLogoutProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのログアウトを中継"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Logout (proxy)",
        operation_description="拡張API経由でベースAPIのログアウトを中継",
        tags=["auth"],
        responses={
            200: openapi.Response(
                "Logout successful",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"message": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            401: openapi.Response(
                "Authentication required",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
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

    @swagger_auto_schema(
        operation_summary="User info (proxy)",
        operation_description="拡張API経由でベースAPIのユーザー情報を取得",
        tags=["auth"],
        responses={
            200: openapi.Response("User info"),
            401: openapi.Response(
                "Authentication required",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def get(self, request):
        if not _has_session_credentials(request):
            return JsonResponse({"detail": UNAUTHENTICATED_DETAIL}, status=401)
        return self._proxy_request(request, "GET", "/api/v1/user/info")

