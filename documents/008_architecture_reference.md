# 拡張APIサーバー設計書（独立版）

> v1-start メモ  
> この資料は詳細設計書です。ハンズオン中は最初から全文を読む必要はありません。  
> 基本は `documents/003_goal_steps_ai_pairing.md` で進め、設計の根拠を確認したいときに該当章だけ参照してください。

AI相談テンプレ:

```text
v1-start の実装中に設計判断で迷っています。
論点: ...
今の実装案: ...
008_architecture_reference.md の該当章: ...
Goalに最短で到達するための選択肢を2つ比較してください。
```

## シナリオ（フロー）

管理者：
　チケットデザイン登録　
ユーザ：
　アカウント作成・ログイン
管理者：
　NFTチケット作成（Meta登録）
ユーザ：
　NFT一覧→画像表示→WOC確認
　トークン取得
　チェックイン（管理者の代わりに自身でもOK)


## ドキュメント情報

| 項目 | 内容 |
| --- | --- |
| 目的 | ベースAPIから独立した拡張APIサーバーの設計指針を示す |
| 対象読者 | API/インフラ/運用担当、実装担当 |
| 想定スタック | Django + DRF（拡張API） |
| 適用範囲 | 拡張APIのみ（ベースAPIは変更しない） |

## 読者とスコープ

本設計書は単体で読めることを前提に、拡張APIの構成・実装指針・運用構成をまとめます。ベースAPIの詳細実装は扱わず、連携インターフェースのみを記述します。

## 用語

- **ベースAPI**: 既存のウォレット/NFT機能を提供するAPIサーバー
- **拡張API**: チケット機能を提供する独立APIサーバー
- **拡張機能**: チケット画像生成、チェックイン、TicketDesign管理

## 概要

このドキュメントでは、ベースAPIを変更せずに拡張機能を外部APIサーバーとして分離する設計案を説明します。本設計では**インポートではなくHTTP API経由でベースAPIを呼び出す**ことで、拡張機能を完全に独立したAPIサーバーとして実装します。
マイクロサービス型アーキテクチャ化を前提に実装します。


## 目的

- **ベースAPIの変更を最小限に**: 既存の`hd_wallet`アプリに影響を与えずに拡張機能を追加
- **完全な分離**: 拡張機能を独立したプロジェクトとして開発・デプロイ
- **スケーラビリティ**: 拡張APIを独立してスケール可能
- **技術選択の自由度**: 拡張APIは異なる技術スタックでも実装可能

## アーキテクチャ概要

```
┌─────────────────────────────────┐
│  ベースAPI (betawallet-dev)     │
│  - NFT作成/送付/一覧            │
│  - ウォレット管理               │
│  - 認証・認可                   │
│  - ユーザー管理                 │
│  - データベース: PostgreSQL     │
└──────────────┬──────────────────┘
               │ HTTP API (Session Cookie)
               │
┌──────────────▼──────────────────┐
│  拡張API (ticket-extension-api) │
│  - チケット画像生成             │
│  - チェックイン処理             │
│  - TicketDesign管理             │
│  - データベース: SQLite/PostgreSQL│
└─────────────────────────────────┘
```

### 通信フロー

1. **クライアント → 拡張API**: チケット画像リクエスト（セッションクッキー付き）
2. **拡張API → ベースAPI**: NFT情報取得（セッションクッキーを転送）
3. **拡張API**: チケット画像生成（独自ロジック）
4. **拡張API → クライアント**: PNG画像を返却

## プロジェクト構造

### ベースAPI（変更なし）

```
betawallet-dev/
├── app/
│   ├── hd_wallet/          # ベース機能（変更なし）
│   │   ├── models.py       # NFT, User, Wallet等
│   │   ├── services/       # NFTService, WalletService
│   │   └── views.py        # ベースAPIエンドポイント
│   └── yp_wallet/
└── requirements.txt
```

### 拡張API（新規プロジェクト）

```
ticket-extension-api/
├── app/
│   ├── ticket_service/
│   │   ├── __init__.py
│   │   ├── views.py               # APIエンドポイント
│   │   ├── models.py              # TicketDesignモデル
│   │   ├── admin.py               # Django Admin設定
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── base_api_client.py    # ベースAPI呼び出しクライアント
│   │   │   └── ticket_service.py     # チケット画像生成ロジック
│   │   └── urls.py
│   └── config/
│       ├── __init__.py
│       ├── settings.py            # Django設定
│       ├── urls.py                 # ルートURL設定
│       └── wsgi.py
├── manage.py
├── requirements.txt
└── README.md
```

### 参考: 既存環境の配置例（任意）

本設計は特定のディレクトリ構成に依存しません。既存環境の配置例を以下に示します。

```
[ベースAPI]
/mnt/extra/betawallet-dev   開発環境
/mnt/extra/betawallet       本番環境

[拡張API]
/mnt/extra/ticket_system-dev   開発環境
/mnt/extra/ticket_system       本番環境
```

## 実装の詳細設計

### 1. ベースAPI呼び出しクライアント

拡張APIからベースAPIを呼び出すためのクライアントクラスを実装します。

