from django.contrib import admin

from .models import Agreement, Block, MentorSession, Message, Report, SupportRequest


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "sponsor", "kind", "need", "call", "status", "initiated_by", "created_at")
    list_filter = ("status", "kind", "initiated_by")
    raw_id_fields = ("project", "sponsor", "need", "call")
    search_fields = ("project__title", "sponsor__name")


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ("team_name", "sponsor_name", "project_title", "team_approved_at", "sponsor_approved_at")
    readonly_fields = ("body", "body_hash", "team_approved_at", "sponsor_approved_at",
                       "team_ip_hash", "sponsor_ip_hash", "template_version")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "reason", "request", "resolved")
    list_filter = ("resolved", "reason")
    list_editable = ("resolved",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Mesajlar yalnızca şikâyet incelemesi için görüntülenir."""

    list_display = ("id", "request", "created_at")
    readonly_fields = ("request", "sender", "body", "created_at", "read_at")

    def has_add_permission(self, request):
        return False


admin.site.register(MentorSession)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("created_at", "team", "sponsor", "blocked_by")
    search_fields = ("team__name", "sponsor__name")
