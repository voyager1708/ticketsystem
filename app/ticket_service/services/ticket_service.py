import json
from dataclasses import dataclass
from datetime import timezone
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

from django.core import signing
from django.utils import timezone as dj_timezone

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
            event_title=str(ticket.get("event_title", "") or ticket.get("event_name", "") or ""),
            event_datetime=str(ticket.get("event_datetime", "") or ticket.get("event_date", "") or ""),
            venue=str(ticket.get("venue", "") or ""),
            seat=str(ticket.get("seat", "") or ""),
            holder_name=str(ticket.get("holder_name", "") or ticket.get("holder_paymail", "") or ""),
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
        
        # デザインがない場合はデフォルトの背景を生成
        if not design or not design.template_image:
            # デフォルトの背景（グラデーション風の暗い背景）
            base = Image.new("RGBA", (800, 400), (30, 30, 50, 255))
            layout = {}
        else:
            base = Image.open(design.template_image).convert("RGBA")
            layout = (design.layout or {}) if isinstance(design.layout, dict) else {}
        
        draw = ImageDraw.Draw(base)
        
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
    
    def render_ticket_png_for_creation(
        self,
        event_name: str,
        event_date: str,
        venue: str = "",
        seat: str = "",
        holder_paymail: str = "",
        checkin_url: str = "",
        design: Optional[TicketDesign] = None,
    ) -> bytes:
        """
        チケット作成時に画像を生成（メタデータなしで直接パラメータから生成）
        
        Args:
            event_name: イベント名
            event_date: イベント日時
            venue: 会場名
            seat: 座席情報
            holder_paymail: 所有者のpaymail
            checkin_url: チェックインURL（QRコードに埋め込む）
            design: チケットデザイン（省略時はアクティブなデザインを使用）
        
        Returns:
            PNG画像のバイトデータ
        """
        design = design or TicketDesign.get_active()
        
        # デザインがない場合はデフォルトの背景を生成
        if not design or not design.template_image:
            base = Image.new("RGBA", (800, 400), (30, 30, 50, 255))
            layout = {}
        else:
            base = Image.open(design.template_image).convert("RGBA")
            layout = (design.layout or {}) if isinstance(design.layout, dict) else {}
        
        draw = ImageDraw.Draw(base)
        font = self._load_font(layout)
        
        # テキスト行を構築
        lines = []
        if event_name:
            lines.append(f"EVENT: {event_name}")
        if event_date:
            lines.append(f"DATE: {event_date}")
        if venue:
            lines.append(f"VENUE: {venue}")
        if seat:
            lines.append(f"SEAT: {seat}")
        if holder_paymail:
            lines.append(f"HOLDER: {holder_paymail}")
        
        # テキストを描画
        x, y = self._get_xy(layout.get("text", {}), default=(40, 40))
        line_gap = int(layout.get("text", {}).get("line_gap", 10))
        text_color = layout.get("text", {}).get("color", "#FFFFFF")
        
        for line in lines:
            draw.text((x, y), line, fill=text_color, font=font)
            y += (font.size if hasattr(font, "size") else 12) + line_gap
        
        # QRコードを描画（checkin_urlが指定されている場合）
        if checkin_url:
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
    
    def build_ticket_metadata(
        self,
        event_name: str,
        event_date: str,
        venue: str = "",
        seat: str = "",
        holder_paymail: str = "",
    ) -> Dict[str, Any]:
        """
        チケットNFT用のメタデータを構築
        
        Args:
            event_name: イベント名
            event_date: イベント日時
            venue: 会場名
            seat: 座席情報
            holder_paymail: 所有者のpaymail
        
        Returns:
            additional_info用のメタデータ辞書
        """
        ticket_data = {
            "event_name": event_name,
            "event_date": event_date,
            "created_at": now_iso(),
        }
        
        if venue:
            ticket_data["venue"] = venue
        if seat:
            ticket_data["seat"] = seat
        if holder_paymail:
            ticket_data["holder_paymail"] = holder_paymail
        
        return {"ticket": ticket_data}


def now_iso() -> str:
    return dj_timezone.now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

