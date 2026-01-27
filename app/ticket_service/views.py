import json
import logging
import os
import requests
from django import forms
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from ticket_service.services.base_api_client import BaseAPIClient
from ticket_service.services.ticket_service import TicketService, now_iso
from ticket_service.models import TicketDesign

logger = logging.getLogger('ticket_service.views')

DEFAULT_TICKET_DESIGN_LAYOUT = (
    '{\n'
    '  "text": {\n'
    '    "x": 40,\n'
    '    "y": 40,\n'
    '    "font_size": 28,\n'
    '    "color": "#FFFFFF",\n'
    '    "line_gap": 10\n'
    '  },\n'
    '  "qr": {\n'
    '    "x": 480,\n'
    '    "y": 40,\n'
    '    "size": 260\n'
    '  }\n'
    '}'
)


class IsAdminOrAllowAll(BasePermission):
    """
    環境変数 TICKET_CREATE_REQUIRE_ADMIN で制御するパーミッションクラス
    
    - TICKET_CREATE_REQUIRE_ADMIN=True: 管理者のみ許可
    - TICKET_CREATE_REQUIRE_ADMIN=False (デフォルト): 全員許可
    """
    
    def has_permission(self, request, view):
        require_admin = os.environ.get('TICKET_CREATE_REQUIRE_ADMIN', 'False').lower() == 'true'
        
        if not require_admin:
            # 管理者チェック不要 - 全員許可
            return True
        
        # 管理者チェックが必要な場合
        # セッションに保存されたユーザー情報を確認
        user_info = request.session.get('base_api_user_info', {})
        if user_info.get('is_staff') or user_info.get('is_superuser'):
            return True
        
        # DjangoのUserモデルも確認（ローカル認証の場合）
        if hasattr(request, 'user') and request.user.is_authenticated:
            if request.user.is_staff or request.user.is_superuser:
                return True
        
        return False


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
        # クッキーをセッションに設定（ドメインを指定しない - requestsが自動的に処理）
        logger.debug(f"Proxy request to {url}, cookies: {list(request.COOKIES.keys())}")
        for cookie_name, cookie_value in request.COOKIES.items():
            # ドメインを指定せずにクッキーを設定（requestsがURLに基づいて送信）
            session.cookies.set(cookie_name, cookie_value)

        headers = {}
        csrf_token = request.COOKIES.get('csrftoken') or request.headers.get('X-CSRFToken')
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
        
        # ログアウト時にDjangoセッションもクリア
        if response.status_code == 200:
            try:
                request.session.pop('base_api_authenticated', None)
                request.session.pop('base_api_user_info', None)
                request.session.save()
            except Exception as e:
                logger.warning(f"Failed to clear session info after logout: {e}")
        
        return response


class AuthUserProxyAPIView(BaseAPIProxyMixin, APIView):
    """拡張API経由でベースAPIのユーザー情報を取得"""

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="User info (proxy)",
        operation_description="拡張API経由でベースAPIのユーザー情報を取得",
        tags=["auth"],
        responses={200: openapi.Response("User info")},
    )
    def get(self, request):
        return self._proxy_request(request, "GET", "/api/v1/user/info")


