# Colab用 1セル実行手順（実API呼び出し版 / app準拠）

この資料はColab上でAPIを順番に実行し、`Goal` まで進むための手順書です。
※今回は使用しません

## 使い方
- 上から順に **セル1から順番に** 実行する（スキップしない）
- 流れは **準備 → 実装 → 起動 → 検証** の一本道
- 参照元は `app/ticket_service/urls.py` の実エンドポイント
- この手順は「ハンズオンで作成したローカルAPI」を実際に呼び出して検証する
- 詰まったら「どのセルで」「何を期待して」「何が起きたか」をAIに渡して相談する

---

## セル1（テキストセル）: AIへの固定ルール
```text
あなたはDjango/DRFの実装・検証アシスタントです。

このノートブックは app フォルダ準拠の実API検証を行う。
対象エンドポイント:
- POST /api/ext/v1/auth/login
- GET  /api/ext/v1/auth/user
- POST /api/ext/v1/ticket/create
- PATCH /api/ext/v1/ticket/layout
- GET  /api/ext/v1/ticket/image/{nft_origin}
- GET  /api/ext/v1/reward/image/{nft_origin}
- GET  /api/ext/v1/ticket/checkin/token?nft_origin=...
- GET/POST /api/ext/v1/ticket/checkin
- GET  /api/ext/v1/auth/logout
このセルは実行しない。以降のコードセルを順番に実行して検証する。
制約:
- 呼び出し先はローカルAPI（http://127.0.0.1:8000）
- BASE_API_URL 環境変数は https://linode.buxbit.net を使用
- APIキー/トークン/パスワードはコード直書きしない
- 既存ファイル削除禁止、全面上書き禁止
- 変更提案は最小差分
禁止事項:
- ファイル/ディレクトリ削除
- 一括自動改変スクリプト（subprocess, shutil, reによる大量変更）
- 既存設定の全面上書き
```

---

## セル2（テキストセル）: Base APIユーザー新規作成（最初に実施）
この手順は必須。`USERNAME` / `PASSWORD` はここで作成したものをセル6で入力する。

1. ブラウザで Base API サイト（`https://linode.buxbit.net`）を開く  
2. 新規アカウントを作成する（username / password を控える）  
3. ログイン可能であることを確認する  
4. Colabに戻り、セル6で同じ `USERNAME` / `PASSWORD` を入力する

> 既存アカウントがある場合は再作成不要。既存の有効な認証情報を使用してよい。

---

## セル3（コードセル）: 依存インストール
```bash
# Cell 3
!pip -q install django djangorestframework drf-spectacular requests python-dotenv pillow qrcode
```

---

## セル4（コードセル）: Swagger追加セットアップ
```bash
%%bash
# Cell 4
python -m pip -q install drf-spectacular
```

---

## セル5（コードセル）: 永続保存セットアップ（Google Drive）
```python
# Cell 5
from google.colab import drive
from pathlib import Path
import os

drive.mount("/content/drive")

WORK_DIR = Path("/content/drive/MyDrive/colabo/tickets-handson")
WORK_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(WORK_DIR)

print("WORK_DIR =", WORK_DIR)
print("cwd =", Path.cwd())
```

---

## セル6（コードセル）: 接続先と資格情報の入力
```python
# Cell 6
import os
from getpass import getpass

# ハンズオンで作成したローカルAPIを呼び出す
os.environ["API_BASE"] = "http://127.0.0.1:8000"
API_BASE = os.environ["API_BASE"]

# ベースAPI URL（app/ticket_system/settings.py 準拠）
os.environ["BASE_API_URL"] = "https://linode.buxbit.net"

USERNAME = input("Base API username: ").strip()
PASSWORD = getpass("Base API password: ").strip()

print("API_BASE =", API_BASE)
print("BASE_API_URL =", os.environ["BASE_API_URL"])
```

---

## セル7（コードセル）: Django雛形作成（未作成時のみ）
```bash
%%bash
# Cell 7
set -e
cd /content/drive/MyDrive/colabo/tickets-handson

if [ ! -f manage.py ]; then
  python -m django startproject mysite .
fi

if [ ! -d ticket_service ]; then
  python manage.py startapp ticket_service
fi

if [ ! -d accounts ]; then
  python manage.py startapp accounts
fi

ls -la
```

---

## セル8（コードセル）: `settings.py` を必須設定で初期化
```python
# Cell 8
from pathlib import Path
import re

settings_path = Path("/content/drive/MyDrive/colabo/tickets-handson/mysite/settings.py")
text = settings_path.read_text()

# INSTALLED_APPS を安全に更新
apps_block = """INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "ticket_service",
    "accounts",
]"""
text, n = re.subn(r"INSTALLED_APPS\s*=\s*\[(?:.|\n)*?\]", apps_block, text, count=1)
if n == 0:
    raise RuntimeError("INSTALLED_APPS block not found")

# 必須設定を追記（未設定時のみ）
if "REST_FRAMEWORK =" not in text:
    text += """

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
"""

if "SPECTACULAR_SETTINGS =" not in text:
    text += """

SPECTACULAR_SETTINGS = {
    "TITLE": "Ticket Extension API",
    "VERSION": "v1",
    "COMPONENT_SPLIT_REQUEST": True,
}
"""

if "BASE_API_URL =" not in text:
    text += """

# Base API URL
import os
BASE_API_URL = os.environ.get("BASE_API_URL", "https://linode.buxbit.net")
"""

if "API_BASE =" not in text:
    text += """

# Local API URL
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
"""

# Colab検証用に全ホスト許可
if "ALLOWED_HOSTS =" in text:
    text = re.sub(r"ALLOWED_HOSTS\s*=\s*\[[^\]]*\]", "ALLOWED_HOSTS = ['*']", text, count=1)
else:
    text += "\nALLOWED_HOSTS = ['*']\n"

settings_path.write_text(text)
print("settings.py patched")
```

---

