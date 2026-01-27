"""
テストアカウントでチケットNFTを作成するマネジメントコマンド

使用方法:
    python manage.py create_ticket --event-name "Test Event" --event-date "2026-02-01T18:00:00+09:00"
"""
import json
import os
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files import File

from ticket_service.models import TicketDesign
from ticket_service.services.base_api_client import BaseAPIClient
from ticket_service.services.ticket_service import TicketService, now_iso


DEFAULT_TEST_USERNAME = "test_yenpoint@linode.buxbit.net"
DEFAULT_TEST_PASSWORD = "yt3b.HW8Z-@eL-`b3H>"
DEFAULT_PUBLIC_URL = "https://ticket.buxbit.net"


class Command(BaseCommand):
    help = "Create a ticket NFT using the test account"

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, default=DEFAULT_TEST_USERNAME)
        parser.add_argument("--password", type=str, default=DEFAULT_TEST_PASSWORD)
        parser.add_argument("--event-name", type=str, default="")
        parser.add_argument("--event-date", type=str, default="")
        parser.add_argument("--venue", type=str, default="")
        parser.add_argument("--seat", type=str, default="")
        parser.add_argument("--recipient-paymail", type=str, default="")
        parser.add_argument("--ticket-design-id", type=int, default=None)
        parser.add_argument("--ticket-design-name", type=str, default="")
        parser.add_argument("--ticket-design-layout", type=str, default="")
        parser.add_argument("--template-image", type=str, default="")
        parser.add_argument("--checkin-reward-image", type=str, default="")
        parser.add_argument("--public-url", type=str, default=DEFAULT_PUBLIC_URL)

    def handle(self, *args, **options):
        base_url = getattr(settings, "BASE_API_URL", "").rstrip("/")
        if not base_url:
            self.stderr.write(self.style.ERROR("BASE_API_URL is not set in settings/.env"))
            return

        username = options["username"]
        password = options["password"]
        event_name = options["event_name"] or "Test Event"
        event_date = options["event_date"] or "2026-02-01T18:00:00+09:00"
        venue = options["venue"] or "Test Venue"
        seat = options["seat"] or "A-1"
        recipient_paymail = options["recipient_paymail"] or ""
        ticket_design_id = options["ticket_design_id"]
        ticket_design_name = options["ticket_design_name"] or ""
        ticket_design_layout = options["ticket_design_layout"] or ""
        template_image_path = options["template_image"] or ""
        checkin_reward_image_path = options["checkin_reward_image"] or ""
        public_url = (options["public_url"] or DEFAULT_PUBLIC_URL).rstrip("/")

        # Base API login to obtain session cookies
        session = requests.Session()
        login_url = f"{base_url}/api/v1/auth/login"
        try:
            response = session.post(
                login_url,
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            self.stderr.write(self.style.ERROR(f"Login failed: {exc}"))
            if getattr(exc, "response", None) is not None:
                self.stderr.write(self.style.ERROR(f"Response: {exc.response.text[:200]}"))
            return

        session_cookies = {}
        if session.cookies.get("sessionid"):
            session_cookies["sessionid"] = session.cookies.get("sessionid")
        if session.cookies.get("csrftoken"):
            session_cookies["csrftoken"] = session.cookies.get("csrftoken")

        if not session_cookies.get("sessionid"):
            self.stderr.write(self.style.ERROR("Login succeeded but sessionid cookie is missing."))
            return

        # Select or create/update ticket design (optional)
        design = None
        layout_payload = {}
        if ticket_design_layout:
            try:
                layout_payload = json.loads(ticket_design_layout)
            except json.JSONDecodeError:
                self.stderr.write(self.style.ERROR("ticket_design_layout must be valid JSON"))
                return

        has_design_payload = any([
            ticket_design_name,
            ticket_design_layout,
            template_image_path,
            checkin_reward_image_path,
        ])

        if ticket_design_id:
            design = TicketDesign.objects.filter(id=ticket_design_id).first()
            if not design:
                self.stderr.write(self.style.ERROR(f"TicketDesign id={ticket_design_id} not found"))
                return
            if has_design_payload:
                if ticket_design_name:
                    design.name = ticket_design_name
                if layout_payload:
                    design.layout = layout_payload
                if template_image_path:
                    if not os.path.exists(template_image_path):
                        self.stderr.write(self.style.ERROR(f"template image not found: {template_image_path}"))
                        return
                    with open(template_image_path, "rb") as f:
                        design.template_image.save(os.path.basename(template_image_path), File(f), save=False)
                if checkin_reward_image_path:
                    if not os.path.exists(checkin_reward_image_path):
                        self.stderr.write(self.style.ERROR(f"checkin reward image not found: {checkin_reward_image_path}"))
                        return
                    with open(checkin_reward_image_path, "rb") as f:
                        design.checkin_reward_image.save(os.path.basename(checkin_reward_image_path), File(f), save=False)
                design.save()
        else:
            if has_design_payload:
                design_name = ticket_design_name or f"{event_name} Design"
                design = TicketDesign.objects.create(
                    name=design_name,
                    layout=layout_payload or {},
                    is_active=True,
                )
                if template_image_path:
                    if not os.path.exists(template_image_path):
                        self.stderr.write(self.style.ERROR(f"template image not found: {template_image_path}"))
                        return
                    with open(template_image_path, "rb") as f:
                        design.template_image.save(os.path.basename(template_image_path), File(f), save=False)
                if checkin_reward_image_path:
                    if not os.path.exists(checkin_reward_image_path):
                        self.stderr.write(self.style.ERROR(f"checkin reward image not found: {checkin_reward_image_path}"))
                        return
                    with open(checkin_reward_image_path, "rb") as f:
                        design.checkin_reward_image.save(os.path.basename(checkin_reward_image_path), File(f), save=False)
                design.save()
            else:
                design = TicketDesign.get_active()

        holder_paymail = recipient_paymail or username
        ticket_service = TicketService()

        # NFT登録用に1px.pngを使用（メタデータのみをNFT化）
        placeholder_image_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "static", "images", "1px.png"
        )
        if not os.path.exists(placeholder_image_path):
            self.stderr.write(self.style.ERROR(f"Placeholder image not found: {placeholder_image_path}"))
            return
        
        with open(placeholder_image_path, "rb") as f:
            png_bytes = f.read()

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
            image_file=png_bytes,
            image_filename="ticket.png",
            nft_name=nft_name,
            metadata=metadata,
            session_cookies=session_cookies,
            recipient_paymail=recipient_paymail or None,
        )

        if not result:
            self.stderr.write(self.style.ERROR("Failed to create ticket NFT"))
            return

        nft_info = result.get("nft_information", {})
        nft_origin = nft_info.get("nft_origin")
        transaction_id = result.get("transaction_id")

        checkin_url = None
        ticket_image_url = None
        if nft_origin:
            token = ticket_service.build_checkin_token(nft_origin=nft_origin)
            checkin_url = f"{public_url}/api/ext/v1/ticket/checkin?token={token}"
            ticket_image_url = f"{public_url}/api/ext/v1/ticket/image/{nft_origin}"

        output = {
            "status": "success",
            "nft_origin": nft_origin,
            "transaction_id": transaction_id,
            "ticket_image_url": ticket_image_url,
            "checkin_url": checkin_url,
            "nft_information": nft_info,
        }
        self.stdout.write(json.dumps(output, ensure_ascii=True, indent=2))