```python
# app/ticket_service/services/base_api_client.py
import requests
import json
import logging
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

class BaseAPIClient:
    """
    ベースAPI (betawallet-dev) を呼び出すクライアント
    
    このクラスは、拡張APIからベースAPIのエンドポイントを
    HTTP経由で呼び出すためのラッパーです。
    """
    
    def __init__(self, base_url: str = None):
        """
        Args:
            base_url: ベースAPIのベースURL（例: https://api.example.com）
                     省略時はsettings.BASE_API_URLを使用（.envファイルから読み込み）
        """
        self.base_url = base_url or settings.BASE_API_URL
        if not self.base_url:
            raise ValueError(
                "BASE_API_URL must be set in settings or .env file. "
                "Please add BASE_API_URL=http://localhost:8000 to your .env file."
            )
        self.base_url = self.base_url.rstrip('/')
    
    def _get_headers(self, session_cookies: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """リクエストヘッダーを生成"""
        headers = {'Content-Type': 'application/json'}
        # セッション認証の場合は、クッキーをヘッダーに含める必要はない
        # requests.Session()が自動的にクッキーを管理する
        return headers
    
    def get_nft(
        self, 
        nft_origin: str, 
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        ベースAPIからNFT情報を取得
        
        GET /api/v1/nft/{nft_origin}
        
        Args:
            nft_origin: NFTのオリジンID
            session_cookies: セッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        
        Returns:
            NFT情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/nft/{nft_origin}"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        for cookie_name, cookie_value in session_cookies.items():
            session.cookies.set(cookie_name, cookie_value, domain=self._get_cookie_domain())
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"NFT not found: {nft_origin}")
            else:
                logger.error(f"HTTP error fetching NFT {nft_origin}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch NFT {nft_origin}: {e}")
            return None
    
    def _get_cookie_domain(self) -> str:
        """クッキーのドメインを取得（設定から、またはデフォルト）"""
        from django.conf import settings
        # 同じドメインの場合はNoneを返す（クッキーが自動的に送信される）
        # 異なるドメインの場合は、設定から取得
        return getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    
    def get_user_nfts(
        self, 
        session_cookies: Dict[str, str], 
        wallet_type: str = "BSV"
    ) -> list:
        """
        ユーザーのNFT一覧を取得
        
        GET /api/v1/nft/user
        
        Args:
            session_cookies: セッションクッキーの辞書
            wallet_type: ウォレットタイプ（デフォルト: BSV）
        
        Returns:
            NFT一覧のリスト
        """
        url = f"{self.base_url}/api/v1/nft/user"
        headers = self._get_headers()
        params = {'wallet_type': wallet_type}
        
        # セッションクッキーを設定
        session = requests.Session()
        for cookie_name, cookie_value in session_cookies.items():
            session.cookies.set(cookie_name, cookie_value, domain=self._get_cookie_domain())
        
        try:
            response = session.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('nfts', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch user NFTs: {e}")
            return []
    
    def update_nft_metadata(
        self, 
        nft_origin: str, 
        metadata_updates: Dict, 
        session_cookies: Dict[str, str]
    ) -> bool:
        """
        NFTのメタデータを更新（チェックイン状態など）
        
        PATCH /api/v1/nft/{nft_origin}/metadata
        
        Args:
            nft_origin: NFTのオリジンID
            metadata_updates: 更新するメタデータの辞書
            session_cookies: セッションクッキーの辞書
        
        Returns:
            更新成功時True、失敗時False
        """
        url = f"{self.base_url}/api/v1/nft/{nft_origin}/metadata"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        for cookie_name, cookie_value in session_cookies.items():
            session.cookies.set(cookie_name, cookie_value, domain=self._get_cookie_domain())
        
        # CSRFトークンが必要な場合は、ヘッダーに追加
        if 'csrftoken' in session_cookies:
            headers['X-CSRFToken'] = session_cookies['csrftoken']
        
        try:
            response = session.patch(
                url, 
                json=metadata_updates, 
                headers=headers, 
                timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update NFT metadata {nft_origin}: {e}")
            return False
    
    def create_reward_nft(
        self,
        image_file: bytes,
        image_filename: str,
        metadata: Dict,
        recipient_paymail: str,
        session_cookies: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        報酬NFTを作成（チェックイン報酬用）
        
        POST /api/v1/nft/create
        
        Args:
            image_file: 画像ファイルのバイトデータ
            image_filename: 画像ファイル名
            metadata: NFTメタデータ
            recipient_paymail: 受領者のpaymail
            session_cookies: セッションクッキーの辞書
        
        Returns:
            作成されたNFT情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/nft/create"
        headers = {}
        
        # セッションクッキーを設定
        session = requests.Session()
        for cookie_name, cookie_value in session_cookies.items():
            session.cookies.set(cookie_name, cookie_value, domain=self._get_cookie_domain())
        
        # CSRFトークンが必要な場合は、ヘッダーに追加
        if 'csrftoken' in session_cookies:
            headers['X-CSRFToken'] = session_cookies['csrftoken']
        
        files = {
            'file': (image_filename, image_file, 'image/png')
        }
        data = {
            'app': 'Ticket System',
            'name': 'Check-in Reward',
            'additional_info': json.dumps(metadata),
            'recipient_paymail': recipient_paymail
        }
        
        try:
            response = session.post(
                url, 
                files=files, 
                data=data, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create reward NFT: {e}")
            return None
    
    def get_user_info(self, session_cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        セッションからユーザー情報を取得
        
        GET /api/v1/auth/user
        
        Args:
            session_cookies: セッションクッキーの辞書
        
        Returns:
            ユーザー情報の辞書、またはNone（エラー時）
        """
        url = f"{self.base_url}/api/v1/auth/user"
        headers = self._get_headers()
        
        # セッションクッキーを設定
        session = requests.Session()
        for cookie_name, cookie_value in session_cookies.items():
            session.cookies.set(cookie_name, cookie_value, domain=self._get_cookie_domain())
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user info: {e}")
            return None
```

