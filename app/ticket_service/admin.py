from django.contrib import admin
from ticket_service.models import Account, TicketDesign


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "created_at")
    search_fields = ("username", "email")


@admin.register(TicketDesign)
class TicketDesignAdmin(admin.ModelAdmin):
    list_display = ("id", "is_active", "template_image", "checkin_reward_image", "updated_at", "created_at")
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("id",)
    fields = ("template_image", "layout", "checkin_reward_image", "is_active")

