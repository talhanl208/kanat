from django.contrib import admin, messages
from django.utils import timezone

from .models import AuditLog, DataRequest, VerificationRequest


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "detail")
    list_filter = ("action",)
    search_fields = ("user__email", "detail")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "full_name", "email", "status", "due_date")
    list_filter = ("status", "kind")
    search_fields = ("full_name", "email")
    readonly_fields = ("full_name", "email", "kind", "message", "user", "created_at", "answered_at")

    def save_model(self, request, obj, form, change):
        if obj.status == DataRequest.Status.DONE and obj.answered_at is None:
            obj.answered_at = timezone.now()
        super().save_model(request, obj, form, change)


def _decide(request, queryset, approve: bool):
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    count = 0
    for vr in queryset.filter(status=VerificationRequest.Status.PENDING).select_related("team", "sponsor", "user"):
        subject = vr.subject
        if subject is None:
            continue
        vr.status = VerificationRequest.Status.APPROVED if approve else VerificationRequest.Status.REJECTED
        vr.reviewer, vr.reviewed_at = request.user, timezone.now()
        vr.save(update_fields=["status", "reviewer", "reviewed_at"])
        if approve:
            type(subject).objects.filter(pk=subject.pk).update(verified=True, verification_method="yonetici")
        notify([vr.user], Notification.Kind.VERIFY,
               "Profilin doğrulandı" if approve else "Doğrulama başvurun sonuçlanmadı",
               vr.response_note or ("Artık doğrulanmış rozetin var." if approve
                                    else "Ek bilgiyle yeniden başvurabilirsin."),
               url="/dogrulama/")
        count += 1
    return count


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "subject_name", "user", "status", "evidence_url")
    list_filter = ("status",)
    search_fields = ("team__name", "sponsor__name", "user__email")
    readonly_fields = ("user", "team", "sponsor", "evidence_url", "note", "created_at", "reviewed_at", "reviewer")
    fields = readonly_fields + ("status", "response_note")
    actions = ["approve", "reject"]

    @admin.display(description="Takım / destekçi")
    def subject_name(self, obj):
        return str(obj.subject)

    @admin.action(description="Onayla ve doğrulanmış rozeti ver")
    def approve(self, request, queryset):
        self.message_user(request, f"{_decide(request, queryset, True)} başvuru onaylandı.")

    @admin.action(description="Reddet")
    def reject(self, request, queryset):
        self.message_user(request, f"{_decide(request, queryset, False)} başvuru reddedildi.", messages.WARNING)
