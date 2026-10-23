from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.mail import send_mail

from apps.core.audit import audit
from apps.core.models import AuditLog

from .models import ConsentRecord, User
from .services import disable_totp


class ConsentInline(admin.TabularInline):
    model = ConsentRecord
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "version", "granted", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "role", "email_verified", "two_factor", "is_active", "date_joined")
    list_filter = ("role", "email_verified", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    readonly_fields = ("last_login", "date_joined", "adult_declared_at", "totp_enabled_at")
    inlines = [ConsentInline]
    actions = ["suspend", "unsuspend", "reset_two_factor"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("full_name", "role", "email_verified", "email_notifications",
                               "adult_declared_at", "totp_enabled_at")}),
        ("Yetkiler", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Tarihler", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),
    )


    @admin.display(boolean=True, description="2FA")
    def two_factor(self, obj):
        return obj.totp_enabled

    @admin.action(description="Seçili hesapları askıya al (giriş yapamazlar)")
    def suspend(self, request, queryset):
        count = 0
        for user in queryset.filter(is_active=True).exclude(pk=request.user.pk):
            user.is_active = False
            user.save(update_fields=["is_active"])
            audit(request, AuditLog.Action.SUSPENDED, user=user, detail=f"yonetici={request.user.pk}")
            send_mail("Kanat — hesabın askıya alındı",
                      "Merhaba,\n\nKanat hesabın kullanım koşullarına aykırılık incelemesi nedeniyle askıya "
                      "alındı. İtiraz etmek için bu e-postayı yanıtlayabilirsin.", None, [user.email],
                      fail_silently=True)
            count += 1
        self.message_user(request, f"{count} hesap askıya alındı.", messages.WARNING)

    @admin.action(description="Seçili hesapları askıdan çıkar")
    def unsuspend(self, request, queryset):
        updated = queryset.filter(is_active=False).exclude(email__endswith="@silinmis.invalid") \
            .update(is_active=True)
        self.message_user(request, f"{updated} hesap yeniden etkin.")

    @admin.action(description="İki adımlı doğrulamayı sıfırla (telefonunu kaybeden kullanıcı için)")
    def reset_two_factor(self, request, queryset):
        for user in queryset:
            disable_totp(user)
            audit(request, AuditLog.Action.TWO_FACTOR_DISABLED, user=user, detail=f"yonetici={request.user.pk}")
        self.message_user(request, "Seçili hesapların iki adımlı doğrulaması sıfırlandı.")


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "version", "granted", "created_at")
    list_filter = ("kind", "granted", "version")
    search_fields = ("user__email",)

    def has_change_permission(self, request, obj=None):
        return False