### 2. チケットサービス（画像生成ロジック）

ベースAPIから取得したNFT情報を使って、チケット画像を生成します。

```python
# app/ticket_service/services/ticket_service.py
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, Any, Optional, Tuple

from django.core import signing
from PIL import Image, ImageDraw, ImageFont

from ticket_service.models import TicketDesign

DEFAULT_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24  # 24h
DEFAULT_SIGNING_SALT = "hd_wallet.ticket.checkin"


@dataclass(frozen=True)
class TicketPayload:
    """チケット情報のデータクラス"""
    ticket_id: str = ""
    event_title: str = ""
    event_datetime: str = ""
    venue: str = ""
    seat: str = ""
    holder_name: str = ""


class TicketService:
    """
    チケット画像生成サービス
    
    - チェックイントークンの生成・検証
    - NFTメタデータからチケット情報を抽出
    - チケット画像（PNG）の生成
    """
    
    def __init__(
        self,
        signing_salt: str = DEFAULT_SIGNING_SALT,
        token_max_age_seconds: int = DEFAULT_TOKEN_MAX_AGE_SECONDS,
    ):
        self.signing_salt = signing_salt
        self.token_max_age_seconds = token_max_age_seconds
    
    def build_checkin_token(self, nft_origin: str) -> str:
        """チェックイントークンを生成"""
        signer = signing.TimestampSigner(salt=self.signing_salt)
        return signer.sign(nft_origin)
    
    def verify_checkin_token(self, token: str) -> str:
        """チェックイントークンを検証"""
        signer = signing.TimestampSigner(salt=self.signing_salt)
        return signer.unsign(token, max_age=self.token_max_age_seconds)
    
    def extract_ticket_payload_from_metadata(
        self, 
        metadata: Dict[str, Any]
    ) -> TicketPayload:
        """
        NFTメタデータからチケット情報を抽出
        
        Args:
            metadata: ベースAPIから取得したNFTメタデータ
        
        Returns:
            TicketPayloadオブジェクト
        """
        map_meta = metadata.get("MAP", {}) if isinstance(metadata.get("MAP"), dict) else {}
        candidate = map_meta.get("subTypeData")
        
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except Exception:
                candidate = None
        
        ticket: Dict[str, Any] = {}
        if isinstance(candidate, dict):
            inner = candidate.get("ticket")
            ticket = inner if isinstance(inner, dict) else candidate
        
        return TicketPayload(
            ticket_id=str(ticket.get("ticket_id", "") or ""),
            event_title=str(ticket.get("event_title", "") or ""),
            event_datetime=str(ticket.get("event_datetime", "") or ""),
            venue=str(ticket.get("venue", "") or ""),
            seat=str(ticket.get("seat", "") or ""),
            holder_name=str(ticket.get("holder_name", "") or ""),
        )
    
    def render_ticket_png_from_metadata(
        self,
        metadata: Dict[str, Any],
        checkin_url: str,
        design: Optional[TicketDesign] = None,
    ) -> bytes:
        """
        NFTメタデータからチケット画像を生成
        
        Args:
            metadata: ベースAPIから取得したNFTメタデータ
            checkin_url: チェックインURL
            design: チケットデザイン（省略時はアクティブなデザインを使用）
        
        Returns:
            PNG画像のバイトデータ
        """
        design = design or TicketDesign.get_active()
        if not design or not design.template_image:
            raise ValueError("TicketDesign (active) not found")
        
        base = Image.open(design.template_image).convert("RGBA")
        draw = ImageDraw.Draw(base)
        
        layout = (design.layout or {}) if isinstance(design.layout, dict) else {}
        payload = self.extract_ticket_payload_from_metadata(metadata)
        
        font = self._load_font(layout)
        
        # テキストを描画
        lines = self._build_text_lines(payload)
        x, y = self._get_xy(layout.get("text", {}), default=(40, 40))
        line_gap = int(layout.get("text", {}).get("line_gap", 10))
        for line in lines:
            if not line:
                continue
            draw.text(
                (x, y), 
                line, 
                fill=layout.get("text", {}).get("color", "#FFFFFF"), 
                font=font
            )
            y += (font.size if hasattr(font, "size") else 12) + line_gap
        
        # QRコードを描画
        qr_conf = layout.get("qr", {}) if isinstance(layout.get("qr"), dict) else {}
        qr_x, qr_y = self._get_xy(qr_conf, default=(base.width - 320, 40))
        qr_size = int(qr_conf.get("size", 260))
        qr_img = self._build_qr_image(checkin_url, qr_size=qr_size)
        
        # QRコードに白背景を追加
        padding = 20
        qr_with_bg = Image.new(
            "RGBA", 
            (qr_size + padding * 2, qr_size + padding * 2), 
            (255, 255, 255, 255)
        )
        qr_with_bg.paste(qr_img, (padding, padding), qr_img)
        base.alpha_composite(qr_with_bg, (qr_x - padding, qr_y - padding))
        
        out = BytesIO()
        base.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    
    def _build_text_lines(self, p: TicketPayload) -> Tuple[str, ...]:
        """チケット情報からテキスト行を生成"""
        return (
            f"EVENT: {p.event_title}" if p.event_title else "",
            f"DATE: {p.event_datetime}" if p.event_datetime else "",
            f"VENUE: {p.venue}" if p.venue else "",
            f"SEAT: {p.seat}" if p.seat else "",
            f"HOLDER: {p.holder_name}" if p.holder_name else "",
            f"TICKET ID: {p.ticket_id}" if p.ticket_id else "",
        )
    
    def _load_font(self, layout: Dict[str, Any]):
        """フォントをロード"""
        text_conf = layout.get("text", {}) if isinstance(layout.get("text"), dict) else {}
        font_path = text_conf.get("font_path")
        font_size = int(text_conf.get("font_size", 28))
        if font_path:
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                pass
        # フォールバック
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
            try:
                return ImageFont.truetype(p, font_size)
            except Exception:
                continue
        return ImageFont.load_default()
    
    def _get_xy(self, conf: Dict[str, Any], default: Tuple[int, int]) -> Tuple[int, int]:
        """設定から座標を取得"""
        try:
            x = int(conf.get("x", default[0]))
            y = int(conf.get("y", default[1]))
            return x, y
        except Exception:
            return default
    
    def _build_qr_image(self, data: str, qr_size: int) -> Image.Image:
        """QRコード画像を生成"""
        try:
            import qrcode
        except Exception as e:
            raise ImportError("qrcode is required to generate ticket QR") from e
        
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        img = img.resize((qr_size, qr_size))
        return img
```

