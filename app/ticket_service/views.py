import json
import logging
import os
from pathlib import Path
import requests
from django import forms
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import now as tz_now
from django.views import View
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from ticket_service.models import Account, TicketDesign, TicketCheckinRecord, TicketCheckinUrl
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


class TicketListAPIView(APIView):
    """
    チケットNFT一覧取得API
    GET /api/ext/v1/ticket/list
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="List Ticket NFTs",
        description="ログインユーザーのNFTからチケット情報を抽出して返す。",
        tags=["ticket"],
        responses={
            200: inline_serializer(
                name="TicketListSuccess",
                fields={
                    "count": serializers.IntegerField(),
                    "results": serializers.ListField(
                        child=inline_serializer(
                            name="TicketListItem",
                            fields={
                                "nft_origin": serializers.CharField(),
                                "checkin_url": serializers.CharField(allow_null=True),
                                "ticket_image_url": serializers.CharField(allow_null=True),
                                "event_name": serializers.CharField(allow_null=True),
                                "event_date": serializers.CharField(allow_null=True),
                                "venue": serializers.CharField(allow_null=True),
                                "seat": serializers.CharField(allow_null=True),
                            },
                        ),
                    ),
                },
            ),
            401: inline_serializer(name="TicketListUnauthorized", fields={"detail": serializers.CharField()}),
        },
    )
    def get(self, request):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response({"detail": UNAUTHENTICATED_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)

        api_client = BaseAPIClient()
        ticket_service = TicketService()
        nfts = api_client.get_user_nfts(session_cookies)
        if isinstance(nfts, dict):
            nfts = nfts.get("results") or nfts.get("nfts") or []
        if not isinstance(nfts, list):
            nfts = []

        results = []
        for nft in nfts:
            if not isinstance(nft, dict):
                continue

            nft_origin = nft.get("nft_origin")
            if not nft_origin:
                continue

            metadata = nft.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            ticket_meta = self._extract_reward_ticket_metadata(metadata)
            if self._is_checkin_reward(ticket_meta):
                continue

            payload = ticket_service.extract_ticket_payload_from_metadata(metadata)
            checkin_url = (
                TicketCheckinUrl.objects.filter(nft_origin=nft_origin).values_list("checkin_url", flat=True).first()
                or _get_checkin_url_from_metadata(metadata)
            )
            if not checkin_url:
                token = ticket_service.build_checkin_token(nft_origin=nft_origin)
                checkin_url = request.build_absolute_uri(f"/api/ext/v1/ticket/checkin?token={token}")

            results.append(
                {
                    "nft_origin": nft_origin,
                    "checkin_url": checkin_url,
                    "ticket_image_url": f"/api/ext/v1/ticket/image/{nft_origin}",
                    "event_name": payload.event_title or None,
                    "event_date": payload.event_datetime or None,
                    "venue": payload.venue or None,
                    "seat": payload.seat or None,
                }
            )

        return Response({"count": len(results), "results": results})

    def _extract_reward_ticket_metadata(self, metadata: dict) -> dict:
        ticket = metadata.get("ticket")
        if isinstance(ticket, dict):
            return ticket

        map_meta = metadata.get("MAP") or metadata.get("map")
        if not isinstance(map_meta, dict):
            return {}
        sub_type_data = map_meta.get("subTypeData")
        if isinstance(sub_type_data, str):
            try:
                sub_type_data = json.loads(sub_type_data)
            except Exception:
                sub_type_data = None
        if isinstance(sub_type_data, dict):
            nested_ticket = sub_type_data.get("ticket")
            if isinstance(nested_ticket, dict):
                return nested_ticket
            return sub_type_data
        return {}

    def _is_checkin_reward(self, ticket_meta: dict) -> bool:
        if not isinstance(ticket_meta, dict):
            return False
        return str(ticket_meta.get("reward_type", "")).strip() == "checkin_reward"

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


class RewardListAPIView(APIView):
    """
    報酬NFT一覧取得API
    GET /api/ext/v1/reward/list
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="List Reward NFTs",
        description="ログインユーザーのNFTから check-in 報酬NFTを抽出して返す。",
        tags=["reward"],
        responses={
            200: inline_serializer(
                name="RewardListSuccess",
                fields={
                    "count": serializers.IntegerField(),
                    "results": serializers.ListField(
                        child=inline_serializer(
                            name="RewardListItem",
                            fields={
                                "nft_origin": serializers.CharField(),
                                "reward_for": serializers.CharField(allow_null=True),
                                "reward_name": serializers.CharField(allow_null=True),
                                "created_at": serializers.CharField(allow_null=True),
                            },
                        ),
                    ),
                },
            ),
            401: inline_serializer(name="RewardListUnauthorized", fields={"detail": serializers.CharField()}),
        },
    )
    def get(self, request):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response({"detail": UNAUTHENTICATED_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)

        api_client = BaseAPIClient()
        nfts = api_client.get_user_nfts(session_cookies)
        if isinstance(nfts, dict):
            nfts = nfts.get("results") or nfts.get("nfts") or []
        if not isinstance(nfts, list):
            nfts = []

        results = []
        for nft in nfts:
            if not isinstance(nft, dict):
                continue
            nft_origin = nft.get("nft_origin")
            if not nft_origin:
                continue

            metadata = nft.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            ticket_meta = self._extract_reward_ticket_metadata(metadata)
            if not self._is_checkin_reward(ticket_meta):
                continue

            results.append(
                {
                    "nft_origin": nft_origin,
                    "reward_for": str(ticket_meta.get("reward_for", "") or "") or None,
                    "reward_name": str(ticket_meta.get("reward_name", "") or "") or None,
                    "created_at": str(ticket_meta.get("created_at", "") or "") or None,
                }
            )

        return Response({"count": len(results), "results": results})

    def _extract_reward_ticket_metadata(self, metadata: dict) -> dict:
        ticket = metadata.get("ticket")
        if isinstance(ticket, dict):
            return ticket

        map_meta = metadata.get("MAP") or metadata.get("map")
        if not isinstance(map_meta, dict):
            return {}
        sub_type_data = map_meta.get("subTypeData")
        if isinstance(sub_type_data, str):
            try:
                sub_type_data = json.loads(sub_type_data)
            except Exception:
                sub_type_data = None
        if isinstance(sub_type_data, dict):
            nested_ticket = sub_type_data.get("ticket")
            if isinstance(nested_ticket, dict):
                return nested_ticket
            return sub_type_data
        return {}

    def _is_checkin_reward(self, ticket_meta: dict) -> bool:
        if not isinstance(ticket_meta, dict):
            return False
        return str(ticket_meta.get("reward_type", "")).strip() == "checkin_reward"

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


class TicketCheckinAPIView(APIView):
    """
    チェックインAPI
    GET/POST /api/ext/v1/ticket/checkin
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Ticket check-in status",
        description="token を検証してチケットの利用状態（used/used_at）を返す。更新は行わない。",
        tags=["ticket"],
        parameters=[
            OpenApiParameter(
                name="token",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="チェックイントークン",
            ),
        ],
        responses={
            200: inline_serializer(
                name="TicketCheckinStatusSuccess",
                fields={
                    "used": serializers.BooleanField(),
                    "used_at": serializers.CharField(allow_null=True),
                    "nft_origin": serializers.CharField(),
                    "message": serializers.CharField(),
                },
            ),
            400: inline_serializer(name="TicketCheckinStatusBadRequest", fields={"error": serializers.CharField()}),
            401: inline_serializer(name="TicketCheckinStatusUnauthorized", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="TicketCheckinStatusNotFound", fields={"error": serializers.CharField()}),
        },
    )
    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)
        return self._get_checkin_status(request, token)

    @extend_schema(
        summary="Ticket check-in execute",
        description="token を検証し、未使用チケットを使用済みに更新する。",
        tags=["ticket"],
        request=inline_serializer(
            name="TicketCheckinExecuteRequest",
            fields={"token": serializers.CharField()},
        ),
        responses={
            200: inline_serializer(
                name="TicketCheckinExecuteSuccess",
                fields={
                    "used": serializers.BooleanField(),
                    "used_at": serializers.CharField(allow_null=True),
                    "nft_origin": serializers.CharField(),
                    "message": serializers.CharField(required=False),
                    "reward_nft": serializers.JSONField(allow_null=True, required=False),
                },
            ),
            400: inline_serializer(name="TicketCheckinExecuteBadRequest", fields={"error": serializers.CharField()}),
            401: inline_serializer(name="TicketCheckinExecuteUnauthorized", fields={"detail": serializers.CharField()}),
            404: inline_serializer(name="TicketCheckinExecuteNotFound", fields={"error": serializers.CharField()}),
            500: inline_serializer(name="TicketCheckinExecuteServerError", fields={"error": serializers.CharField()}),
        },
    )
    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)
        return self._process_checkin(request, token)

    def _get_checkin_status(self, request, token: str):
        nft_origin = self._verify_token(token)
        if not nft_origin:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)

        record = TicketCheckinRecord.objects.filter(nft_origin=nft_origin).first()
        used = bool(record)
        used_at = record.used_at.isoformat().replace("+00:00", "Z") if record else None
        return Response(
            {
                "used": used,
                "used_at": used_at,
                "nft_origin": nft_origin,
                "message": "Already checked in" if used else "Not checked in",
            }
        )

    def _process_checkin(self, request, token: str):
        nft_origin = self._verify_token(token)
        if not nft_origin:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)

        session_cookies = self._extract_session_cookies(request)
        checked_in_by = ""
        if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
            checked_in_by = request.user.username

        record = TicketCheckinRecord.objects.filter(nft_origin=nft_origin).first()
        if record:
            used_at = record.used_at.isoformat().replace("+00:00", "Z")
            reward_nft = None
            reward_nft_origin = getattr(record, "reward_nft_origin", "")
            if reward_nft_origin:
                reward_nft = {"created": True, "nft_origin": reward_nft_origin}
            return Response(
                {
                    "used": True,
                    "used_at": used_at,
                    "nft_origin": nft_origin,
                    "message": "Already checked in",
                    "reward_nft": reward_nft,
                }
            )

        reward_nft = self._create_default_reward(session_cookies, nft_origin)
        reward_nft_origin = ""
        if isinstance(reward_nft, dict) and reward_nft.get("created") and reward_nft.get("nft_origin"):
            reward_nft_origin = str(reward_nft["nft_origin"])

        record = TicketCheckinRecord.objects.create(
            nft_origin=nft_origin,
            used_at=tz_now(),
            checked_in_by=checked_in_by,
            reward_nft_origin=reward_nft_origin,
        )
        used_at = record.used_at.isoformat().replace("+00:00", "Z")
        return Response(
            {
                "used": True,
                "used_at": used_at,
                "nft_origin": nft_origin,
                "message": "Checked in",
                "reward_nft": reward_nft,
            }
        )

    def _verify_token(self, token: str) -> str | None:
        ticket_service = TicketService()
        try:
            return ticket_service.verify_checkin_token(token)
        except Exception as e:
            logger.warning("Invalid check-in token: %s", e)
            return None

    def _load_reward_image_for_checkin(self):
        """
        チェックイン報酬用画像を取得。
        1) active TicketDesign.checkin_reward_image
        2) image_samples/SendaiArt1_Reward.jpg
        """
        active_design = TicketDesign.get_active()
        if active_design and active_design.checkin_reward_image:
            try:
                with active_design.checkin_reward_image.open("rb") as f:
                    image_bytes = f.read()
                if image_bytes:
                    image_filename = Path(active_design.checkin_reward_image.name).name or "checkin_reward.png"
                    return image_bytes, image_filename, None
            except Exception as e:
                logger.warning("Failed to read TicketDesign.checkin_reward_image: %s", e, exc_info=True)

        default_image_path = Path(settings.BASE_DIR) / "image_samples" / "SendaiArt1_Reward.jpg"
        if not default_image_path.exists():
            return None, None, "Default reward image not found"
        try:
            return default_image_path.read_bytes(), default_image_path.name, None
        except Exception as e:
            logger.error("Failed to read default reward image: %s", e, exc_info=True)
            return None, None, "Failed to read default reward image"

    def _create_default_reward(self, session_cookies: dict, nft_origin: str):
        if not session_cookies:
            return {"error": "Authentication credentials were not provided."}
        image_bytes, image_filename, image_error = self._load_reward_image_for_checkin()
        if image_error:
            return {"error": image_error}

        metadata = {
            "ticket": {
                "reward_type": "checkin_reward",
                "source": "ticket_checkin",
                "reward_for": nft_origin,
            }
        }
        api_client = BaseAPIClient()
        result = api_client.create_reward_nft(
            image_file=image_bytes,
            image_filename=image_filename,
            metadata=metadata,
            recipient_paymail=None,
            session_cookies=session_cookies,
        )
        if not result:
            return {"error": "Failed to create reward NFT"}
        nft_info = result.get("nft_information", {}) if isinstance(result, dict) else {}
        return {"created": True, "nft_origin": nft_info.get("nft_origin")}

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


class RewardCreateAPIView(APIView):
    """
    チェックイン報酬画像登録API
    POST /api/ext/v1/reward/create
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @extend_schema(
        summary="Register check-in reward image",
        description=(
            "チェックイン時の報酬NFTに使う画像を登録します。"
            "reward_image を未指定の場合は image_samples/SendaiArt1_Reward.jpg を登録します。"
            "このAPIはNFTを作成しません。"
        ),
        tags=["reward"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "reward_image": {"type": "string", "format": "binary", "description": "報酬画像（省略可）"},
                },
            },
        },
        responses={
            200: inline_serializer(
                name="RewardRegisterSuccess",
                fields={
                    "status": serializers.CharField(),
                    "message": serializers.CharField(),
                    "ticket_design_id": serializers.IntegerField(),
                    "image_name": serializers.CharField(),
                    "image_url": serializers.CharField(allow_null=True),
                    "used_default_image": serializers.BooleanField(),
                },
            ),
            400: inline_serializer(name="RewardCreateBadRequest", fields={"error": serializers.CharField()}),
            401: inline_serializer(name="RewardCreateUnauthorized", fields={"detail": serializers.CharField()}),
            500: inline_serializer(name="RewardCreateServerError", fields={"error": serializers.CharField()}),
        },
    )
    def post(self, request):
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"detail": UNAUTHENTICATED_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        reward_file = request.FILES.get("reward_image")
        used_default_image = False

        if reward_file:
            image_bytes = reward_file.read()
            image_filename = getattr(reward_file, "name", "reward.png")
            if not image_bytes:
                return Response(
                    {"error": "reward_image is empty"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            used_default_image = True
            # 既定画像（image_samples/SendaiArt1_Reward.jpg）を使用
            default_image_path = Path(settings.BASE_DIR) / "image_samples" / "SendaiArt1_Reward.jpg"
            if not default_image_path.exists():
                return Response(
                    {
                        "error": (
                            "Default reward image not found: "
                            "image_samples/SendaiArt1_Reward.jpg"
                        )
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            try:
                image_bytes = default_image_path.read_bytes()
                image_filename = default_image_path.name
            except Exception as e:
                logger.error("Failed to read default reward image: %s", e, exc_info=True)
                return Response(
                    {"error": "Failed to read default reward image"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        active_design = TicketDesign.get_active()
        if not active_design:
            active_design = TicketDesign.objects.create(name="Default", is_active=True)
        active_design.checkin_reward_image.save(image_filename, ContentFile(image_bytes), save=True)

        return Response(
            {
                "status": "success",
                "message": "Check-in reward image registered successfully",
                "ticket_design_id": active_design.id,
                "image_name": Path(active_design.checkin_reward_image.name).name,
                "image_url": (
                    active_design.checkin_reward_image.url if active_design.checkin_reward_image else None
                ),
                "used_default_image": used_default_image,
            },
            status=status.HTTP_200_OK,
        )

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


class TicketsPageView(View):
    """
    マイチケット・報酬表示ページ。
    GET /tickets/
    既存の ticket/list と reward/list API を内部 HTTP で呼び、結果を表示する。
    """

    def get(self, request):
        ticket_list_url = request.build_absolute_uri("/api/ext/v1/ticket/list")
        reward_list_url = request.build_absolute_uri("/api/ext/v1/reward/list")
        cookies = dict(request.COOKIES) if request.COOKIES else {}

        try:
            ticket_resp = requests.get(ticket_list_url, cookies=cookies, timeout=10)
            if ticket_resp.status_code == 401:
                return redirect("/accounts/login/?next=/tickets/")
            ticket_list = []
            if ticket_resp.status_code == 200:
                data = ticket_resp.json()
                ticket_list = data.get("results") or []
        except Exception:
            ticket_list = []

        # 各チケットの使用済み状態を TicketCheckinRecord から付与
        # #region agent log
        _lp = "/home/ds9/ticketsystem-start/.cursor/debug-686d38.log"
        _json = __import__("json")
        try:
            _rec_nft = list(TicketCheckinRecord.objects.values_list("nft_origin", flat=True))
            with open(_lp, "a") as _f:
                _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "used_check", "location": "TicketsPageView.used_state", "message": "ticket_list vs records", "data": {"ticket_count": len(ticket_list), "ticket_nft_origins": [item.get("nft_origin") for item in ticket_list], "record_nft_origins": _rec_nft}, "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        for item in ticket_list:
            nft_origin = item.get("nft_origin")
            record = TicketCheckinRecord.objects.filter(nft_origin=nft_origin).first() if nft_origin else None
            item["used"] = record is not None
            item["used_at"] = record.used_at.strftime("%Y-%m-%d %H:%M") if record and record.used_at else None
            # #region agent log
            try:
                with open(_lp, "a") as _f:
                    _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "used_check", "location": "TicketsPageView.used_per_item", "message": "lookup result", "data": {"nft_origin": nft_origin, "found_record": record is not None, "used_at": item.get("used_at")}, "timestamp": __import__("time").time() * 1000}) + "\n")
            except Exception:
                pass
            # #endregion

        try:
            reward_resp = requests.get(reward_list_url, cookies=cookies, timeout=10)
            if reward_resp.status_code == 401:
                return redirect("/accounts/login/?next=/tickets/")
            reward_list = []
            if reward_resp.status_code == 200:
                data = reward_resp.json()
                reward_list = data.get("results") or []
        except Exception:
            reward_list = []

        return render(
            request,
            "ticket_service/tickets.html",
            {"ticket_list": ticket_list, "reward_list": reward_list},
        )


class RewardImageAPIView(View):
    """
    報酬NFT画像取得API。
    GET /api/ext/v1/reward/image/<nft_origin>
    NFT の生データを取得し、画像として返す。未ログインは 401。
    """

    def get(self, request, nft_origin: str):
        _lp = "/home/ds9/ticketsystem-start/.cursor/debug-686d38.log"
        _json = __import__("json")
        _time = __import__("time").time
        # #region agent log
        try:
            _c = _get_proxy_cookies(request)
            with open(_lp, "a") as _f:
                _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "A", "location": "RewardImageAPIView.get.entry", "message": "reward image request", "data": {"nft_origin": nft_origin, "has_cookies": bool(_c), "cookie_keys": list(_c.keys()) if _c else []}, "timestamp": _time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        cookies = _get_proxy_cookies(request)
        if not cookies:
            # #region agent log
            try:
                with open(_lp, "a") as _f:
                    _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "A", "location": "RewardImageAPIView.get.401", "message": "no cookies", "data": {}, "timestamp": _time() * 1000}) + "\n")
            except Exception:
                pass
            # #endregion
            return HttpResponse(
                '{"detail": "Authentication credentials were not provided."}',
                status=401,
                content_type="application/json",
            )
        api_client = BaseAPIClient()
        raw_bytes = api_client.get_nft_raw(nft_origin, cookies)
        # #region agent log
        try:
            with open(_lp, "a") as _f:
                _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "B", "location": "RewardImageAPIView.get.after_get_nft_raw", "message": "raw_bytes result", "data": {"raw_is_none": raw_bytes is None, "raw_len": len(raw_bytes) if raw_bytes else 0}, "timestamp": _time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        if not raw_bytes:
            return HttpResponse(
                '{"error": "NFT not found"}',
                status=404,
                content_type="application/json",
            )
        body = strip_ordinals_envelope(raw_bytes)
        nft_data = api_client.get_nft(nft_origin, cookies)
        content_type = "image/png"
        if isinstance(nft_data, dict):
            ct = nft_data.get("content_type") or nft_data.get("content-type")
            if ct and ("image/" in str(ct) or "image/" in str(ct).lower()):
                content_type = str(ct).split(";")[0].strip()
            else:
                name = (nft_data.get("original_file_name") or "") or ""
                name_lower = name.lower()
                if name_lower.endswith(".jpg") or name_lower.endswith(".jpeg"):
                    content_type = "image/jpeg"
                elif name_lower.endswith(".webp"):
                    content_type = "image/webp"
                elif name_lower.endswith(".gif"):
                    content_type = "image/gif"
        # #region agent log
        try:
            _pre = body[:24].hex() if body and len(body) >= 24 else (body.hex() if body else "")
            with open(_lp, "a") as _f:
                _f.write(_json.dumps({"sessionId": "686d38", "hypothesisId": "C", "location": "RewardImageAPIView.get.before_return", "message": "body and content_type", "data": {"body_len": len(body) if body else 0, "content_type": content_type, "body_prefix_hex": _pre}, "timestamp": _time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        return HttpResponse(body, content_type=content_type)
