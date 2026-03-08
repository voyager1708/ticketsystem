from django.db import models
from django.contrib.auth.hashers import make_password


class Account(models.Model):
    """
    ローカル用アカウント。POST /api/accounts/create で作成（ベースAPI sign-up と同時に作成）。
    """
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)  # hashed
    email = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_system_account"
        ordering = ["-created_at"]

    def __str__(self):
        return self.username

    def set_password(self, raw_password):
        self.password = make_password(raw_password)


class TicketDesign(models.Model):
    """
    Ticket template design for NFT tickets (movie-ticket style).

    Stored in MEDIA:
    - template_image: background PNG/JPG
    - layout: JSON config controlling positions/sizes for QR + text (fallback when layout_html is empty)
    - layout_html: HTML fragment for ticket layout (placeholders: event_name, event_date, venue, seat, holder_paymail, background_block, qr_block, nft_metadata_json)
    - checkin_reward_image: image to be sent as NFT reward after check-in
    """

    name = models.CharField(max_length=100, default="Default", help_text="Design name for identification")
    template_image = models.ImageField(upload_to="ticket_templates/", null=True, blank=True)
    layout = models.JSONField(default=dict, blank=True)
    layout_html = models.TextField(null=True, blank=True, help_text="HTML template for ticket layout (placeholders: {{ event_name }}, {{ event_date }}, {{ venue }}, {{ seat }}, {{ holder_paymail }}, {{ background_block }}, {{ qr_block }}, {{ nft_metadata_json }})")
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
        return cls.objects.filter(is_active=True).order_by("-updated_at").first()


class TicketCheckinUrl(models.Model):
    """
    チケット作成時に返した checkin_url を nft_origin ごとに保存する。
    画像APIで同じURLをQRに使うため。
    """
    nft_origin = models.CharField(max_length=256, unique=True, db_index=True)
    checkin_url = models.URLField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_system_ticket_checkin_url"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.nft_origin}: {self.checkin_url[:50]}..."

