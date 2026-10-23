from django.contrib import admin

from .models import Award, PointEntry


@admin.register(PointEntry)
class PointEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "sponsor", "kind", "points", "held", "hold_reason", "is_void")
    list_filter = ("held", "is_void", "kind")
    search_fields = ("sponsor__name",)
    raw_id_fields = ("sponsor", "request")
    actions = ["release", "void"]

    @admin.action(description="İncelemeden çıkar (puan sıralamaya yansısın)")
    def release(self, request, queryset):
        updated = queryset.filter(held=True).update(held=False)
        self.message_user(request, f"{updated} puan kaydı onaylandı.")

    @admin.action(description="Geçersiz say")
    def void(self, request, queryset):
        updated = queryset.update(is_void=True, held=False)
        self.message_user(request, f"{updated} puan kaydı geçersiz sayıldı.")


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ("kind", "period", "league", "rank", "sponsor", "points", "code")
    list_filter = ("kind", "period", "league")