## セル9（コードセル）: 実装ファイル作成（BASE API連携版）
```bash
%%bash
# Cell 9
set -e
cd /content/drive/MyDrive/colabo/tickets-handson

cat > ticket_service/views.py <<'EOF'
import base64
import json
import requests
from io import BytesIO
from urllib.parse import quote, unquote

from django.conf import settings
from django.http import HttpResponse
from PIL import Image, ImageDraw, ImageFont
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiRequest, OpenApiResponse, extend_schema

# Hands-on only: keep reward image bytes in memory.
# key = ticket nft_origin
REWARD_IMAGE_STORE = {}


class AuthLoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class AuthProxyGenericResponseSerializer(serializers.Serializer):
    # Upstream response is service-dependent, so keep this generic.
    detail = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


class AuthLoginProxyAPIView(APIView):
    @extend_schema(
        request=AuthLoginRequestSerializer,
        responses={
            200: AuthProxyGenericResponseSerializer,
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
            502: OpenApiResponse(description="Upstream request failed"),
        },
    )
    def post(self, request):
        url = f"{settings.BASE_API_URL.rstrip('/')}/api/v1/auth/login"
        try:
            upstream = requests.post(url, json=request.data, timeout=20)
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)

        data = {}
        try:
            data = upstream.json()
        except Exception:
            data = {"raw": upstream.text[:500]}

        response = Response(data, status=upstream.status_code)
        for c in upstream.cookies:
            response.set_cookie(c.name, c.value)
        # Swaggerからの連続呼び出し用に、ベースAPIクッキーをDjangoセッションへ保存
        request.session["base_api_cookies"] = requests.utils.dict_from_cookiejar(upstream.cookies)
        request.session.modified = True
        return response


class AuthLogoutProxyAPIView(APIView):
    def get(self, request):
        url = f"{settings.BASE_API_URL.rstrip('/')}/api/v1/auth/logout"
        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        try:
            upstream = requests.get(url, cookies=base_api_cookies, timeout=20)
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)
        try:
            response = Response(upstream.json(), status=upstream.status_code)
        except Exception:
            response = Response({"raw": upstream.text[:500]}, status=upstream.status_code)
        request.session.pop("base_api_cookies", None)
        return response


class AuthUserProxyAPIView(APIView):
    def get(self, request):
        url = f"{settings.BASE_API_URL.rstrip('/')}/api/v1/user/info"
        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        try:
            upstream = requests.get(url, cookies=base_api_cookies, timeout=20)
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)
        try:
            return Response(upstream.json(), status=upstream.status_code)
        except Exception:
            return Response({"raw": upstream.text[:500]}, status=upstream.status_code)


class TicketCreateRequestSerializer(serializers.Serializer):
    event_name = serializers.CharField()
    event_date = serializers.CharField()
    venue = serializers.CharField(required=False, allow_blank=True)
    seat = serializers.CharField(required=False, allow_blank=True)
    ticket_design_name = serializers.CharField()
    ticket_design_layout = serializers.CharField(required=False, allow_blank=True)
    extra_metadata = serializers.CharField(required=False, allow_blank=True)
    reward_image_source = serializers.CharField(required=False, allow_blank=True)
    reward_image_ref = serializers.CharField(required=False, allow_blank=True)
    template_image = serializers.ImageField(required=True)
    checkin_reward_image = serializers.ImageField(required=False, allow_null=True)


class TicketCreateResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    nft_origin = serializers.CharField(allow_null=True)
    transaction_id = serializers.CharField(required=False, allow_null=True)
    ticket_design_name = serializers.CharField()
    ticket_design_layout = serializers.CharField(required=False, allow_blank=True)
    extra_metadata = serializers.JSONField(required=False)
    reward_image_source = serializers.CharField(required=False)
    reward_image_ref = serializers.CharField(required=False, allow_blank=True)
    template_image_name = serializers.CharField()
    checkin_reward_image_name = serializers.CharField(required=False, allow_null=True)
    ticket_image_url = serializers.CharField(required=False, allow_null=True)
    checkin_url = serializers.CharField(required=False, allow_null=True)
    nft_information = serializers.JSONField(required=False)


class TicketLayoutPatchRequestSerializer(serializers.Serializer):
    nft_origin = serializers.CharField()
    ticket_design_layout = serializers.CharField(required=False, allow_blank=True)
    extra_metadata = serializers.CharField(required=False, allow_blank=True)
    reward_image_source = serializers.CharField(required=False, allow_blank=True)
    reward_image_ref = serializers.CharField(required=False, allow_blank=True)


class TicketLayoutPatchResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    nft_origin = serializers.CharField()
    ticket_design_layout = serializers.JSONField(required=False)
    extra_metadata = serializers.JSONField(required=False)
    reward_image_source = serializers.CharField(required=False)
    reward_image_ref = serializers.CharField(required=False, allow_blank=True)
    ticket_image_url = serializers.CharField()


class TicketCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        request=OpenApiRequest(
            request=TicketCreateRequestSerializer,
            encoding={
                "template_image": {"contentType": "image/png, image/jpeg"},
                "checkin_reward_image": {"contentType": "image/png, image/jpeg"},
            },
        ),
        responses={
            201: TicketCreateResponseSerializer,
            400: OpenApiResponse(description="Bad Request"),
        },
    )
    def post(self, request):
        event_name = request.data.get("event_name")
        event_date = request.data.get("event_date")
        ticket_design_name = request.data.get("ticket_design_name")
        ticket_design_layout = request.data.get("ticket_design_layout", "")
        extra_metadata_raw = request.data.get("extra_metadata", "")
        reward_image_source = str(request.data.get("reward_image_source", "")).strip().lower()
        reward_image_ref = str(request.data.get("reward_image_ref", "")).strip()
        template_image = request.FILES.get("template_image")
        checkin_reward_image = request.FILES.get("checkin_reward_image")
        if not event_name or not event_date:
            return Response({"error": "event_name and event_date are required"}, status=400)
        if not ticket_design_name:
            return Response({"error": "ticket_design_name is required"}, status=400)
        if not template_image:
            return Response({"error": "template_image is required"}, status=400)

        if not reward_image_source:
            reward_image_source = "uploaded" if checkin_reward_image else "default"
        if reward_image_source not in {"uploaded", "default", "nft_origin"}:
            return Response(
                {"error": "reward_image_source must be one of uploaded/default/nft_origin"},
                status=400,
            )
        if reward_image_source == "uploaded" and not checkin_reward_image:
            return Response(
                {"error": "checkin_reward_image is required when reward_image_source=uploaded"},
                status=400,
            )
        if reward_image_source == "nft_origin" and not reward_image_ref:
            return Response(
                {"error": "reward_image_ref is required when reward_image_source=nft_origin"},
                status=400,
            )

        reward_image_payload = None
        if checkin_reward_image and reward_image_source == "uploaded":
            reward_image_payload = {
                "bytes": checkin_reward_image.read(),
                "name": getattr(checkin_reward_image, "name", "checkin_reward.png"),
                "content_type": getattr(checkin_reward_image, "content_type", None) or "image/png",
            }

        extra_metadata = {}
        if extra_metadata_raw:
            if isinstance(extra_metadata_raw, dict):
                extra_metadata = extra_metadata_raw
            else:
                try:
                    extra_metadata = json.loads(str(extra_metadata_raw))
                except json.JSONDecodeError:
                    return Response({"error": "extra_metadata must be valid JSON"}, status=400)

        recipient_paymail = request.data.get("recipient_paymail", "").strip()
        metadata = {
            "event_name": event_name,
            "event_date": event_date,
            "venue": request.data.get("venue", ""),
            "seat": request.data.get("seat", ""),
            "ticket_design_name": ticket_design_name,
            "ticket_design_layout": ticket_design_layout,
            "extra_metadata": extra_metadata,
            "reward_image_source": reward_image_source,
            "reward_image_ref": reward_image_ref,
            "holder_paymail": recipient_paymail,
        }
        base_api_url = settings.BASE_API_URL.rstrip("/")
        create_url = f"{base_api_url}/api/v1/nft/create"

        headers = {"Referer": base_api_url + "/"}
        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        csrf_token = base_api_cookies.get("csrftoken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        files = {
            "file": (
                template_image.name,
                template_image.read(),
                getattr(template_image, "content_type", None) or "image/png",
            )
        }
        data = {
            "app": "Ticket System",
            "name": f"{event_name} Ticket",
            "additional_info": json.dumps(metadata, ensure_ascii=False),
        }
        if recipient_paymail:
            data["recipient_paymail"] = recipient_paymail

        try:
            upstream = requests.post(
                create_url,
                files=files,
                data=data,
                headers=headers,
                cookies=base_api_cookies,
                timeout=60,
            )
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)

        try:
            upstream_data = upstream.json()
        except Exception:
            upstream_data = {"raw": upstream.text[:500]}

        if upstream.status_code >= 400:
            return Response(
                {"error": "Failed to create NFT", "details": upstream_data},
                status=upstream.status_code,
            )

        nft_info = upstream_data.get("nft_information", {}) if isinstance(upstream_data, dict) else {}
        nft_origin = nft_info.get("nft_origin")
        transaction_id = upstream_data.get("transaction_id") if isinstance(upstream_data, dict) else None
        api_base = getattr(settings, "API_BASE", "http://127.0.0.1:8000").rstrip("/")
        token = quote(str(nft_origin)) if nft_origin else None
        ticket_image_url = f"/api/ext/v1/ticket/image/{nft_origin}" if nft_origin else None
        checkin_url = f"{api_base}/api/ext/v1/ticket/checkin?token={token}" if token else None
        if nft_origin and reward_image_payload:
            REWARD_IMAGE_STORE[str(nft_origin)] = reward_image_payload
        return Response(
            {
                "status": "success",
                "message": upstream_data.get("message", "Ticket NFT created successfully"),
                "nft_origin": nft_origin,
                "transaction_id": transaction_id,
                "ticket_design_name": ticket_design_name,
                "ticket_design_layout": ticket_design_layout,
                "extra_metadata": extra_metadata,
                "reward_image_source": reward_image_source,
                "reward_image_ref": reward_image_ref,
                "template_image_name": template_image.name,
                "checkin_reward_image_name": checkin_reward_image.name if checkin_reward_image else None,
                "ticket_image_url": ticket_image_url,
                "checkin_url": checkin_url,
                "nft_information": nft_info,
            },
            status=status.HTTP_201_CREATED,
        )


class TicketLayoutPatchAPIView(APIView):
    @extend_schema(
        request=TicketLayoutPatchRequestSerializer,
        responses={
            200: TicketLayoutPatchResponseSerializer,
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
            502: OpenApiResponse(description="Upstream request failed"),
        },
    )
    def patch(self, request):
        nft_origin = request.data.get("nft_origin")
        layout_raw = request.data.get("ticket_design_layout")
        extra_metadata_raw = request.data.get("extra_metadata")
        reward_image_source_raw = request.data.get("reward_image_source")
        reward_image_ref_raw = request.data.get("reward_image_ref")
        if not nft_origin:
            return Response({"error": "nft_origin is required"}, status=400)

        if (
            layout_raw in (None, "")
            and extra_metadata_raw in (None, "")
            and reward_image_source_raw in (None, "")
            and reward_image_ref_raw in (None, "")
        ):
            return Response(
                {"error": "ticket_design_layout or extra_metadata or reward_image_source/reward_image_ref is required"},
                status=400,
            )

        layout_payload = None
        if isinstance(layout_raw, dict):
            layout_payload = layout_raw
        elif layout_raw not in (None, ""):
            try:
                layout_payload = json.loads(str(layout_raw))
            except json.JSONDecodeError:
                return Response({"error": "ticket_design_layout must be valid JSON"}, status=400)

        extra_metadata_payload = None
        if isinstance(extra_metadata_raw, dict):
            extra_metadata_payload = extra_metadata_raw
        elif extra_metadata_raw not in (None, ""):
            try:
                extra_metadata_payload = json.loads(str(extra_metadata_raw))
            except json.JSONDecodeError:
                return Response({"error": "extra_metadata must be valid JSON"}, status=400)

        reward_image_source = None
        if reward_image_source_raw not in (None, ""):
            reward_image_source = str(reward_image_source_raw).strip().lower()
            if reward_image_source not in {"uploaded", "default", "nft_origin"}:
                return Response(
                    {"error": "reward_image_source must be one of uploaded/default/nft_origin"},
                    status=400,
                )
        reward_image_ref = None
        if reward_image_ref_raw not in (None, ""):
            reward_image_ref = str(reward_image_ref_raw).strip()

        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        if not base_api_cookies:
            return Response(
                {"detail": "Authentication credentials were not provided. Please login first."},
                status=401,
            )

        base_api_url = settings.BASE_API_URL.rstrip("/")
        headers = {"Referer": base_api_url + "/"}
        csrf_token = base_api_cookies.get("csrftoken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        meta_url = f"{base_api_url}/api/v1/nft/meta/{quote(str(nft_origin))}"
        try:
            get_meta = requests.get(meta_url, headers=headers, cookies=base_api_cookies, timeout=20)
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)

        if get_meta.status_code >= 400:
            try:
                details = get_meta.json()
            except Exception:
                details = {"raw": get_meta.text[:500]}
            return Response({"error": "Failed to fetch metadata", "details": details}, status=get_meta.status_code)

        try:
            meta_payload = get_meta.json()
        except Exception:
            return Response({"error": "Invalid upstream metadata response"}, status=502)

        metadata = {}
        if isinstance(meta_payload, dict):
            metadata = meta_payload.get("metadata", {}) if isinstance(meta_payload.get("metadata"), dict) else {}

        map_meta = metadata.get("MAP", {}) if isinstance(metadata.get("MAP"), dict) else {}
        sub_type_data_raw = map_meta.get("subTypeData")
        sub_type_data = {}
        if isinstance(sub_type_data_raw, dict):
            sub_type_data = sub_type_data_raw
        elif isinstance(sub_type_data_raw, str):
            try:
                parsed_sub = json.loads(sub_type_data_raw)
                if isinstance(parsed_sub, dict):
                    sub_type_data = parsed_sub
            except Exception:
                sub_type_data = {}
        if sub_type_data:
            # additional_info を更新（存在する場合）
            additional_info_obj = sub_type_data.get("additional_info")
            if isinstance(additional_info_obj, str):
                try:
                    additional_info_obj = json.loads(additional_info_obj)
                except Exception:
                    additional_info_obj = {}
            elif not isinstance(additional_info_obj, dict):
                additional_info_obj = {}
            if reward_image_source is not None:
                additional_info_obj["reward_image_source"] = reward_image_source
            if reward_image_ref is not None:
                additional_info_obj["reward_image_ref"] = reward_image_ref
            if additional_info_obj:
                sub_type_data["additional_info"] = additional_info_obj

            if layout_payload is not None:
                sub_type_data["ticket_design_layout"] = layout_payload
            if extra_metadata_payload is not None:
                sub_type_data["extra_metadata"] = extra_metadata_payload
            if reward_image_source is not None:
                sub_type_data["reward_image_source"] = reward_image_source
            if reward_image_ref is not None:
                sub_type_data["reward_image_ref"] = reward_image_ref
            map_meta["subTypeData"] = sub_type_data
            metadata["MAP"] = map_meta
        else:
            if layout_payload is not None:
                metadata["ticket_design_layout"] = layout_payload
            if extra_metadata_payload is not None:
                metadata["extra_metadata"] = extra_metadata_payload
            if reward_image_source is not None:
                metadata["reward_image_source"] = reward_image_source
            if reward_image_ref is not None:
                metadata["reward_image_ref"] = reward_image_ref

        try:
            patch_meta = requests.patch(
                meta_url,
                json={"metadata": metadata},
                headers=headers,
                cookies=base_api_cookies,
                timeout=20,
            )
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)

        if patch_meta.status_code >= 400:
            try:
                details = patch_meta.json()
            except Exception:
                details = {"raw": patch_meta.text[:500]}
            return Response({"error": "Failed to update metadata", "details": details}, status=patch_meta.status_code)

        return Response(
            {
                "status": "success",
                "message": "ticket metadata updated",
                "nft_origin": nft_origin,
                "ticket_design_layout": layout_payload,
                "extra_metadata": extra_metadata_payload,
                "reward_image_source": reward_image_source,
                "reward_image_ref": reward_image_ref,
                "ticket_image_url": f"/api/ext/v1/ticket/image/{nft_origin}",
            },
            status=200,
        )


class TicketImageAPIView(APIView):
    def get(self, request, nft_origin: str):
        base_api_url = settings.BASE_API_URL.rstrip("/")
        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        if not base_api_cookies:
            return Response(
                {"detail": "Authentication credentials were not provided. Please login first."},
                status=401,
            )

        url = f"{base_api_url}/api/v1/nft/data/{quote(nft_origin)}?data_format=base64"
        headers = {"Referer": base_api_url + "/"}
        csrf_token = base_api_cookies.get("csrftoken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        try:
            upstream = requests.get(url, headers=headers, cookies=base_api_cookies, timeout=30)
        except requests.RequestException:
            return Response({"error": "Upstream request failed"}, status=502)

        if upstream.status_code >= 400:
            try:
                details = upstream.json()
            except Exception:
                details = {"raw": upstream.text[:500]}
            return Response(
                {"error": "Failed to fetch NFT image", "details": details},
                status=upstream.status_code,
            )

        raw_bytes = b""
        if "application/json" in (upstream.headers.get("content-type") or ""):
            try:
                payload = upstream.json()
            except Exception:
                return Response({"error": "Invalid upstream JSON response"}, status=502)
            b64_data = payload.get("data") if isinstance(payload, dict) else None
            if not b64_data:
                return Response({"error": "NFT image data not found"}, status=404)
            try:
                raw_bytes = base64.b64decode(b64_data)
            except Exception:
                return Response({"error": "Failed to decode NFT image data"}, status=502)
        else:
            raw_bytes = upstream.content

        # メタデータ取得（文字合成用）
        meta_url = f"{base_api_url}/api/v1/nft/meta/{quote(nft_origin)}"
        metadata = {}
        try:
            meta_upstream = requests.get(meta_url, headers=headers, cookies=base_api_cookies, timeout=20)
            if meta_upstream.status_code < 400:
                meta_payload = meta_upstream.json()
                if isinstance(meta_payload, dict):
                    metadata = meta_payload.get("metadata", {}) or {}
        except Exception:
            metadata = {}

        # ベースAPI実装に合わせて MAP.subTypeData を優先して読む
        ticket_data = {}
        map_meta = metadata.get("MAP", {}) if isinstance(metadata.get("MAP"), dict) else {}
        sub_type_data_raw = map_meta.get("subTypeData")
        sub_type_data = {}
        if isinstance(sub_type_data_raw, dict):
            sub_type_data = sub_type_data_raw
        elif isinstance(sub_type_data_raw, str):
            try:
                parsed_sub = json.loads(sub_type_data_raw)
                if isinstance(parsed_sub, dict):
                    sub_type_data = parsed_sub
            except Exception:
                sub_type_data = {}
        if sub_type_data:
            ticket_data = sub_type_data
        elif isinstance(metadata, dict):
            ticket_data = metadata

        # additional_info があれば最優先で採用
        additional_info = ticket_data.get("additional_info") or metadata.get("additional_info")
        if isinstance(additional_info, str):
            try:
                parsed = json.loads(additional_info)
                if isinstance(parsed, dict):
                    ticket_data = parsed
            except Exception:
                pass
        elif isinstance(additional_info, dict):
            ticket_data = additional_info

        disable_qr = bool(getattr(request, "_disable_qr", False))
        reward_mode = bool(getattr(request, "_reward_mode", False))
        debug_mode = str(request.GET.get("debug", "0")).lower() in ("1", "true", "yes", "on")

        def dbg(label, data):
            if not debug_mode:
                return
            try:
                if isinstance(data, (dict, list)):
                    text = json.dumps(data, ensure_ascii=False, default=str)
                else:
                    text = str(data)
            except Exception:
                text = repr(data)
            if len(text) > 1200:
                text = text[:1200] + "...(truncated)"
            print(f"[TicketImage DEBUG] {label}: {text}", flush=True)

        # extra_metadata（または external_info）を取得
        extra_meta = ticket_data.get("extra_metadata")
        if extra_meta is None and isinstance(additional_info, dict):
            extra_meta = additional_info.get("extra_metadata")
        # 呼び名の揺れに対応
        if extra_meta is None:
            extra_meta = ticket_data.get("external_info") or ticket_data.get("external_metadata")
        if isinstance(extra_meta, str):
            try:
                parsed_extra = json.loads(extra_meta)
                extra_meta = parsed_extra if isinstance(parsed_extra, dict) else {}
            except Exception:
                extra_meta = {}
        elif not isinstance(extra_meta, dict):
            extra_meta = {}
        # reward画像では reward_profile を表示元としても使う
        if not extra_meta and isinstance(ticket_data.get("reward_profile"), dict):
            extra_meta = {"reward_profile": ticket_data.get("reward_profile")}

        dbg(
            "metadata parse",
            {
                "nft_origin": nft_origin,
                "reward_mode": reward_mode,
                "subTypeData_type": type(sub_type_data_raw).__name__,
                "ticket_data_keys": sorted(list(ticket_data.keys()))[:40] if isinstance(ticket_data, dict) else str(type(ticket_data)),
                "additional_info_type": type(additional_info).__name__,
                "extra_meta_keys": sorted(list(extra_meta.keys()))[:40] if isinstance(extra_meta, dict) else str(type(extra_meta)),
                "ticket_reward_profile": ticket_data.get("reward_profile") if isinstance(ticket_data.get("reward_profile"), dict) else None,
                "extra_reward_profile": extra_meta.get("reward_profile") if isinstance(extra_meta, dict) and isinstance(extra_meta.get("reward_profile"), dict) else None,
            },
        )

        # レイアウトを解釈（JSON文字列 or dict）
        layout = {}
        layout_raw = ticket_data.get("ticket_design_layout")
        if isinstance(layout_raw, str):
            try:
                parsed_layout = json.loads(layout_raw)
                if isinstance(parsed_layout, dict):
                    layout = parsed_layout
            except Exception:
                layout = {}
        elif isinstance(layout_raw, dict):
            layout = layout_raw

        api_base = getattr(settings, "API_BASE", "http://127.0.0.1:8000").rstrip("/")
        token = quote(str(nft_origin))
        checkin_url = f"{api_base}/api/ext/v1/ticket/checkin?token={token}"

        # 画像へ文字を合成
        try:
            image = Image.open(BytesIO(raw_bytes)).convert("RGBA")
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default()

            def conf(key, default):
                value = layout.get(key, {})
                return value if isinstance(value, dict) else default

            title_c = conf("title", {})
            date_c = conf("event_date", {})
            venue_c = conf("venue", {})
            seat_c = conf("seat", {})

            # キー名ゆれに対応（event_name/event_title, event_date/event_datetime）
            event_name = str(ticket_data.get("event_name") or ticket_data.get("event_title") or "").strip()
            event_date = str(ticket_data.get("event_date") or ticket_data.get("event_datetime") or "").strip()
            venue = str(ticket_data.get("venue") or "").strip()
            seat = str(ticket_data.get("seat") or ticket_data.get("seat_no") or "").strip()

            def draw_label(x, y, text, color="#FFFFFF"):
                if not text:
                    return
                # 背景色に依存せず読めるように細い縁取りを付ける
                draw.text((x, y), text, fill=color, font=font, stroke_width=1, stroke_fill="#000000")

            draw_label(
                int(title_c.get("x", 80)),
                int(title_c.get("y", 70)),
                event_name,
                title_c.get("color", "#FFFFFF"),
            )
            draw_label(
                int(date_c.get("x", 80)),
                int(date_c.get("y", 150)),
                event_date,
                date_c.get("color", "#FFFFFF"),
            )
            draw_label(
                int(venue_c.get("x", 80)),
                int(venue_c.get("y", 190)),
                venue,
                venue_c.get("color", "#FFFFFF"),
            )
            draw_label(
                int(seat_c.get("x", 80)),
                int(seat_c.get("y", 230)),
                f"Seat: {seat}" if seat else "",
                seat_c.get("color", "#FFFFFF"),
            )

            # META情報を右下へ自動配置（extra_metadata / external_info / reward_profile）
            def flatten_meta(prefix, value, out):
                if isinstance(value, dict):
                    for k, v in value.items():
                        new_prefix = f"{prefix}.{k}" if prefix else str(k)
                        flatten_meta(new_prefix, v, out)
                elif isinstance(value, list):
                    out.append(f"{prefix}: {', '.join(map(str, value[:4]))}")
                else:
                    out.append(f"{prefix}: {value}")

            meta_lines = []
            flatten_meta("", extra_meta, meta_lines)
            if reward_mode:
                # reward画像では key:value 形式で見せる（例: reward_type, style, serial_no, campaign_id）
                reward_profile = {}
                reward_ticket = ticket_data.get("ticket", {}) if isinstance(ticket_data.get("ticket"), dict) else {}

                if isinstance(ticket_data.get("reward_profile"), dict):
                    reward_profile = ticket_data.get("reward_profile")
                elif isinstance(extra_meta, dict) and isinstance(extra_meta.get("reward_profile"), dict):
                    reward_profile = extra_meta.get("reward_profile")

                display_pairs = []
                # reward_profile 配下は key をフラット化して表示
                for k, v in reward_profile.items():
                    if v not in (None, "", []):
                        display_pairs.append((str(k), v))
                # reward_profile 以外の top-level も表示（campaign_id など）
                if isinstance(extra_meta, dict):
                    for k, v in extra_meta.items():
                        if k == "reward_profile":
                            continue
                        if v not in (None, "", []):
                            display_pairs.append((str(k), v))
                # reward_metadata 直下にある値（campaign_id など）も補完
                for root_key in ("campaign_id",):
                    root_val = ticket_data.get(root_key)
                    if root_val not in (None, "", []):
                        display_pairs.append((root_key, root_val))
                # fallback（追加情報が少ない場合）
                reward_type = str(reward_ticket.get("reward_type") or reward_profile.get("reward_type") or "checkin_reward")
                reward_for = str(reward_ticket.get("reward_for") or "")
                if reward_type and not any(k == "reward_type" for k, _ in display_pairs):
                    display_pairs.append(("reward_type", reward_type))
                if reward_for and not any(k == "reward_for" for k, _ in display_pairs):
                    display_pairs.append(("reward_for", reward_for[:12] + "..."))

                meta_lines = []
                for k, v in display_pairs:
                    if isinstance(v, list):
                        val = ", ".join(map(str, v[:4]))
                    elif isinstance(v, dict):
                        val = json.dumps(v, ensure_ascii=False)
                    else:
                        val = str(v)
                    meta_lines.append(f"{k}: {val}")
                dbg("reward display_pairs", display_pairs)
            # 長すぎると見切れるので上限を設ける
            meta_lines = [line for line in meta_lines if line and len(line) <= 120][:8]
            dbg("meta_lines_after_limit", meta_lines)
            if meta_lines:
                meta_conf = layout.get("extra_metadata", {}) if isinstance(layout.get("extra_metadata"), dict) else {}
                meta_color = meta_conf.get("color", "#FFFFFF")
                margin_x = int(meta_conf.get("margin_x", 24))
                margin_y = int(meta_conf.get("margin_y", 20))
                line_gap = int(meta_conf.get("line_gap", 4))

                # 右下基準で下から上に積む
                y = image.height - margin_y
                for line in reversed(meta_lines):
                    try:
                        left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
                        text_w = max(0, right - left)
                        text_h = max(0, bottom - top)
                    except Exception:
                        text_w = len(line) * 6
                        text_h = 12
                    x = max(0, image.width - margin_x - text_w)
                    y = max(0, y - text_h)
                    draw.text((x, y), line, fill=meta_color, font=font, stroke_width=1, stroke_fill="#000000")
                    y = max(0, y - line_gap)

            # QRコードを合成（reward画像では無効化）
            if not disable_qr:
                try:
                    import qrcode
                    qr_conf = layout.get("qr", {}) if isinstance(layout.get("qr"), dict) else {}
                    qr_size = int(qr_conf.get("size", 220))
                    qr_padding = int(qr_conf.get("padding", 12))
                    margin_x = int(qr_conf.get("margin_x", 24))
                    margin_y = int(qr_conf.get("margin_y", 40))
                    align = str(qr_conf.get("align", "right")).lower()

                    # x未指定時は align で自動配置（デフォルトは right）
                    if "x" in qr_conf:
                        qr_x = int(qr_conf["x"])
                    elif align == "left":
                        qr_x = margin_x
                    elif align == "center":
                        qr_x = max(0, (image.width - qr_size) // 2)
                    else:
                        qr_x = max(0, image.width - qr_size - qr_padding * 2 - margin_x)

                    # y未指定時は上マージンから配置
                    qr_y = int(qr_conf.get("y", margin_y))

                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=10,
                        border=2,
                    )
                    qr.add_data(checkin_url)
                    qr.make(fit=True)
                    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
                    qr_img = qr_img.resize((qr_size, qr_size))

                    qr_bg = Image.new(
                        "RGBA",
                        (qr_size + qr_padding * 2, qr_size + qr_padding * 2),
                        (255, 255, 255, 255),
                    )
                    qr_bg.paste(qr_img, (qr_padding, qr_padding), qr_img)
                    image.alpha_composite(qr_bg, (max(0, qr_x - qr_padding), max(0, qr_y - qr_padding)))
                except Exception:
                    # QR生成に失敗してもチケット画像返却は継続
                    pass

            buf = BytesIO()
            image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
        except Exception:
            # 合成に失敗した場合は元画像を返す
            png_bytes = raw_bytes

        resp = HttpResponse(png_bytes, content_type="image/png", status=200)
        resp["Content-Disposition"] = f'inline; filename="ticket_{nft_origin}.png"'
        resp["ticket-token"] = token
        resp["checkin_url"] = checkin_url
        return resp


class RewardImageAPIView(TicketImageAPIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(description="Reward image (PNG)"),
            401: OpenApiResponse(description="Authentication credentials were not provided"),
            502: OpenApiResponse(description="Upstream request failed"),
        },
    )
    def get(self, request, nft_origin: str):
        request._disable_qr = True
        request._reward_mode = True
        return super().get(request, nft_origin)


class TicketCheckinTokenQuerySerializer(serializers.Serializer):
    token = serializers.CharField()


class TicketCheckinTokenIssueQuerySerializer(serializers.Serializer):
    nft_origin = serializers.CharField()


class TicketCheckinTokenIssueResponseSerializer(serializers.Serializer):
    nft_origin = serializers.CharField()
    token = serializers.CharField()
    checkin_url = serializers.CharField()


class TicketCheckinRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class TicketCheckinResponseSerializer(serializers.Serializer):
    used = serializers.BooleanField()
    used_at = serializers.CharField(required=False, allow_null=True)
    message = serializers.CharField()
    nft_origin = serializers.CharField(required=False)
    reward_nft = serializers.JSONField(required=False, allow_null=True)


class TicketCheckinTokenAPIView(APIView):
    @extend_schema(
        parameters=[TicketCheckinTokenIssueQuerySerializer],
        responses={
            200: TicketCheckinTokenIssueResponseSerializer,
            400: OpenApiResponse(description="nft_origin required"),
        },
    )
    def get(self, request):
        nft_origin = request.query_params.get("nft_origin")
        if not nft_origin:
            return Response({"error": "nft_origin required"}, status=400)

        api_base = getattr(settings, "API_BASE", "http://127.0.0.1:8000").rstrip("/")
        token = quote(str(nft_origin))
        checkin_url = f"{api_base}/api/ext/v1/ticket/checkin?token={token}"
        return Response(
            {
                "nft_origin": nft_origin,
                "token": token,
                "checkin_url": checkin_url,
            },
            status=200,
        )


class TicketCheckinAPIView(APIView):
    used_tokens = set()

    @extend_schema(
        parameters=[TicketCheckinTokenQuerySerializer],
        responses={
            200: TicketCheckinResponseSerializer,
            400: OpenApiResponse(description="Token required"),
        },
    )
    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"error": "Token required"}, status=400)
        used = token in self.used_tokens
        nft_origin = unquote(str(token))
        return Response(
            {
                "used": used,
                "used_at": "now" if used else None,
                "nft_origin": nft_origin,
                "message": "Already checked in" if used else "Not checked in",
            }
        )

    @extend_schema(
        request=TicketCheckinRequestSerializer,
        responses={
            200: TicketCheckinResponseSerializer,
            400: OpenApiResponse(description="Token required"),
            409: OpenApiResponse(description="Already checked in"),
        },
    )
    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"error": "Token required"}, status=400)
        if token in self.used_tokens:
            return Response({"used": True, "message": "Already checked in"}, status=409)

        nft_origin = unquote(str(token))
        reward_nft = self._create_reward_nft(request, nft_origin)
        self.used_tokens.add(token)
        return Response(
            {
                "used": True,
                "used_at": "now",
                "nft_origin": nft_origin,
                "reward_nft": reward_nft,
                "message": "Check-in successful",
            },
            status=200,
        )

    def _create_reward_nft(self, request, nft_origin: str):
        base_api_cookies = request.session.get("base_api_cookies", {}) or request.COOKIES
        if not base_api_cookies:
            return {"created": False, "reason": "login required"}

        base_api_url = settings.BASE_API_URL.rstrip("/")
        query_obj = getattr(request, "query_params", request.GET)
        debug_mode = str(query_obj.get("debug", "0")).lower() in ("1", "true", "yes", "on")

        def dbg(label, data):
            if not debug_mode:
                return
            try:
                if isinstance(data, (dict, list)):
                    text = json.dumps(data, ensure_ascii=False, default=str)
                else:
                    text = str(data)
            except Exception:
                text = repr(data)
            if len(text) > 1200:
                text = text[:1200] + "...(truncated)"
            print(f"[RewardCreate DEBUG] {label}: {text}", flush=True)

        headers = {"Referer": base_api_url + "/"}
        csrf_token = base_api_cookies.get("csrftoken")
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        meta_url = f"{base_api_url}/api/v1/nft/meta/{quote(str(nft_origin))}"
        try:
            meta_res = requests.get(meta_url, headers=headers, cookies=base_api_cookies, timeout=20)
            meta_res.raise_for_status()
            meta_payload = meta_res.json()
        except Exception as e:
            return {"created": False, "reason": f"metadata fetch failed: {e}"}

        metadata = meta_payload.get("metadata", {}) if isinstance(meta_payload, dict) else {}
        map_meta = metadata.get("MAP", {}) if isinstance(metadata.get("MAP"), dict) else {}
        sub_type_data_raw = map_meta.get("subTypeData")
        sub_type_data = {}
        if isinstance(sub_type_data_raw, dict):
            sub_type_data = sub_type_data_raw
        elif isinstance(sub_type_data_raw, str):
            try:
                parsed_sub = json.loads(sub_type_data_raw)
                if isinstance(parsed_sub, dict):
                    sub_type_data = parsed_sub
            except Exception:
                sub_type_data = {}
        ticket_data = sub_type_data if sub_type_data else metadata

        additional_info = ticket_data.get("additional_info") or metadata.get("additional_info")
        if isinstance(additional_info, str):
            try:
                additional_info = json.loads(additional_info)
            except Exception:
                additional_info = {}
        elif not isinstance(additional_info, dict):
            additional_info = {}
        # 元メタ（subTypeData直下）と additional_info を統合して参照
        source_meta = {}
        if isinstance(ticket_data, dict):
            source_meta.update(ticket_data)
        if isinstance(additional_info, dict):
            source_meta.update(additional_info)
        dbg(
            "source_meta merged",
            {
                "nft_origin": nft_origin,
                "subTypeData_type": type(sub_type_data_raw).__name__,
                "ticket_data_keys": sorted(list(ticket_data.keys()))[:40] if isinstance(ticket_data, dict) else str(type(ticket_data)),
                "additional_info_keys": sorted(list(additional_info.keys()))[:40] if isinstance(additional_info, dict) else str(type(additional_info)),
                "source_meta_keys": sorted(list(source_meta.keys()))[:60] if isinstance(source_meta, dict) else str(type(source_meta)),
            },
        )
        # PATCHで subTypeData 直下に置いた値も優先反映
        if isinstance(ticket_data, dict):
            if ticket_data.get("reward_image_source") not in (None, ""):
                additional_info["reward_image_source"] = ticket_data.get("reward_image_source")
            if ticket_data.get("reward_image_ref") not in (None, ""):
                additional_info["reward_image_ref"] = ticket_data.get("reward_image_ref")

        reward_image_source = str(additional_info.get("reward_image_source", "uploaded") or "uploaded").lower()
        reward_image_ref = str(additional_info.get("reward_image_ref", "") or "").strip()
        reward_payload = None

        if reward_image_source == "uploaded":
            reward_payload = REWARD_IMAGE_STORE.get(str(nft_origin))
            if not reward_payload:
                return {
                    "created": False,
                    "reason": "checkin_reward_image not found for this ticket. set checkin_reward_image on ticket/create or switch reward_image_source",
                }
        elif reward_image_source == "default":
            reward_payload = {
                # 1x1 transparent PNG
                "bytes": bytes.fromhex(
                    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
                    "0000000A49444154789C6360000000020001E221BC330000000049454E44AE426082"
                ),
                "name": "default_reward.png",
                "content_type": "image/png",
            }
        elif reward_image_source == "nft_origin":
            if not reward_image_ref:
                return {"created": False, "reason": "reward_image_ref required for reward_image_source=nft_origin"}
            ref_url = f"{base_api_url}/api/v1/nft/data/{quote(reward_image_ref)}?data_format=base64"
            try:
                ref_res = requests.get(ref_url, headers=headers, cookies=base_api_cookies, timeout=30)
                ref_res.raise_for_status()
                ref_payload = ref_res.json()
                ref_b64 = ref_payload.get("data") if isinstance(ref_payload, dict) else None
                if not ref_b64:
                    return {"created": False, "reason": "reward image nft has no data"}
                reward_payload = {
                    "bytes": base64.b64decode(ref_b64),
                    "name": f"reward_from_{reward_image_ref}.png",
                    "content_type": "image/png",
                }
            except Exception as e:
                return {"created": False, "reason": f"failed to fetch reward image from nft_origin: {e}"}
        else:
            return {"created": False, "reason": f"unknown reward_image_source: {reward_image_source}"}

        reward_profile = {}
        reward_extra_metadata = {}
        extra_meta = source_meta.get("extra_metadata")
        if isinstance(extra_meta, str):
            try:
                parsed_extra = json.loads(extra_meta)
                extra_meta = parsed_extra if isinstance(parsed_extra, dict) else {}
            except Exception:
                extra_meta = {}
        if extra_meta in (None, ""):
            extra_meta = source_meta.get("external_info") or source_meta.get("external_metadata")
        if isinstance(extra_meta, str):
            try:
                parsed_extra = json.loads(extra_meta)
                extra_meta = parsed_extra if isinstance(parsed_extra, dict) else {}
            except Exception:
                extra_meta = {}
        if isinstance(extra_meta, dict):
            reward_extra_metadata = extra_meta
            reward_profile = extra_meta.get("reward_profile", {}) if isinstance(extra_meta.get("reward_profile"), dict) else {}
        elif isinstance(extra_meta, str):
            try:
                parsed_extra = json.loads(extra_meta)
                if isinstance(parsed_extra, dict):
                    reward_extra_metadata = parsed_extra
                    reward_profile = parsed_extra.get("reward_profile", {}) if isinstance(parsed_extra.get("reward_profile"), dict) else {}
            except Exception:
                reward_extra_metadata = {}
                reward_profile = {}
        # 追加フォールバック:
        # 元チケットのsubTypeData直下に reward_profile / campaign_id があるケースも拾う
        if not reward_extra_metadata and isinstance(source_meta, dict):
            candidate = {}
            if isinstance(source_meta.get("reward_profile"), dict):
                candidate["reward_profile"] = source_meta.get("reward_profile")
            if source_meta.get("campaign_id") not in (None, ""):
                candidate["campaign_id"] = source_meta.get("campaign_id")
            if candidate:
                reward_extra_metadata = candidate
            if not reward_profile and isinstance(candidate.get("reward_profile"), dict):
                reward_profile = candidate.get("reward_profile", {})

        reward_metadata = {
            "ticket": {
                "reward_for": nft_origin,
                "reward_type": (
                    reward_profile.get("reward_type")
                    or source_meta.get("reward_type")
                    or "checkin_reward"
                ),
            },
            "reward_profile": reward_profile,
            # 元チケット側の extra_metadata をそのまま保持（campaign_id など）
            "extra_metadata": reward_extra_metadata,
            "campaign_id": (
                reward_extra_metadata.get("campaign_id", "")
                if isinstance(reward_extra_metadata, dict)
                else source_meta.get("campaign_id", "")
            ),
            "event_name": source_meta.get("event_name", ""),
            "event_date": source_meta.get("event_date", ""),
            "venue": source_meta.get("venue", ""),
            "seat": source_meta.get("seat", ""),
        }
        dbg(
            "reward metadata payload",
            {
                "reward_image_source": reward_image_source,
                "reward_image_ref": reward_image_ref,
                "reward_profile": reward_profile,
                "reward_extra_metadata": reward_extra_metadata,
                "reward_metadata": reward_metadata,
            },
        )

        files = {
            "file": (
                reward_payload.get("name", "checkin_reward.png"),
                reward_payload.get("bytes", b""),
                reward_payload.get("content_type", "image/png"),
            )
        }
        data = {
            "app": "Ticket System Reward",
            "name": f"Check-in Reward {nft_origin[:8]}",
            "additional_info": json.dumps(reward_metadata, ensure_ascii=False),
        }
        recipient_paymail = source_meta.get("holder_paymail", "")
        if recipient_paymail:
            data["recipient_paymail"] = recipient_paymail

        create_url = f"{base_api_url}/api/v1/nft/create"
        try:
            reward_res = requests.post(
                create_url,
                files=files,
                data=data,
                headers=headers,
                cookies=base_api_cookies,
                timeout=60,
            )
        except Exception as e:
            return {"created": False, "reason": f"reward mint failed: {e}"}

        try:
            reward_data = reward_res.json()
        except Exception:
            reward_data = {"raw": reward_res.text[:500]}

        if reward_res.status_code >= 400:
            return {"created": False, "reason": "reward mint failed", "details": reward_data}

        return {
            "created": True,
            "source": reward_image_source,
            "source_ref": reward_image_ref,
            "nft_origin": (reward_data.get("nft_information", {}) or {}).get("nft_origin"),
            "transaction_id": reward_data.get("transaction_id"),
        }
EOF

cat > ticket_service/urls.py <<'EOF'
from django.urls import path
from .views import (
    AuthLoginProxyAPIView,
    AuthLogoutProxyAPIView,
    AuthUserProxyAPIView,
    TicketCreateAPIView,
    TicketLayoutPatchAPIView,
    TicketImageAPIView,
    RewardImageAPIView,
    TicketCheckinTokenAPIView,
    TicketCheckinAPIView,
)

urlpatterns = [
    path("ext/v1/auth/login", AuthLoginProxyAPIView.as_view()),
    path("ext/v1/auth/logout", AuthLogoutProxyAPIView.as_view()),
    path("ext/v1/auth/user", AuthUserProxyAPIView.as_view()),
    path("ext/v1/ticket/create", TicketCreateAPIView.as_view()),
    path("ext/v1/ticket/layout", TicketLayoutPatchAPIView.as_view()),
    path("ext/v1/ticket/image/<str:nft_origin>", TicketImageAPIView.as_view()),
    path("ext/v1/reward/image/<str:nft_origin>", RewardImageAPIView.as_view()),
    path("ext/v1/ticket/checkin/token", TicketCheckinTokenAPIView.as_view()),
    path("ext/v1/ticket/checkin", TicketCheckinAPIView.as_view()),
]
EOF

cat > mysite/urls.py <<'EOF'
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

def health(_):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", health),
    path("api/", include("ticket_service.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
EOF
```

