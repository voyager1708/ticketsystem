import base64
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


def strip_ordinals_envelope(raw_bytes: bytes) -> bytes:
    """
    Ordinals インスクリプションの生バイトから envelope（ord + content-type 等）を除き、
    HTML 本体だけを返す。ブラウザで開いたときに文字化けしないようにするため。
    """
    if not raw_bytes:
        return raw_bytes
    # HTML の開始位置を探す（大文字小文字を無視）
    lower = raw_bytes.lower()
    for start in (b"<!doctype html", b"<html"):
        idx = lower.find(start)
        if idx != -1:
            return raw_bytes[idx:]
    return raw_bytes

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
        表示用 PNG: メタデータ ＋ TicketDesign（背景画像・layout JSON）＋ QR を PIL で描画する。
        """
        design = design or TicketDesign.get_active()
        if not design or not design.template_image:
            base = Image.new("RGBA", (800, 400), (30, 30, 50, 255))
            layout = {}
        else:
            base = Image.open(design.template_image).convert("RGBA")
            layout = (design.layout or {}) if isinstance(design.layout, dict) else {}
        draw = ImageDraw.Draw(base)
        payload = self.extract_ticket_payload_from_metadata(metadata)
        font = self._load_font(layout)
        lines = self._build_text_lines(payload)
        x, y = self._get_xy(layout.get("text", {}), default=(40, 40))
        line_gap = int(layout.get("text", {}).get("line_gap", 10))
        text_color = layout.get("text", {}).get("color", "#FFFFFF")
        for line in lines:
            if not line:
                continue
            draw.text((x, y), line, fill=text_color, font=font)
            y += (font.size if hasattr(font, "size") else 12) + line_gap
        if checkin_url:
            qr_conf = layout.get("qr", {}) if isinstance(layout.get("qr"), dict) else {}
            qr_x, qr_y = self._get_xy(qr_conf, default=(base.width - 320, 40))
            qr_size = int(qr_conf.get("size", 260))
            qr_img = self._build_qr_image(checkin_url, qr_size=qr_size)
            padding = 20
            qr_with_bg = Image.new(
                "RGBA", (qr_size + padding * 2, qr_size + padding * 2), (255, 255, 255, 255)
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

    def _build_qr_data_url(self, data: str, qr_size: int = 260) -> str:
        """QRコード画像を生成し、data URL として返す（HTML 埋め込み用）"""
        img = self._build_qr_image(data, qr_size)
        out = BytesIO()
        img.convert("RGB").save(out, format="PNG")
        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    def _build_background_block(self, design: Optional[TicketDesign]) -> str:
        """背景用の HTML 断片を返す（base64 画像またはデフォルトの div）。画像以外（HTML 等）が入っている場合は使わずフォールバックする。"""
        if design and design.template_image:
            try:
                with design.template_image.open("rb") as f:
                    raw = f.read()
                # 画像以外（HTML 等）がアップロードされていたら使わない
                if raw[:3] == b"\xff\xd8\xff":
                    mime = "image/jpeg"
                elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                    mime = "image/png"
                else:
                    raw = None
                if raw:
                    b64 = base64.b64encode(raw).decode("ascii")
                    return f'<img class="ticket-bg" src="data:{mime};base64,{b64}" alt="">'
            except Exception:
                pass
        return '<div class="ticket-bg" style="width:100%;height:100%;background:linear-gradient(135deg,#1e1e32 0%,#2a2a42 100%);"></div>'

    def _build_qr_block(self, qr_data_url: str) -> str:
        """QR 表示用の HTML 断片を返す"""
        if not qr_data_url:
            return ""
        return f'<div class="ticket-qr"><img src="{qr_data_url}" alt="QR"></div>'

    def _render_ticket_html_with_placeholders(
        self,
        event_name: str = "",
        event_date: str = "",
        venue: str = "",
        seat: str = "",
        holder_paymail: str = "",
        issue_date: str = "",
        background_block: str = "",
        qr_block: str = "",
        nft_metadata_json: str = "",
        layout_html: Optional[str] = None,
    ) -> str:
        """プレースホルダを埋めた HTML 文字列を返す。layout_html が空の場合は ValueError。{{x}} と {{ x }} の両方に対応。"""
        template = (layout_html or "").strip()
        if not template:
            raise ValueError("ticket_html must not be empty.")
        if not background_block:
            background_block = '<div class="ticket-bg" style="width:100%;height:100%;background:linear-gradient(135deg,#1e1e32 0%,#2a2a42 100%);"></div>'
        # スペースあり・なしの両方を置換
        def _repl(html: str, key: str, value: str) -> str:
            v = value or ""
            html = html.replace("{{ " + key + " }}", v)
            return html.replace("{{" + key + "}}", v)
        html = _repl(template, "event_name", event_name)
        html = _repl(html, "event_date", event_date)
        html = _repl(html, "venue", venue)
        html = _repl(html, "seat", seat)
        html = _repl(html, "holder_paymail", holder_paymail)
        html = _repl(html, "recipient_paymail", holder_paymail)
        html = _repl(html, "issue_date", issue_date)
        html = _repl(html, "background_block", background_block)
        html = _repl(html, "qr_block", qr_block)
        html = _repl(html, "nft_metadata_json", nft_metadata_json)
        return html

    def build_nft_metadata_for_embed(
        self,
        event_name: str,
        event_date: str,
        venue: str = "",
        seat: str = "",
        holder_paymail: str = "",
    ) -> Dict[str, Any]:
        """
        HTML 埋め込み用の NFT メタデータ（MAP 形式）を構築。
        API で渡されたデータを 1 つの NFT に含めるため、HTML 内の script#nft-metadata に埋め込む。
        """
        sub_type_data = self.build_ticket_metadata(
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            seat=seat,
            holder_paymail=holder_paymail,
        )
        return {
            "map": {
                "app": "Ticket System",
                "name": f"{event_name} Ticket",
                "type": "ord",
                "subType": "collectionItem",
                "subTypeData": sub_type_data,
            },
            "insc": {
                "file": {"hash": "...", "size": 0, "type": "text/html"},
            },
        }

    def render_ticket_html_for_creation(
        self,
        event_name: str,
        event_date: str,
        venue: str = "",
        seat: str = "",
        holder_paymail: str = "",
        layout_html: str = "",
    ) -> str:
        """
        アップロードされた HTML にプレースホルダを埋めてチケット用 HTML を生成。
        TicketDesign は使わない。スタイルはアップロード HTML に含まれる。
        {{ nft_metadata_json }} に API で受け取ったデータの JSON を埋め込む。
        """
        nft_metadata = self.build_nft_metadata_for_embed(
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            seat=seat,
            holder_paymail=holder_paymail or "",
        )
        nft_metadata_json = json.dumps(nft_metadata, ensure_ascii=False, indent=2)
        issue_date = now_iso()
        return self._render_ticket_html_with_placeholders(
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            seat=seat,
            holder_paymail=holder_paymail or "",
            issue_date=issue_date,
            background_block="",
            qr_block="",
            nft_metadata_json=nft_metadata_json,
            layout_html=layout_html,
        )

    def _get_issue_date_from_metadata(self, metadata: Dict[str, Any]) -> str:
        """メタデータの subTypeData.ticket.created_at を issue_date として返す。"""
        map_meta = metadata.get("MAP", {}) if isinstance(metadata.get("MAP"), dict) else {}
        candidate = map_meta.get("subTypeData")
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except Exception:
                candidate = None
        ticket = (candidate.get("ticket") if isinstance(candidate, dict) else None) or {}
        return str(ticket.get("created_at", "") or "")

    def render_ticket_html_from_metadata(
        self,
        metadata: Dict[str, Any],
        checkin_url: str,
        design: Optional[TicketDesign] = None,
    ) -> str:
        """メタデータからチケット HTML を生成（ticket/image 用）。QR は checkin_url を埋め込む。既存 NFT のメタデータをそのまま JSON で埋め込む。"""
        payload = self.extract_ticket_payload_from_metadata(metadata)
        design = design or TicketDesign.get_active()
        background_block = self._build_background_block(design)
        qr_data_url = self._build_qr_data_url(checkin_url) if checkin_url else ""
        qr_block = self._build_qr_block(qr_data_url)
        layout_html = getattr(design, "layout_html", None) if design else None
        nft_metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
        issue_date = self._get_issue_date_from_metadata(metadata)
        return self._render_ticket_html_with_placeholders(
            event_name=payload.event_title,
            event_date=payload.event_datetime,
            venue=payload.venue,
            seat=payload.seat,
            holder_paymail=payload.holder_name,
            issue_date=issue_date,
            background_block=background_block,
            qr_block=qr_block,
            nft_metadata_json=nft_metadata_json,
            layout_html=layout_html,
        )

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
        表示用 PNG の別経路: パラメータから PIL で描画（TicketDesign の背景・layout JSON ＋ QR）。
        作成時は NFT アセットに HTML を送るため通常は未使用。
        """
        design = design or TicketDesign.get_active()
        if not design or not design.template_image:
            base = Image.new("RGBA", (800, 400), (30, 30, 50, 255))
            layout = {}
        else:
            base = Image.open(design.template_image).convert("RGBA")
            layout = (design.layout or {}) if isinstance(design.layout, dict) else {}
        draw = ImageDraw.Draw(base)
        font = self._load_font(layout)
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
        x, y = self._get_xy(layout.get("text", {}), default=(40, 40))
        line_gap = int(layout.get("text", {}).get("line_gap", 10))
        text_color = layout.get("text", {}).get("color", "#FFFFFF")
        for line in lines:
            draw.text((x, y), line, fill=text_color, font=font)
            y += (font.size if hasattr(font, "size") else 12) + line_gap
        if checkin_url:
            qr_conf = layout.get("qr", {}) if isinstance(layout.get("qr"), dict) else {}
            qr_x, qr_y = self._get_xy(qr_conf, default=(base.width - 320, 40))
            qr_size = int(qr_conf.get("size", 260))
            qr_img = self._build_qr_image(checkin_url, qr_size=qr_size)
            padding = 20
            qr_with_bg = Image.new(
                "RGBA", (qr_size + padding * 2, qr_size + padding * 2), (255, 255, 255, 255)
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
            venue: 会場名・場所（住所）
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