### 3. APIビュー実装

拡張APIのエンドポイントを実装します。

```python
# app/ticket_service/views.py
import logging
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from ticket_service.services.base_api_client import BaseAPIClient
from ticket_service.services.ticket_service import TicketService
from ticket_service.models import TicketDesign

logger = logging.getLogger(__name__)


class TicketImageAPIView(APIView):
    """
    チケット画像生成API
    
    GET /api/ext/v1/ticket/image/<nft_origin>
    
    ベースAPIからNFT情報を取得し、チケット画像を生成して返却します。
    """
    
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, nft_origin: str):
        # セッションクッキーを取得
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # ベースAPIからNFT情報を取得
        api_client = BaseAPIClient()
        nft_data = api_client.get_nft(nft_origin, session_cookies)
        
        if not nft_data:
            return Response(
                {"error": "NFT not found or access denied"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # チケットNFTかどうか確認
        if nft_data.get('app') != 'Ticket System':
            return Response(
                {"error": "Not a ticket NFT"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # チケット画像を生成
        ticket_service = TicketService()
        token_str = ticket_service.build_checkin_token(nft_origin=nft_origin)
        
        # チェックインURLを生成（拡張APIのURL）
        checkin_url = request.build_absolute_uri(
            f"/api/ext/v1/ticket/checkin?token={token_str}"
        )
        
        try:
            # NFTデータからメタデータを抽出
            metadata = nft_data.get('metadata', {})
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
    
    def _extract_session_cookies(self, request) -> Dict[str, str]:
        """
        リクエストからセッションクッキーを抽出
        
        Returns:
            セッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        """
        cookies = {}
        if hasattr(request, 'COOKIES'):
            # セッションIDとCSRFトークンを取得
            session_id = request.COOKIES.get('sessionid')
            csrf_token = request.COOKIES.get('csrftoken')
            
            if session_id:
                cookies['sessionid'] = session_id
            if csrf_token:
                cookies['csrftoken'] = csrf_token
        
        return cookies


class TicketCheckinAPIView(APIView):
    """
    チェックインAPI
    
    GET/POST /api/ext/v1/ticket/checkin
    
    QRコードから取得したトークンでチェックインを実行します。
    ベースAPIのNFTメタデータを更新して、使用済み状態にします。
    """
    
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """GETリクエスト（QRコードスキャン用）"""
        token = request.query_params.get('token')
        if not token:
            return Response(
                {"error": "Token required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return self._process_checkin(request, token)
    
    def post(self, request):
        """POSTリクエスト"""
        token = request.data.get('token')
        if not token:
            return Response(
                {"error": "Token required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return self._process_checkin(request, token)
    
    def _process_checkin(self, request, token: str):
        # トークンを検証
        ticket_service = TicketService()
        try:
            nft_origin = ticket_service.verify_checkin_token(token)
        except Exception as e:
            logger.warning(f"Invalid check-in token: {e}")
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # セッションクッキーを取得
        session_cookies = self._extract_session_cookies(request)
        if not session_cookies:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # ベースAPIからNFT情報を取得
        api_client = BaseAPIClient()
        nft_data = api_client.get_nft(nft_origin, session_cookies)
        
        if not nft_data:
            return Response(
                {"error": "NFT not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 既にチェックイン済みか確認
        metadata = nft_data.get('metadata', {})
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
                        "used_at": timezone.now().isoformat(),
                        "checked_in_by": request.user.username if hasattr(request, 'user') else None
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
                api_client, session_cookies, nft_data, design
            )
        
        return Response({
            "used": True,
            "used_at": updated_metadata["MAP"]["subTypeData"]["ticket"]["used_at"],
            "nft_origin": nft_origin,
            "reward_nft": reward_nft
        })
```