---

## セル10（コードセル）: ローカルAPIの起動（未起動なら）
```python
# Cell 10
# manage.py がある作業ディレクトリで起動
%cd /content/drive/MyDrive/colabo/tickets-handson

# 初回テーブル作成（django_session を含む）
!python manage.py makemigrations
!python manage.py migrate

# 既存プロセスを停止してから起動（古いURL設定の残留を防ぐ）
get_ipython().system_raw("pkill -f 'manage.py runserver' || true")
get_ipython().system_raw("python manage.py runserver 0.0.0.0:8000 &")
print("runserver started on 0.0.0.0:8000")


%%bash
# Cell 10 (cloudflared)
pkill -f cloudflared || true
echo "cloudflared stopped"
cd /content
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://localhost:8000



```

---

## セル11（コードセル）: 起動後スモークテスト（必須）
```python
# Cell 11
import requests

for p in ["/healthz", "/api/schema/", "/swagger/"]:
    r = requests.get("http://127.0.0.1:8000" + p, timeout=10)
    print(p, r.status_code)

# 期待値: すべて 200
```

---

## セル12（コードセル）: セッション付きHTTPクライアント準備
```python
# Cell 12
import json
import requests
from urllib.parse import urlparse, parse_qs

session = requests.Session()
session.headers.update({"Accept": "application/json"})

def api_get(path, **kwargs):
    url = f"{API_BASE}{path}"
    res = session.get(url, timeout=30, **kwargs)
    print("GET", url, "->", res.status_code)
    return res

def api_post(path, json_body=None, data=None, files=None, **kwargs):
    url = f"{API_BASE}{path}"
    res = session.post(url, json=json_body, data=data, files=files, timeout=60, **kwargs)
    print("POST", url, "->", res.status_code)
    return res
```

