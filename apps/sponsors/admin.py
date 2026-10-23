from django.contrib import admin

from .models import Sponsor, SponsorCall


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "league", "city", "verified", "verification_method",
                    "accepting_requests", "max_active_projects", "created_at")
    list_filter = ("verified", "verification_method", "kind", "league", "accepting_requests")
    search_fields = ("name", "sector", "owner__email")
    raw_id_fields = ("owner",)
    actions = ["mark_verified"]

    @admin.action(description="Seçili destekçileri doğrula (yönetici incelemesi)")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True, verification_method="yonetici")
        self.message_user(request, f"{updated} destekçi doğrulandı.")


@admin.register(SponsorCall)
class SponsorCallAdmin(admin.ModelAdmin):
    list_display = ("title", "sponsor", "kind", "slots", "deadline", "status")
    list_filter = ("status", "kind")
    search_fields = ("title", "sponsor__name")