### holder_paymail の自動設定

チェックイン報酬NFTを送付するために、NFTメタデータに `holder_paymail`（チケット所有者のpaymail）が必要です。
この値は**ベースAPI側で自動的に設定**されます。

#### 設定タイミング

| タイミング | 処理内容 | 設定場所 |
|-----------|---------|---------|
| **NFT作成時** | `recipient_paymail`が指定されている場合、`metadata.map.subTypeData.ticket.holder_paymail`に自動設定 | `CreateNFTAPIView` |
| **NFT転送時（Paymail）** | 転送先の`recipient_paymail`で`holder_paymail`を更新 | `SendNFTPaymailAPIView` |

#### メタデータ構造

```json
{
  "map": {
    "app": "ticket_system",
    "name": "Concert Ticket #001",
    "type": "ord",
    "subType": "collectionItem",
    "subTypeData": {
      "ticket": {
        "event_name": "Summer Festival 2026",
        "event_date": "2026-08-15",
        "holder_paymail": "user@example.com",
        "used_at": null,
        "checked_in_by": null
      }
    }
  }
}
```

#### ベースAPI側の実装（CreateNFTAPIView）

```python
# additional_infoにholder_paymailを追加（チケットシステム用）
additional_info = validated_data.get('additional_info') or ''
recipient_paymail = validated_data.get('recipient_paymail')
if recipient_paymail:
    try:
        import json
        info_dict = json.loads(additional_info) if additional_info else {}
        if isinstance(info_dict, dict):
            if 'ticket' not in info_dict:
                info_dict['ticket'] = {}
            info_dict['ticket']['holder_paymail'] = recipient_paymail
            additional_info = json.dumps(info_dict)
    except (json.JSONDecodeError, TypeError):
        import json
        info_dict = {
            'original_info': additional_info,
            'ticket': {'holder_paymail': recipient_paymail}
        }
        additional_info = json.dumps(info_dict)
```

#### ベースAPI側の実装（SendNFTPaymailAPIView）

```python
# メタデータのholder_paymailを更新（チケットシステム用）
recipient_paymail = form.get_recipient_paymail()
if recipient_paymail:
    try:
        import json
        current_metadata = user_nft.metadata or {}
        map_data = current_metadata.get('map', {})
        subtype_data = map_data.get('subTypeData', {})
        
        if isinstance(subtype_data, str):
            try:
                subtype_data = json.loads(subtype_data)
            except (json.JSONDecodeError, TypeError):
                subtype_data = {}
        
        if isinstance(subtype_data, dict):
            if 'ticket' not in subtype_data:
                subtype_data['ticket'] = {}
            subtype_data['ticket']['holder_paymail'] = recipient_paymail
            
            map_data['subTypeData'] = subtype_data
            current_metadata['map'] = map_data
            user_nft.metadata = current_metadata
            user_nft.save(update_fields=['metadata', 'updated_at'])
    except Exception as e:
        logger.warning(f"Failed to update holder_paymail: {e}")
```

### チェックイン報酬NFT送付

#### 報酬NFT送付の条件

チェックイン時に報酬NFTを自動送付するには、以下の**3つの条件すべて**を満たす必要があります：

| 条件 | 説明 | 確認方法 |
|------|------|---------|
| **1. TicketDesignが設定されている** | `TicketDesign.get_active()` でアクティブなデザインが取得できる必要がある | Django Admin または `TicketDesign.objects.filter(is_active=True).exists()` |
| **2. checkin_reward_imageが設定されている** | `design.checkin_reward_image` に報酬用の画像がアップロードされている必要がある | Django Admin で画像をアップロード |
| **3. NFTメタデータにholder_paymailが含まれている** | `metadata.map.subTypeData.ticket.holder_paymail` に受領者のpaymailが必要 | NFT作成時に`recipient_paymail`を指定、または転送時に自動設定 |

#### 報酬NFTが送付されない場合（`reward_nft: null`）

チェックインAPIのレスポンスで `"reward_nft": null` が返される場合、以下のいずれかが原因です：

1. **TicketDesignが設定されていない**
   - Django Adminで`TicketDesign`を作成し、`is_active=True`に設定

2. **checkin_reward_imageが設定されていない**
   - Django Adminで`TicketDesign`の`checkin_reward_image`フィールドに画像をアップロード