---

## セル13（コードセル）: API疎通確認（OpenAPI schema）
```python
# Cell 13
r = api_get("/api/schema/")
print(r.text[:300])
r.raise_for_status()
```

---

## セル14（コードセル）: ログイン（`POST /api/ext/v1/auth/login`）
```python
# Cell 14
payload = {"username": USERNAME, "password": PASSWORD}
r = api_post("/api/ext/v1/auth/login", json_body=payload)
print(r.text[:500])
r.raise_for_status()
```

---

## セル15（コードセル）: ユーザー情報確認（`GET /api/ext/v1/auth/user`）
```python
# Cell 15
r = api_get("/api/ext/v1/auth/user")
print(r.text[:500])
r.raise_for_status()
```

---

## セル16（コードセル）: チケットNFT作成（背景画像 + テンプレート指定）
```python
# Cell 16
# 背景画像を作成（1x1 PNG）
png_path = WORK_DIR / "template.png"
png_bytes = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000A49444154789C6360000000020001E221BC330000000049454E44AE426082"
)
with open(png_path, "wb") as f:
    f.write(png_bytes)

# チェックイン報酬画像（任意）
# ここで指定した画像が、checkin時の reward NFT 画像として使用される。
# 運用推奨: 画像そのものは additional_info に入れず、API側メモリ/ストレージで管理する。
reward_png_path = WORK_DIR / "reward.png"
with open(reward_png_path, "wb") as f:
    f.write(png_bytes)

# レイアウトサンプル（JSON文字列）
layout_samples = {
    "event_info_card": "{\"title\":{\"x\":80,\"y\":70,\"font_size\":44},\"event_date\":{\"x\":80,\"y\":150,\"font_size\":28},\"venue\":{\"x\":80,\"y\":190,\"font_size\":24},\"seat\":{\"x\":480,\"y\":190,\"font_size\":28,\"align\":\"right\"}}",
}

# 使いたいキーを選択
selected_layout_key = "event_info_card"

create_data = {
    "event_name": "Colab Hands-on Live",
    "event_date": "2026-03-01T19:00:00+09:00",
    "venue": "Tokyo Hall",
    "seat": "A-12",
    "ticket_design_name": "default-template",
    "ticket_design_layout": layout_samples[selected_layout_key],
    # reward画像の指定方法:
    # - uploaded: checkin_reward_image を使用（推奨）
    # - default: 既定の画像を使用
    # - nft_origin: reward_image_ref で指定したNFT画像を使用
    "reward_image_source": "uploaded",
    "reward_image_ref": "",
    # reward向け拡張メタ: リトグラフ風シリアルNOなど
    "extra_metadata": json.dumps(
        {
            "reward_profile": {
                "style": "lithograph",
                "serial_no": "LTG-2026-000123",
                "edition_total": 500,
            },
            "campaign_id": "movie-checkin-2026",
            "reward_title": "Check-in Commemorative Lithograph",
        },
        ensure_ascii=False,
    ),
}

with open(png_path, "rb") as fp, open(reward_png_path, "rb") as rp:
    files = {
        "template_image": ("template.png", fp, "image/png"),
        "checkin_reward_image": ("reward.png", rp, "image/png"),  # reward_image_source=uploaded の場合に使用
    }
    r = api_post("/api/ext/v1/ticket/create", data=create_data, files=files)

print(r.text[:1000])
r.raise_for_status()
create_result = r.json()
```

