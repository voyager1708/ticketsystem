import json
import logging
import os
import requests
from django import forms
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from ticket_service.models import Account, TicketDesign, TicketCheckinUrl
from ticket_service.services.base_api_client import BaseAPIClient
from ticket_service.services.ticket_service import (
    TicketService,
    extract_background_image_from_html,
    strip_ordinals_envelope,
)

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


def _get_checkin_url_from_metadata(metadata) -> str:
    """
    メタデータに作成時に保存した checkin_url があれば返す。
    ticket.checkin_url または MAP.subTypeData.ticket.checkin_url を参照。
    """
    if not isinstance(metadata, dict):
        return ""
    ticket = metadata.get("ticket")
    if isinstance(ticket, dict) and ticket.get("checkin_url"):
        return str(ticket.get("checkin_url", "")).strip()
    map_meta = metadata.get("MAP") or metadata.get("map")
    if isinstance(map_meta, dict):
        sub = map_meta.get("subTypeData")
        if isinstance(sub, dict):
            ticket = sub.get("ticket")
            if isinstance(ticket, dict) and ticket.get("checkin_url"):
                return str(ticket.get("checkin_url", "")).strip()
    return ""


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


class TicketCreateAPIView(APIView):
    """
    チケットNFT作成API（参考実装・goal ブランチ由来）

    POST /api/ext/v1/ticket/create

    必須: event_name, event_date。成功時 201、バリデーションエラー時 400。
    生成結果の nft_origin は後続のチェックイン API で利用可能。
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @extend_schema(
        summary="Create Ticket NFT",
        description=(
            "チケットNFTを作成します。event_name, event_date, ticket_html 必須。"
            "アップロードした HTML にスタイルが含まれるため TicketDesign は使わない。"
            "multipart/form-data で送信してください。"
        ),
        tags=["ticket"],
        request={
            "multipart/form-data": {
                "type": "object",
                "required": ["event_name", "event_date", "ticket_html"],
                "properties": {
                    "event_name": {"type": "string", "description": "イベント名（必須）"},
                    "event_date": {"type": "string", "description": "イベント日時（必須・ISO 8601推奨）"},
                    "venue": {"type": "string", "description": "会場名・場所（住所）"},
                    "seat": {"type": "string", "description": "座席情報"},
                    "recipient_paymail": {"type": "string", "description": "受領者paymail（省略時は自分）"},
                    "ticket_html": {"type": "string", "format": "binary", "description": "チケット用HTML（必須・スタイル含む）"},
                },
            },
        },
        responses={
            201: inline_serializer(
                name="TicketCreateSuccess",
                fields={
                    "status": serializers.CharField(),
                    "message": serializers.CharField(),
                    "nft_origin": serializers.CharField(),
                    "transaction_id": serializers.CharField(allow_null=True),
                    "ticket_image_url": serializers.CharField(allow_null=True),
                    "checkin_url": serializers.CharField(allow_null=True),
                    "nft_information": serializers.JSONField(allow_null=True),
                },
            ),
            400: inline_serializer(
                name="TicketCreateBadRequest",
                fields={"error": serializers.CharField()},
            ),
            401: inline_serializer(
                name="TicketCreateUnauthorized",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"detail": UNAUTHENTICATED_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        event_name = request.data.get("event_name")
        event_date = request.data.get("event_date")
        venue = request.data.get("venue", "")
        seat = request.data.get("seat", "")
        recipient_paymail = request.data.get("recipient_paymail")
        ticket_html_file = request.FILES.get("ticket_html")

        if not event_name:
            return Response(
                {"error": "event_name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not event_date:
            return Response(
                {"error": "event_date is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ticket_html_file:
            return Response(
                {"error": "ticket_html is required (HTML file with styles)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            layout_html = ticket_html_file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                {"error": "ticket_html must be UTF-8 text"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        holder_paymail = recipient_paymail or ""
        ticket_service = TicketService()

        try:
            html_str = ticket_service.render_ticket_html_for_creation(
                event_name=event_name,
                event_date=event_date,
                venue=venue,
                seat=seat,
                holder_paymail=holder_paymail,
                layout_html=layout_html,
            )
            html_bytes = html_str.encode("utf-8")
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error("Failed to render ticket HTML: %s", e, exc_info=True)
            return Response(
                {"error": "Failed to render ticket HTML"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        metadata = ticket_service.build_ticket_metadata(
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            seat=seat,
            holder_paymail=holder_paymail,
        )
        nft_name = f"{event_name} Ticket"

        api_client = BaseAPIClient()
        result = api_client.create_ticket_nft(
            image_file=html_bytes,
            image_filename="ticket.html",
            nft_name=nft_name,
            metadata=metadata,
            session_cookies=session_cookies,
            recipient_paymail=recipient_paymail,
        )

        if not result:
            return Response(
                {"error": "Failed to create NFT"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        nft_info = result.get("nft_information", {})
        nft_origin = nft_info.get("nft_origin")
        transaction_id = result.get("transaction_id")

        if nft_origin:
            token_str = ticket_service.build_checkin_token(nft_origin=nft_origin)
            checkin_url = request.build_absolute_uri(
                f"/api/ext/v1/ticket/checkin?token={token_str}",
            )
            ticket_image_url = f"/api/ext/v1/ticket/image/{nft_origin}"
            TicketCheckinUrl.objects.update_or_create(
                defaults={"checkin_url": checkin_url},
                nft_origin=nft_origin,
            )
        else:
            checkin_url = None
            ticket_image_url = None

        return Response({
            "status": "success",
            "message": "Ticket NFT created successfully",
            "nft_origin": nft_origin,
            "transaction_id": transaction_id,
            "ticket_image_url": ticket_image_url,
            "checkin_url": checkin_url,
            "nft_information": nft_info,
        }, status=status.HTTP_201_CREATED)

    def _extract_session_cookies(self, request):
        base_api_cookies = request.session.get("base_api_cookies", {})
        if base_api_cookies:
            return base_api_cookies
        cookies = {}
        if hasattr(request, "COOKIES"):
            if request.COOKIES.get("sessionid"):
                cookies["sessionid"] = request.COOKIES.get("sessionid")
            if request.COOKIES.get("csrftoken"):
                cookies["csrftoken"] = request.COOKIES.get("csrftoken")
        return cookies


class TicketImageAPIView(APIView):
    """
    チケット画像取得API。メタデータ ＋ TicketDesign（背景・layout JSON）＋ QR を PIL で描画して PNG を返す。
    GET /api/ext/v1/ticket/image/<nft_origin>
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get ticket image",
        description="チケット画像（PNG）を返す。HTML テンプレートでレイアウトし QR を含む。",
        tags=["ticket"],
        responses={
            200: {"content": {"image/png": {}}, "description": "PNG image"},
            401: inline_serializer(name="TicketImageUnauthorized", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="TicketImageNotFound", fields={"error": serializers.CharField()}),
        },
    )
    def get(self, request, nft_origin: str):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"detail": UNAUTHENTICATED_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        api_client = BaseAPIClient()
        nft_data = api_client.get_nft(nft_origin, session_cookies)
        if not nft_data:
            return Response(
                {"error": "NFT not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        metadata = nft_data.get("metadata", nft_data) if isinstance(nft_data, dict) else {}
        if not metadata and isinstance(nft_data, dict):
            metadata = nft_data
        ticket_service = TicketService()
        raw_bytes = api_client.get_nft_raw(nft_origin, session_cookies)
        html_bytes = strip_ordinals_envelope(raw_bytes) if raw_bytes else b""
        payload = ticket_service.extract_ticket_payload_from_metadata(metadata)
        if not any([payload.event_title, payload.event_datetime, payload.venue, payload.seat, payload.holder_name, payload.ticket_id]) and html_bytes:
            payload_from_html = ticket_service.extract_ticket_payload_from_html(html_bytes)
            if payload_from_html:
                metadata = ticket_service.metadata_from_payload(payload_from_html)
        checkin_url = (
            TicketCheckinUrl.objects.filter(nft_origin=nft_origin).values_list("checkin_url", flat=True).first()
            or _get_checkin_url_from_metadata(metadata)
        )
        if not checkin_url:
            checkin_url = request.build_absolute_uri(
                f"/api/ext/v1/ticket/checkin?token={ticket_service.build_checkin_token(nft_origin)}"
            )
        png_bytes = None
        if html_bytes:
            png_bytes, render_error = ticket_service.render_html_to_png_then_add_qr(html_bytes, checkin_url)
            # HTML がある場合は NFT の内容をそのまま表示する。置換（メタデータから描き直し）は行わない。
            if png_bytes is None:
                logger.error(
                    "TicketImageAPIView: HTML present but Playwright render failed for nft_origin=%s: %s",
                    nft_origin,
                    render_error or "unknown",
                )
                return Response(
                    {
                        "error": "Ticket image could not be rendered. Playwright may be unavailable.",
                        "detail": render_error or "Unknown error",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        if png_bytes is None:
            # HTML がない場合のみメタデータから PNG を描画
            background_image_bytes = extract_background_image_from_html(html_bytes) if html_bytes else None
            try:
                png_bytes = ticket_service.render_ticket_png_from_metadata(
                    metadata=metadata,
                    checkin_url=checkin_url,
                    design=None,
                    background_image_bytes=background_image_bytes,
                )
            except Exception as e:
                logger.error("TicketImageAPIView render failed: %s", e, exc_info=True)
                payload = {"error": "Failed to render ticket image"}
                if getattr(settings, "DEBUG", False):
                    payload["detail"] = str(e)
                return Response(
                    payload,
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return HttpResponse(png_bytes, content_type="image/png")

    def _extract_session_cookies(self, request):
        base_api_cookies = request.session.get("base_api_cookies", {})
        if base_api_cookies:
            return base_api_cookies
        cookies = {}
        if hasattr(request, "COOKIES"):
            if request.COOKIES.get("sessionid"):
                cookies["sessionid"] = request.COOKIES.get("sessionid")
            if request.COOKIES.get("csrftoken"):
                cookies["csrftoken"] = request.COOKIES.get("csrftoken")
        return cookies


class TicketHtmlAPIView(APIView):
    """
    チケットの素の HTML を返す。Ordinals の envelope を除いた HTML のみ返すので、
    ダウンロードしてブラウザで開いても文字化けしない。
    GET /api/ext/v1/ticket/html/<nft_origin>
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get ticket HTML (decoded)",
        description="Ordinals envelope を除いた HTML のみ返す。保存してブラウザで開くと正しく表示される。",
        tags=["ticket"],
        responses={
            200: {"content": {"text/html": {}}, "description": "Plain HTML"},
            401: inline_serializer(name="TicketHtmlUnauthorized", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="TicketHtmlNotFound", fields={"error": serializers.CharField()}),
        },
    )
    def get(self, request, nft_origin: str):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"detail": UNAUTHENTICATED_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        api_client = BaseAPIClient()
        raw_bytes = api_client.get_nft_raw(nft_origin, session_cookies)
        if not raw_bytes:
            return Response(
                {"error": "NFT not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        html_bytes = strip_ordinals_envelope(raw_bytes)
        response = HttpResponse(html_bytes, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="ticket.html"'
        return response

    def _extract_session_cookies(self, request):
        base_api_cookies = request.session.get("base_api_cookies", {})
        if base_api_cookies:
            return base_api_cookies
        cookies = {}
        if hasattr(request, "COOKIES"):
            if request.COOKIES.get("sessionid"):
                cookies["sessionid"] = request.COOKIES.get("sessionid")
            if request.COOKIES.get("csrftoken"):
                cookies["csrftoken"] = request.COOKIES.get("csrftoken")
        return cookies