3. **NFTメタデータにholder_paymailがない**
   - NFT作成時に`recipient_paymail`を指定していない
   - 古いNFT（`holder_paymail`自動設定機能追加前に作成されたもの）

#### 確認コマンド

```bash
# TicketDesignの状態を確認
docker compose exec ticket_web python -c "
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ticket_system.settings'
import django
django.setup()

from ticket_service.models import TicketDesign

design = TicketDesign.get_active()
if design:
    print(f'Active design: {design.name}')
    print(f'Has reward image: {bool(design.checkin_reward_image)}')
    if design.checkin_reward_image:
        print(f'Reward image path: {design.checkin_reward_image.path}')
else:
    print('No active TicketDesign found')
"
```

#### 実装コード

```python
    def _send_checkin_reward(
        self, 
        api_client: BaseAPIClient, 
        session_cookies: Dict[str, str], 
        nft_data: Dict, 
        design: TicketDesign
    ):
        """チェックイン報酬NFTを送付"""
        try:
            # 報酬画像を読み込む
            with design.checkin_reward_image.open('rb') as f:
                image_data = f.read()
            
            # 受領者のpaymailを取得（NFTメタデータから）
            metadata = nft_data.get('metadata', {})
            ticket_meta = metadata.get('MAP', {}).get('subTypeData', {})
            if isinstance(ticket_meta, str):
                import json
                try:
                    ticket_meta = json.loads(ticket_meta)
                except:
                    ticket_meta = {}
            
            recipient_paymail = ticket_meta.get('ticket', {}).get('holder_paymail')
            if not recipient_paymail:
                logger.warning("Recipient paymail not found in NFT metadata")
                return None
            
            # 報酬NFTのメタデータ
            reward_metadata = {
                "ticket": {
                    "reward_for": nft_data.get('nft_origin'),
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
    
    def _extract_session_cookies(self, request) -> Dict[str, str]:
        """
        リクエストからセッションクッキーを抽出
        
        Returns:
            セッションクッキーの辞書（例: {'sessionid': '...', 'csrftoken': '...'}）
        """
        cookies = {}
        if hasattr(request, 'COOKIES'):
            # セッションIDとCSRFトークンを取得
            session_id = request.COOKIES.get('sessionid')
            csrf_token = request.COOKIES.get('csrftoken')
            
            if session_id:
                cookies['sessionid'] = session_id
            if csrf_token:
                cookies['csrftoken'] = csrf_token
        
        return cookies
```

### 4. モデル定義

拡張API専用のデータベースモデルを定義します。

```python
# app/ticket_service/models.py
from django.db import models

class TicketDesign(models.Model):
    """
    チケットテンプレートデザイン
    
    拡張API専用のデータベースに保存されます。
    """
    
    name = models.CharField(
        max_length=100, 
        default="Default", 
        help_text="Design name for identification"
    )
    template_image = models.ImageField(
        upload_to="ticket_templates/", 
        null=True, 
        blank=True
    )
    layout = models.JSONField(default=dict, blank=True)
    checkin_reward_image = models.ImageField(
        upload_to="ticket_templates/checkin_rewards/",
        null=True,
        blank=True,
        help_text="Image to be sent as NFT reward after check-in completion"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "ticket_system_ticket_design"
        indexes = [
            models.Index(fields=["is_active"], name="idx_ticket_design_active"),
        ]
    
    def __str__(self):
        return f"TicketDesign {self.id}: {self.name}"
    
    @classmethod
    def get_active(cls):
        """アクティブなデザインを取得"""
        return cls.objects.filter(is_active=True).order_by("-updated_at").first()
```

### デフォルトTicketDesignの自動設定

コンテナ起動時に、デフォルトの`TicketDesign`が自動的に作成されます。

#### 環境変数による設定

`.env`ファイルで以下の環境変数を設定できます：

| 環境変数 | 説明 | デフォルト値 |
|---------|------|-------------|
| `TICKET_DESIGN_NAME` | デザイン名 | `Default` |
| `TICKET_DESIGN_TEMPLATE_IMAGE` | テンプレート画像のパス | なし |
| `TICKET_DESIGN_REWARD_IMAGE` | 報酬画像のパス | なし |
| `TICKET_DESIGN_LAYOUT` | レイアウトJSON | `{}` |

#### .env設定例

```bash
# Ticket Design Settings
TICKET_DESIGN_NAME=MyTicket
TICKET_DESIGN_TEMPLATE_IMAGE=/app/assets/template.png
TICKET_DESIGN_REWARD_IMAGE=/app/assets/reward.png
TICKET_DESIGN_LAYOUT={"text":{"x":40,"y":40,"color":"#FFFFFF"},"qr":{"x":500,"y":40,"size":200}}
```

#### マネジメントコマンド

```bash
# デフォルトデザインを作成（存在しない場合のみ）
python manage.py setup_default_ticket_design

# 既存のデザインを強制更新
python manage.py setup_default_ticket_design --force

# 名前を指定して作成
python manage.py setup_default_ticket_design --name "Concert Ticket"
```

#### 起動時の自動実行

`entrypoint.sh`で起動時に自動的に実行されます：