---

## セル17（コードセル）: `nft_origin` と `token` を抽出
```python
# Cell 17
nft_origin = create_result.get("nft_origin")
checkin_url = create_result.get("checkin_url", "")

if not nft_origin:
    raise ValueError("nft_origin not found in create response")

token = None
if checkin_url:
    parsed = urlparse(checkin_url)
    token = parse_qs(parsed.query).get("token", [None])[0]

print("nft_origin =", nft_origin)
print("token =", token)
```

---

## セル18（コードセル）: チケット画像取得（`GET /api/ext/v1/ticket/image/{nft_origin}`）
```python
# Cell 18
r = api_get(f"/api/ext/v1/ticket/image/{nft_origin}")
print("content-type:", r.headers.get("content-type"))
r.raise_for_status()

ticket_png_path = WORK_DIR / "ticket.png"
with open(ticket_png_path, "wb") as f:
    f.write(r.content)

print("saved:", ticket_png_path)
```

---

## セル19（コードセル）: チェックイン状態確認（`GET /api/ext/v1/ticket/checkin?token=...`）
```python
# Cell 19
if not token:
    raise ValueError("token is missing. check create response/checkin_url.")

r = api_get("/api/ext/v1/ticket/checkin", params={"token": token})
print(r.text[:500])
r.raise_for_status()
```

