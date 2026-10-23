from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Güvenlik açısından önemli olayların kaydı. IP adresi açık halde saklanmaz."""

    class Action(models.TextChoices):
        REGISTER = "register", "Kayıt"
        LOGIN = "login", "Giriş"
        LOGIN_FAILED = "login_failed", "Başarısız giriş"
        LOGOUT = "logout", "Çıkış"
        EMAIL_VERIFIED = "email_verified", "E-posta doğrulandı"
        PASSWORD_CHANGED = "password_changed", "Parola değişti"
        CONSENT_CHANGED = "consent_changed", "Rıza değişti"
        DATA_EXPORTED = "data_exported", "Veri dışa aktarıldı"
        ACCOUNT_DELETED = "account_deleted", "Hesap silindi"
        AGREEMENT_APPROVED = "agreement_approved", "Sözleşme onaylandı"
        REPORT = "report", "Şikâyet"
        EMAIL_CHANGED = "email_changed", "E-posta değişti"
        TWO_FACTOR_ENABLED = "2fa_enabled", "İki adımlı doğrulama açıldı"
        TWO_FACTOR_DISABLED = "2fa_disabled", "İki adımlı doğrulama kapatıldı"
        TWO_FACTOR_FAILED = "2fa_failed", "Hatalı doğrulama kodu"
        RECOVERY_CODE_USED = "recovery_used", "Kurtarma kodu kullanıldı"
        TEAM_MEMBER = "team_member", "Takım üyeliği değişti"
        BLOCK = "block", "Engelleme"
        SUSPENDED = "suspended", "Hesap askıya alındı"
        VERIFICATION = "verification", "Doğrulama"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    detail = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Güvenlik kaydı"
        verbose_name_plural = "Güvenlik kayıtları"

    def __str__(self):
        return f"{self.get_action_display()} — {self.created_at:%d.%m.%Y %H:%M}"


class DataRequest(models.Model):
    """KVKK md. 11 kapsamındaki ilgili kişi başvuruları."""

    class Kind(models.TextChoices):
        INFO = "bilgi", "Verilerimin işlenip işlenmediğini öğrenmek"
        ACCESS = "erisim", "Verilerime erişmek / kopyasını almak"
        CORRECT = "duzeltme", "Eksik veya yanlış verilerin düzeltilmesi"
        DELETE = "silme", "Verilerimin silinmesi veya yok edilmesi"
        THIRD = "aktarim", "Aktarıldığı üçüncü kişileri öğrenmek"
        OBJECT = "itiraz", "Otomatik analiz sonucuna itiraz"
        OTHER = "diger", "Diğer"

    class Status(models.TextChoices):
        NEW = "yeni", "Yeni"
        IN_PROGRESS = "isleniyor", "İşleniyor"
        DONE = "yanitlandi", "Yanıtlandı"

    full_name = models.CharField("Ad soyad", max_length=120)
    email = models.EmailField("E-posta")
    kind = models.CharField("Talep türü", max_length=20, choices=Kind.choices)
    message = models.TextField("Açıklama", max_length=3000)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    internal_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "KVKK başvurusu"
        verbose_name_plural = "KVKK başvuruları"

    def __str__(self):
        return f"{self.get_kind_display()} — {self.created_at:%d.%m.%Y}"

    @property
    def due_date(self):
        """KVKK md. 13: başvurular en geç 30 gün içinde sonuçlandırılır."""
        from datetime import timedelta

        return self.created_at + timedelta(days=30)


class VerificationRequest(models.Model):
    """Takım ya da destekçinin elle doğrulanma başvurusu (yönetici inceler)."""

    class Status(models.TextChoices):
        PENDING = "bekliyor", "İnceleniyor"
        APPROVED = "onaylandi", "Onaylandı"
        REJECTED = "reddedildi", "Reddedildi"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    team = models.ForeignKey("projects.Team", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="verification_requests")
    sponsor = models.ForeignKey("sponsors.Sponsor", null=True, blank=True, on_delete=models.CASCADE,
                                related_name="verification_requests")
    evidence_url = models.URLField(
        "Kanıt bağlantısı (https)", blank=True, max_length=300,
        help_text="Örnek: yarışma başvuru sayfası, okul/üniversite duyurusu, kurumsal web sayfası",
    )
    note = models.TextField(
        "Açıklama", max_length=1500,
        help_text="Kim olduğunuzu ve nasıl doğrulanabileceğinizi anlatın. Kimlik numarası yazmayın.",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    response_note = models.CharField("Yanıt", max_length=400, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Doğrulama başvurusu"
        verbose_name_plural = "Doğrulama başvuruları"

    def __str__(self):
        subject = self.team or self.sponsor
        return f"{subject} — {self.get_status_display()}"

    @property
    def subject(self):
        return self.team or self.sponsor