```bash
#!/bin/bash
# ...

# マイグレーションを実行
echo "Running migrations..."
python manage.py migrate --noinput

# デフォルトのTicketDesignを作成（存在しない場合のみ）
echo "Setting up default TicketDesign..."
python manage.py setup_default_ticket_design || echo "TicketDesign setup skipped or failed"

# サーバーを実行
exec gunicorn ticket_system.wsgi:application --bind 0.0.0.0:8001 ...
```

#### 起動ログ例

```
Setting up default TicketDesign...
Creating new TicketDesign "Default"...
TicketDesign "Default" (id=1) setup complete!
  is_active: True
  has_template_image: False
  has_reward_image: False
```

### 5. Django設定

```python
# app/config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_DIR = BASE_DIR.parent  # .envファイルはプロジェクトルートに配置

# Load environment variables from env files.
# NOTE:
# - Primary file is ".env" (common in Docker / deployment).
# - Local overrides can be placed in "env.local" (no leading dot).
dotenv_path = os.path.join(ENV_DIR, ".env")
env_local_path = os.path.join(ENV_DIR, "env.local")

# Load primary first, then local overrides (if any).
load_dotenv(dotenv_path)
if os.path.exists(env_local_path):
    load_dotenv(env_local_path, override=True)

# Some env files in this repo use "KEY = value" (spaces around '=') and/or quotes.
_DOTENV_VALUES = dict(dotenv_values(dotenv_path))
if os.path.exists(env_local_path):
    _DOTENV_VALUES.update(dotenv_values(env_local_path))


def _get_env(key: str, default=None):
    """環境変数を取得（.envファイルからも読み込み）"""
    val = os.environ.get(key)
    if val is not None and val != "":
        return val
    for k in (key, key.strip(), f"{key} ", f" {key}"):
        v = _DOTENV_VALUES.get(k)
        if v is not None and v != "":
            return v
    return default

# ベースAPIのURL（.envファイルから取得）
# .envファイルに以下を追加:
# BASE_API_URL=http://localhost:8000
BASE_API_URL = _get_env('BASE_API_URL', 'http://localhost:8000')

# セキュリティ設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# データベース（拡張API専用）
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # または PostgreSQL:
        # 'ENGINE': 'django.db.backends.postgresql',
        # 'NAME': os.environ.get('DB_NAME', 'ticket_extension'),
        # 'USER': os.environ.get('DB_USER', 'postgres'),
        # 'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        # 'HOST': os.environ.get('DB_HOST', 'localhost'),
        # 'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'rest_framework',
    'ticket_service',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# REST Framework設定
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# セッション設定（ベースAPIと同じドメイン/設定を使用）
SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_AGE = 1209600  # 2 weeks in seconds
SESSION_COOKIE_SECURE = True  # HTTPS使用時
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# セッションストア（ベースAPIと同じストアを使用する場合）
# 同じドメインの場合は、デフォルトのDBセッションでOK
# 異なるドメインの場合は、Redis等の共有ストアを使用
# SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.redis.RedisCache',
#         'LOCATION': 'redis://localhost:6379/1',
#     }
# }

# メディアファイル設定
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 静的ファイル設定
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
```

### 6. URL設定

```python
# app/config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('ticket_service.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

```python
# app/ticket_service/urls.py
from django.urls import path
from ticket_service.views import TicketImageAPIView, TicketCheckinAPIView

urlpatterns = [
    path(
        'api/ext/v1/ticket/image/<str:nft_origin>', 
        TicketImageAPIView.as_view(), 
        name='ext-ticket-image'
    ),
    path(
        'api/ext/v1/ticket/checkin', 
        TicketCheckinAPIView.as_view(), 
        name='ext-ticket-checkin'
    ),
]
```

### 7. requirements.txt

```txt
Django>=4.2.0
djangorestframework>=3.14.0
Pillow>=10.0.0
qrcode[pil]>=7.4.0
requests>=2.31.0
python-dotenv>=1.0.0
```

### 8. .envファイルの設定

プロジェクトルートに`.env`ファイルを作成し、ベースAPIのURLを設定します。

```bash
# .env
# ベースAPIのベースURL（末尾のスラッシュは不要）
BASE_API_URL=http://localhost:8000

# 本番環境の例:
# BASE_API_URL=https://api.example.com

# 開発環境のローカルオーバーライド（env.local）
# このファイルはgitignoreに追加することを推奨
# BASE_API_URL=http://localhost:8000
```

**注意**: 
- `.env`ファイルは環境ごとに異なる値を設定できます
- `env.local`ファイルを作成すると、`.env`の値を上書きできます（gitignoreに追加推奨）
- `BASE_API_URL`には末尾のスラッシュを含めないでください（コード内で自動的に処理されます）

## デプロイ構成

### 開発環境

```
ベースAPI: http://localhost:8000
拡張API:   http://localhost:8001
```

### 本番環境（推奨構成）

```
┌─────────────────┐
│   Nginx/Gateway │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌───▼──────┐
│ベースAPI│ │ 拡張API │
│:8000  │ │ :8001   │
└───────┘ └─────────┘
```

Nginx設定例:

```nginx
# /etc/nginx/sites-available/ticket-extension
upstream base_api {
    server localhost:8000;
}