---

## セル20（コードセル）: チェックイン実行（`POST /api/ext/v1/ticket/checkin`）
```python
# Cell 20
r1 = api_post("/api/ext/v1/ticket/checkin", json_body={"token": token})
print("first:", r1.status_code, r1.text[:500])

r2 = api_post("/api/ext/v1/ticket/checkin", json_body={"token": token})
print("second:", r2.status_code, r2.text[:500])  # 既チェックインなら "Already checked in"
```

---

## セル21（コードセル）: ログアウト（`GET /api/ext/v1/auth/logout`）
```python
# Cell 21
r = api_get("/api/ext/v1/auth/logout")
print(r.text[:500])
```

---

## セル22（コードセル）: 実行結果サマリ保存
```python
# Cell 22
summary = {
    "api_base": API_BASE,
    "base_api_url": os.environ.get("BASE_API_URL"),
    "nft_origin": nft_origin,
    "token_exists": bool(token),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

summary_path = WORK_DIR / "handson_result.json"
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("saved:", summary_path)
```

---

## 補足（appフォルダ対応表）
- ルーティング参照: `app/ticket_service/urls.py`
- ログイン/ログアウト/ユーザー取得: `AuthLoginProxyAPIView` / `AuthLogoutProxyAPIView` / `AuthUserProxyAPIView`
- チケット作成: `TicketCreateAPIView`
- 画像取得: `TicketImageAPIView`
- チェックイン: `TicketCheckinAPIView`
- ベースAPI接続先設定: `app/ticket_system/settings.py` の `BASE_API_URL`