class TicketImageAPIView(APIView):
    """
    チケット画像生成API
    
    GET /api/ext/v1/ticket/image/<nft_origin>
    
    ベースAPIからNFT情報を取得し、チケット画像を生成して返却します。
    """
    
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]  # セッションクッキーで認証するため、DRFの認証は不要
    
    def get(self, request, nft_origin: str):
        # セッションクッキーを取得
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"error": "Authentication required. Please login first."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # ベースAPIからNFT情報を取得（ユーザーのNFT一覧から検索）
        api_client = BaseAPIClient()
        nft_data = api_client.get_nft_from_user_list(nft_origin, session_cookies)
        
        if not nft_data:
            # フォールバック: 直接取得を試みる
            nft_data = api_client.get_nft(nft_origin, session_cookies)
        
        if not nft_data:
            logger.warning(f"NFT not found: {nft_origin}")
            return Response(
                {"error": "NFT not found or access denied"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # メタデータを取得（get_nft_from_user_listとget_nftでレスポンス形式が異なる）
        # get_nft_from_user_list: NFT情報全体が返る（metadataフィールドあり）
        # get_nft: {"status": "success", "data": "base64..."} 形式
        metadata = nft_data.get('metadata', {})
        
        # メタデータがない場合は、別途メタデータエンドポイントから取得
        if not metadata:
            print(f"TicketImageAPIView: metadata not in nft_data, fetching from meta endpoint", flush=True)
            metadata = api_client.get_nft_metadata(nft_origin, session_cookies) or {}
        
        print(f"TicketImageAPIView: metadata keys: {list(metadata.keys()) if metadata else 'EMPTY'}", flush=True)
        
        # チケット画像を生成
        ticket_service = TicketService()
        token_str = ticket_service.build_checkin_token(nft_origin=nft_origin)
        
        # チェックインURLを生成（拡張APIのURL）
        checkin_url = request.build_absolute_uri(
            f"/api/ext/v1/ticket/checkin?token={token_str}"
        )
        
        try:
            png_bytes = ticket_service.render_ticket_png_from_metadata(
                metadata=metadata,
                checkin_url=checkin_url
            )
        except Exception as e:
            logger.error(f"TicketImageAPIView render failed: {e}", exc_info=True)
            return Response(
                {"error": "Failed to render ticket image"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        resp = HttpResponse(png_bytes, content_type="image/png", status=200)
        resp["Content-Disposition"] = f'inline; filename="ticket_{nft_origin}.png"'
        return resp
    
    def _extract_session_cookies(self, request) -> dict:
        """
        DjangoセッションからベースAPIのセッションクッキーを抽出
        
        ログイン時にベースAPIから取得したセッションクッキーを
        Djangoセッションに保存しているので、それを使用する。
        
        Returns:
            ベースAPIのセッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        """
        print(f"TicketImageAPIView._extract_session_cookies: Session keys: {list(request.session.keys())}", flush=True)
        print(f"TicketImageAPIView._extract_session_cookies: Request cookies: {list(request.COOKIES.keys())}", flush=True)
        
        # DjangoセッションからベースAPIのクッキーを取得
        base_api_cookies = request.session.get('base_api_cookies', {})
        if base_api_cookies:
            print(f"TicketImageAPIView: Using base API cookies from session: {list(base_api_cookies.keys())}", flush=True)
            return base_api_cookies
        
        # フォールバック: リクエストのクッキーを使用（後方互換性のため）
        cookies = {}
        if hasattr(request, 'COOKIES'):
            session_id = request.COOKIES.get('sessionid')
            csrf_token = request.COOKIES.get('csrftoken')
            
            if session_id:
                cookies['sessionid'] = session_id
            if csrf_token:
                cookies['csrftoken'] = csrf_token
            
            if cookies:
                print(f"TicketImageAPIView: Using cookies from request (fallback): {list(cookies.keys())}", flush=True)
        
        print(f"TicketImageAPIView: Final cookies: {list(cookies.keys()) if cookies else 'EMPTY'}", flush=True)
        return cookies


class TicketCheckinAPIView(APIView):
    """
    チェックインAPI
    
    GET/POST /api/ext/v1/ticket/checkin
    
    - GET: 状態確認のみ。トークンでチケットの使用有無（used/used_at）を返す。更新は行わない。
    - POST: 使用（チェックイン実行）。ベースAPIのNFTメタデータを更新して使用済みにし、必要に応じて報酬NFTを送付する。
    """
    
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]  # セッションクッキーで認証するため、DRFの認証は不要
    
    @swagger_auto_schema(
        operation_summary="Ticket Check-in Status (GET)",
        operation_description="チケットの状態確認のみ行います。トークンを検証し、使用済みかどうか（used/used_at）を返します。NFTメタデータの更新は行いません。",
        tags=["ticket"],
        manual_parameters=[
            openapi.Parameter(
                'token',
                openapi.IN_QUERY,
                description="チェックイントークン（QRコードから取得）",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                "Status check successful",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "used": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="チェックイン済みフラグ"),
                        "used_at": openapi.Schema(type=openapi.TYPE_STRING, description="チェックイン日時（未使用の場合はnull）"),
                        "nft_origin": openapi.Schema(type=openapi.TYPE_STRING, description="NFT Origin ID"),
                        "message": openapi.Schema(type=openapi.TYPE_STRING, description="メッセージ（例: Not checked in / Already checked in）"),
                    },
                ),
            ),
            400: openapi.Response(
                "Bad Request",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            401: openapi.Response(
                "Authentication required",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            404: openapi.Response(
                "NFT not found",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def get(self, request):
        """GET: 状態確認のみ（更新なし）"""
        token = request.query_params.get('token')
        if not token:
            return Response(
                {"error": "Token required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return self._get_checkin_status(request, token)
    
    @swagger_auto_schema(
        operation_summary="Ticket Check-in Execute (POST)",
        operation_description="チケットの使用（チェックイン実行）を行います。トークンを検証し、ベースAPIのNFTメタデータを使用済みに更新します。必要に応じてチェックイン報酬NFTを送付します。",
        tags=["ticket"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "token": openapi.Schema(type=openapi.TYPE_STRING, description="チェックイントークン"),
            },
            required=["token"],
        ),
        responses={
            200: openapi.Response(
                "Check-in successful",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "used": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="チェックイン済みフラグ"),
                        "used_at": openapi.Schema(type=openapi.TYPE_STRING, description="チェックイン日時"),
                        "nft_origin": openapi.Schema(type=openapi.TYPE_STRING, description="NFT Origin ID"),
                        "message": openapi.Schema(type=openapi.TYPE_STRING, description="メッセージ"),
                        "reward_nft": openapi.Schema(type=openapi.TYPE_OBJECT, description="報酬NFT情報（オプション）"),
                    },
                ),
            ),
            400: openapi.Response(
                "Bad Request",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            401: openapi.Response(
                "Authentication required",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            404: openapi.Response(
                "NFT not found",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request):
        """POST: 使用（チェックイン実行）"""
        token = request.data.get('token')
        if not token:
            return Response(
                {"error": "Token required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return self._process_checkin(request, token)
    
    def _get_checkin_status(self, request, token: str):
        """
        状態確認のみ。トークンを検証し、チケットの使用有無（used/used_at）を返す。
        NFTメタデータの更新は行わない。
        """
        ticket_service = TicketService()
        try:
            nft_origin = ticket_service.verify_checkin_token(token)
        except Exception as e:
            logger.warning(f"Invalid check-in token: {e}")
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        api_client = BaseAPIClient()
        metadata = api_client.get_nft_metadata(nft_origin, session_cookies)
        if metadata is None:
            logger.warning(f"NFT not found for checkin status: {nft_origin}")
            return Response(
                {"error": "NFT not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        ticket_meta = metadata.get('MAP', {}).get('subTypeData', {})
        if isinstance(ticket_meta, str):
            try:
                ticket_meta = json.loads(ticket_meta)
            except Exception:
                ticket_meta = {}
        
        ticket_info = ticket_meta.get('ticket', {})
        used_at = ticket_info.get('used_at')
        used = bool(used_at)
        message = "Already checked in" if used else "Not checked in"
        
        return Response({
            "used": used,
            "used_at": used_at,
            "nft_origin": nft_origin,
            "message": message,
        })
    
    def _process_checkin(self, request, token: str):
        import sys
        print(f"=== _process_checkin called with token: {token[:50]}... ===", flush=True)
        sys.stdout.flush()
        
        # トークンを検証
        ticket_service = TicketService()
        try:
            nft_origin = ticket_service.verify_checkin_token(token)
            print(f"Token verified, nft_origin: {nft_origin}", flush=True)
        except Exception as e:
            print(f"Token verification failed: {e}", flush=True)
            logger.warning(f"Invalid check-in token: {e}")
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # セッションクッキーを取得
        print("Extracting session cookies...", flush=True)
        session_cookies = self._extract_session_cookies(request)
        print(f"Session cookies: {list(session_cookies.keys()) if session_cookies else 'None'}", flush=True)
        if not session_cookies:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # ベースAPIからNFTメタデータを取得
        api_client = BaseAPIClient()
        print(f"Fetching NFT metadata for checkin: {nft_origin}", flush=True)
        metadata = api_client.get_nft_metadata(nft_origin, session_cookies)
        print(f"NFT metadata result: {metadata is not None}", flush=True)
        
        if metadata is None:
            logger.warning(f"NFT not found for checkin: {nft_origin}")
            return Response(
                {"error": "NFT not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 既にチェックイン済みか確認
        ticket_meta = metadata.get('MAP', {}).get('subTypeData', {})
        if isinstance(ticket_meta, str):
            import json
            try:
                ticket_meta = json.loads(ticket_meta)
            except:
                ticket_meta = {}
        
        ticket_info = ticket_meta.get('ticket', {})
        if ticket_info.get('used_at'):
            return Response({
                "used": True,
                "used_at": ticket_info['used_at'],
                "nft_origin": nft_origin,
                "message": "Already checked in"
            })
        
        # チェックイン状態を更新
        updated_metadata = {
            "MAP": {
                "subTypeData": {
                    "ticket": {
                        **ticket_info,
                        "used_at": now_iso(),
                        "checked_in_by": request.user.username if hasattr(request, 'user') and request.user.is_authenticated else None
                    }
                }
            }
        }
        
        # ベースAPIでメタデータを更新
        success = api_client.update_nft_metadata(nft_origin, updated_metadata, session_cookies)
        
        if not success:
            return Response(
                {"error": "Failed to update NFT metadata"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 報酬NFTの送付（オプション）
        reward_nft = None
        design = TicketDesign.get_active()
        if design and design.checkin_reward_image:
            reward_nft = self._send_checkin_reward(
                api_client, session_cookies, metadata, nft_origin, design
            )
        
        return Response({
            "used": True,
            "used_at": updated_metadata["MAP"]["subTypeData"]["ticket"]["used_at"],
            "nft_origin": nft_origin,
            "reward_nft": reward_nft
        })
    
    def _send_checkin_reward(
        self, 
        api_client: BaseAPIClient, 
        session_cookies: dict, 
        metadata: dict,
        nft_origin: str,
        design: TicketDesign
    ):
        """チェックイン報酬NFTを送付"""
        try:
            # 報酬画像を読み込む
            with design.checkin_reward_image.open('rb') as f:
                image_data = f.read()
            
            # 受領者のpaymailを取得（NFTメタデータから）
            ticket_meta = metadata.get('MAP', {}).get('subTypeData', {})
            if isinstance(ticket_meta, str):
                import json
                try:
                    ticket_meta = json.loads(ticket_meta)
                except json.JSONDecodeError:
                    ticket_meta = {}
            
            recipient_paymail = ticket_meta.get('ticket', {}).get('holder_paymail')
            if not recipient_paymail:
                logger.warning("Recipient paymail not found in NFT metadata")
                return None
            
            # 報酬NFTのメタデータ
            reward_metadata = {
                "ticket": {
                    "reward_for": nft_origin,
                    "reward_type": "checkin_reward"
                }
            }
            
            # ベースAPIで報酬NFTを作成
            result = api_client.create_reward_nft(
                image_file=image_data,
                image_filename='checkin_reward.png',
                metadata=reward_metadata,
                recipient_paymail=recipient_paymail,
                session_cookies=session_cookies
            )
            
            if result:
                return {
                    "created": True,
                    "nft_origin": result.get('nft_information', {}).get('nft_origin')
                }
            else:
                return {"error": "Failed to create reward NFT"}
        except Exception as e:
            logger.error(f"Failed to send check-in reward: {e}", exc_info=True)
            return {"error": str(e)}
    
    def _extract_session_cookies(self, request) -> dict:
        """
        DjangoセッションからベースAPIのセッションクッキーを抽出
        
        ログイン時にベースAPIから取得したセッションクッキーを
        Djangoセッションに保存しているので、それを使用する。
        
        Returns:
            ベースAPIのセッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        """
        # DjangoセッションからベースAPIのクッキーを取得
        print(f"TicketCheckinAPIView: Session keys: {list(request.session.keys())}")
        print(f"TicketCheckinAPIView: base_api_authenticated: {request.session.get('base_api_authenticated')}")
        base_api_cookies = request.session.get('base_api_cookies', {})
        if base_api_cookies:
            print(f"TicketCheckinAPIView: Using base API cookies from session: {list(base_api_cookies.keys())}")
            return base_api_cookies
        
        # フォールバック: リクエストのクッキーを使用（後方互換性のため）
        print("TicketCheckinAPIView: base_api_cookies not found in session, using fallback")
        cookies = {}
        if hasattr(request, 'COOKIES'):
            session_id = request.COOKIES.get('sessionid')
            csrf_token = request.COOKIES.get('csrftoken')
            
            if session_id:
                cookies['sessionid'] = session_id
            if csrf_token:
                cookies['csrftoken'] = csrf_token
            
            if cookies:
                logger.info(f"TicketCheckinAPIView: Using cookies from request (fallback): {list(cookies.keys())}")
        
        return cookies


class TicketCreateAPIView(APIView):
    """
    チケットNFT作成API
    
    POST /api/ext/v1/ticket/create
    
    チケット画像を自動生成し、ベースAPIを経由してNFTを作成します。
    
    認証:
    - セッションクッキーで認証（ベースAPIへのリクエストに使用）
    - TICKET_CREATE_REQUIRE_ADMIN=True の場合、管理者のみ許可
    - TICKET_CREATE_REQUIRE_ADMIN=False (デフォルト) の場合、全員許可
    """
    
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAdminOrAllowAll]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    
    @swagger_auto_schema(
        operation_summary="Create Ticket NFT",
        operation_description="""
        チケットNFTを作成します。
        
        チケット画像（QRコード付き）を自動生成し、ベースAPIを経由してNFTを作成します。
        
        - event_name: イベント名（必須）
        - event_date: イベント日時（必須）
        - venue: 会場名（オプション）
        - seat: 座席情報（オプション）
        - recipient_paymail: 受領者paymail（省略時は自分）
        - ticket_design_id: 使用するTicketDesignのID（省略時はアクティブなデザイン）
        - ticket_design_name: TicketDesignの名称（新規作成時のみ）
        - ticket_design_layout: TicketDesignのlayout（JSON文字列）
        - template_image: 背景画像（PNG/JPG）
        - checkin_reward_image: チェックイン報酬NFT用画像
        """,
        tags=["ticket"],
        consumes=["application/json", "multipart/form-data"],
        manual_parameters=[
            openapi.Parameter(
                "event_name",
                openapi.IN_FORM,
                description="イベント名",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "event_date",
                openapi.IN_FORM,
                description="イベント日時（ISO 8601形式推奨）",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "venue",
                openapi.IN_FORM,
                description="会場名",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "seat",
                openapi.IN_FORM,
                description="座席情報",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "recipient_paymail",
                openapi.IN_FORM,
                description="受領者paymail（省略時は自分）",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "ticket_design_id",
                openapi.IN_FORM,
                description="使用するTicketDesignのID（省略時はアクティブなデザイン）",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "ticket_design_name",
                openapi.IN_FORM,
                description="TicketDesignの名称（新規作成時のみ）",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "ticket_design_layout",
                openapi.IN_FORM,
                description="TicketDesignのlayout（JSON文字列）",
                type=openapi.TYPE_STRING,
                format="textarea",
                default=DEFAULT_TICKET_DESIGN_LAYOUT,
            ),
            openapi.Parameter(
                "template_image",
                openapi.IN_FORM,
                description="背景画像（PNG/JPG）",
                type=openapi.TYPE_FILE,
            ),
            openapi.Parameter(
                "checkin_reward_image",
                openapi.IN_FORM,
                description="チェックイン報酬NFT用画像",
                type=openapi.TYPE_FILE,
            ),
        ],
        responses={
            201: openapi.Response(
                "Ticket NFT created successfully",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "status": openapi.Schema(type=openapi.TYPE_STRING, example="success"),
                        "message": openapi.Schema(type=openapi.TYPE_STRING, example="Ticket NFT created successfully"),
                        "nft_origin": openapi.Schema(type=openapi.TYPE_STRING, example="abc123..._0"),
                        "transaction_id": openapi.Schema(type=openapi.TYPE_STRING, example="abc123..."),
                        "ticket_image_url": openapi.Schema(type=openapi.TYPE_STRING, example="/api/ext/v1/ticket/image/abc123..._0"),
                        "checkin_url": openapi.Schema(type=openapi.TYPE_STRING, example="https://ticket.buxbit.net/api/ext/v1/ticket/checkin?token=..."),
                        "nft_information": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            ),
            400: openapi.Response(
                "Bad Request",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            401: openapi.Response(
                "Authentication required",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
            500: openapi.Response(
                "Internal Server Error",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
                ),
            ),
        },
    )
    def post(self, request):
        # セッションクッキーを取得
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # パラメータを取得
        event_name = request.data.get('event_name')
        event_date = request.data.get('event_date')
        venue = request.data.get('venue', '')
        seat = request.data.get('seat', '')
        recipient_paymail = request.data.get('recipient_paymail')
        ticket_design_id = request.data.get('ticket_design_id')
        ticket_design_name = request.data.get('ticket_design_name')
        ticket_design_layout = request.data.get('ticket_design_layout') or request.data.get('layout')
        template_image = request.FILES.get('template_image') or request.FILES.get('ticket_template_image')
        checkin_reward_image = request.FILES.get('checkin_reward_image') or request.FILES.get('ticket_checkin_reward_image')
        
        # バリデーション
        if not event_name:
            return Response(
                {"error": "event_name is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not event_date:
            return Response(
                {"error": "event_date is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TicketDesignの作成/更新に必要なデータを準備
        has_design_payload = any([
            ticket_design_name,
            ticket_design_layout,
            template_image,
            checkin_reward_image,
        ])
        layout_payload = None
        if ticket_design_layout:
            if isinstance(ticket_design_layout, dict):
                layout_payload = ticket_design_layout
            else:
                try:
                    layout_payload = json.loads(str(ticket_design_layout))
                except json.JSONDecodeError:
                    return Response(
                        {"error": "ticket_design_layout must be valid JSON"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        # TicketDesignを取得/作成/更新
        design = None
        if ticket_design_id:
            design = TicketDesign.objects.filter(id=ticket_design_id).first()
            if not design:
                return Response(
                    {"error": f"TicketDesign id={ticket_design_id} not found"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if has_design_payload:
                if ticket_design_name:
                    design.name = ticket_design_name
                if layout_payload is not None:
                    design.layout = layout_payload
                if template_image:
                    design.template_image = template_image
                if checkin_reward_image:
                    design.checkin_reward_image = checkin_reward_image
                design.save()
        else:
            if has_design_payload:
                design_name = ticket_design_name or f"{event_name} Design"
                design = TicketDesign.objects.create(
                    name=design_name,
                    layout=layout_payload or {},
                    template_image=template_image,
                    checkin_reward_image=checkin_reward_image,
                    is_active=True,
                )
            else:
                design = TicketDesign.get_active()
        
        # holder_paymailを決定（recipient_paymailが指定されていればそれを使用）
        holder_paymail = recipient_paymail or ''
        
        # チケットサービスを初期化
        ticket_service = TicketService()
        
        # NFT登録用に1px.pngを使用（メタデータのみをNFT化、画像は動的生成）
        import os
        placeholder_image_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "images", "1px.png"
        )
        try:
            with open(placeholder_image_path, "rb") as f:
                png_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read placeholder image: {e}", exc_info=True)
            return Response(
                {"error": "Failed to read placeholder image"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # メタデータを構築
        metadata = ticket_service.build_ticket_metadata(
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            seat=seat,
            holder_paymail=holder_paymail,
        )
        
        # NFT名を生成
        nft_name = f"{event_name} Ticket"
        
        # ベースAPIでNFTを作成
        api_client = BaseAPIClient()
        result = api_client.create_ticket_nft(
            image_file=png_bytes,
            image_filename='ticket.png',
            nft_name=nft_name,
            metadata=metadata,
            session_cookies=session_cookies,
            recipient_paymail=recipient_paymail,
        )
        
        if not result:
            return Response(
                {"error": "Failed to create NFT"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # NFT情報を取得
        nft_info = result.get('nft_information', {})
        nft_origin = nft_info.get('nft_origin')
        transaction_id = result.get('transaction_id')
        
        # 実際のチェックインURLを生成
        if nft_origin:
            token_str = ticket_service.build_checkin_token(nft_origin=nft_origin)
            checkin_url = request.build_absolute_uri(
                f"/api/ext/v1/ticket/checkin?token={token_str}"
            )
            ticket_image_url = f"/api/ext/v1/ticket/image/{nft_origin}"
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
    
    def _extract_session_cookies(self, request) -> dict:
        """
        DjangoセッションからベースAPIのセッションクッキーを抽出
        """
        # DjangoセッションからベースAPIのクッキーを取得
        base_api_cookies = request.session.get('base_api_cookies', {})
        if base_api_cookies:
            logger.debug(f"TicketCreateAPIView: Using base API cookies from session: {list(base_api_cookies.keys())}")
            return base_api_cookies
        
        # フォールバック: リクエストのクッキーを使用
        cookies = {}
        if hasattr(request, 'COOKIES'):
            session_id = request.COOKIES.get('sessionid')
            csrf_token = request.COOKIES.get('csrftoken')
            
            if session_id:
                cookies['sessionid'] = session_id
            if csrf_token:
                cookies['csrftoken'] = csrf_token
        
        return cookies