upstream extension_api {
    server localhost:8001;
}

server {
    listen 443 ssl;
    server_name api.example.com;
    
    # ベースAPI
    location /api/v1/ {
        proxy_pass http://base_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # 拡張API
    location /api/ext/v1/ {
        proxy_pass http://extension_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## メリット

1. **完全な分離**: ベースAPIに一切の変更を加えずに拡張機能を追加
2. **独立デプロイ**: 拡張APIを独立してデプロイ・スケール可能
3. **技術選択の自由度**: 拡張APIは異なるフレームワーク（Flask、FastAPI等）でも実装可能
4. **データ分離**: 拡張APIは独自のデータベースで管理
5. **チーム分離**: 拡張機能を別チームで開発可能
6. **障害分離**: 拡張APIの障害がベースAPIに影響しない

## デメリット・注意点

1. **ネットワーク遅延**: ベースAPI呼び出しのオーバーヘッド
   - **対策**: キャッシュの導入、非同期処理の活用

2. **認証の複雑さ**: セッションクッキーの共有
   - **対策**: 同じドメインでセッションクッキーを共有、または共有セッションストア（Redis等）を使用

3. **エラーハンドリング**: ベースAPI障害時の対応
   - **対策**: リトライロジック、フォールバック処理

4. **トランザクション**: 複数APIにまたがる整合性
   - **対策**: イベント駆動アーキテクチャ、補償トランザクション

5. **運用の複雑さ**: 複数サーバーの管理
   - **対策**: コンテナ化（Docker）、オーケストレーション（Kubernetes）

## 推奨実装パターン

### 1. API Gatewayパターン（セッション共有）

NginxやKongなどのAPI Gatewayを使用して、セッションクッキーを共有します。
同じドメインで動作させることで、セッションクッキーが自動的に共有されます。

```
クライアント → API Gateway (同一ドメイン) → ベースAPI/拡張API
```

**Nginx設定例（セッションクッキー共有）**:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;
    
    # セッションクッキーのドメインを設定
    location / {
        proxy_pass http://extension_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # クッキーを転送
        proxy_cookie_path / /;
    }
    
    # ベースAPI
    location /api/v1/ {
        proxy_pass http://base_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cookie_path / /;
    }
    
    # 拡張API
    location /api/ext/v1/ {
        proxy_pass http://extension_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cookie_path / /;
    }
}
```

### 2. キャッシュ戦略

NFT情報を一時的にキャッシュして、パフォーマンスを向上させます。

```python
from django.core.cache import cache

class BaseAPIClient:
    def get_nft(self, nft_origin: str, session_cookies: Dict[str, str]):
        # キャッシュキー
        cache_key = f"nft:{nft_origin}"
        
        # キャッシュから取得
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # ベースAPIから取得
        nft_data = self._fetch_from_base_api(nft_origin, session_cookies)
        
        # キャッシュに保存（5分間）
        if nft_data:
            cache.set(cache_key, nft_data, 300)
        
        return nft_data
```

### 3. 非同期処理

報酬NFT送付など、時間のかかる処理は非同期で実行します。

```python
from celery import shared_task

@shared_task
def send_checkin_reward_async(nft_origin, session_cookies, design_id):
    """チェックイン報酬NFTを非同期で送付"""
    # 実装...
    # 注意: セッションクッキーは有効期限があるため、
    # 非同期処理では、ベースAPIの認証方法を再検討する必要がある場合があります
    pass
```

### 4. リトライロジック

ベースAPI呼び出しにリトライロジックを追加します。

```python
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class BaseAPIClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.BASE_API_URL
        self.session = requests.Session()
        
        # リトライ設定
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
```

## 移行手順

既存の`ticket_system`アプリから拡張APIへの移行手順:

1. **新規プロジェクトの作成**
   ```bash
   django-admin startproject ticket_extension_api
   cd ticket_extension_api
   python manage.py startapp ticket_service
   ```

2. **コードの移植**
   - `ticket_service.py`を移植（ベースAPI呼び出しに変更）
   - `models.py`を移植（TicketDesign）
   - `views.py`を移植（BaseAPIClientを使用）

3. **設定の調整**
   - `.env`ファイルに`BASE_API_URL`を設定（例: `BASE_API_URL=http://localhost:8000`）
   - `python-dotenv`を`requirements.txt`に追加済みであることを確認
   - データベース設定を確認

4. **テスト**
   - ベースAPIとの連携テスト
   - エラーハンドリングのテスト

5. **デプロイ**
   - 拡張APIを別サーバーにデプロイ
   - Nginx設定を更新

6. **既存アプリの無効化**
   - `ticket_system`アプリを`INSTALLED_APPS`から削除
   - マイグレーションをロールバック（必要に応じて）

## まとめ

マイクロサービス型アーキテクチャにより、ベースAPIを変更せずに拡張機能を追加できます。完全な分離により、独立した開発・デプロイ・スケーリングが可能になります。

ただし、ネットワーク遅延や認証の複雑さなどの課題もあるため、API Gatewayやキャッシュなどの推奨パターンを活用することが重要です。

