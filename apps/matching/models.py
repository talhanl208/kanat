import hashlib

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import SUPPORT_KINDS
from apps.projects.models import Need, Project, Team
from apps.sponsors.models import Sponsor, SponsorCall


class SupportRequest(models.Model):
    """Bir proje ile bir destekçi arasındaki destek süreci (talep → anlaşma → teslim)."""

    class Status(models.TextChoices):
        PENDING = "beklemede", "Yanıt bekleniyor"
        ACCEPTED = "kabul", "Kabul edildi, sözleşme bekleniyor"
        DECLINED = "red", "Reddedildi"
        WITHDRAWN = "geri_cekildi", "Geri çekildi"
        AGREED = "anlasma", "Sözleşme onaylandı"
        COMPLETED = "tamamlandi", "Destek teslim edildi"

    OPEN_STATUSES = (Status.PENDING, Status.ACCEPTED, Status.AGREED)

    class Initiator(models.TextChoices):
        TEAM = "takim", "Takım"
        SPONSOR = "destekci", "Destekçi"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="requests")
    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="requests")
    initiated_by = models.CharField(max_length=10, choices=Initiator.choices)
    kind = models.CharField("Destek türü", max_length=12, choices=SUPPORT_KINDS)
    note = models.TextField("Mesajınız", max_length=1000)
    amount = models.DecimalField(
        "Tahmini değer (₺)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    mentor_hours = models.PositiveSmallIntegerField("Mentörlük saati", null=True, blank=True)
    need = models.ForeignKey(
        Need, null=True, blank=True, on_delete=models.SET_NULL, related_name="contributions",
        verbose_name="Hangi ihtiyaç için?",
        help_text="Bir ihtiyacın yalnızca bir kısmını da üstlenebilirsin (ortak kanat).",
    )
    call = models.ForeignKey(
        SponsorCall, null=True, blank=True, on_delete=models.SET_NULL, related_name="applications",
        verbose_name="Destek çağrısı",
    )
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.PENDING)
    match_score = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    # Teslim ve teşekkür (takım doldurur)
    delivered_value = models.DecimalField(
        "Teslim alınan desteğin değeri (₺)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    rating = models.PositiveSmallIntegerField(
        "Memnuniyet", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    thanks_note = models.CharField("Teşekkür notu", max_length=400, blank=True)
    thanks_public = models.BooleanField("Teşekkür duvarında yayınlansın", default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Destek talebi"
        verbose_name_plural = "Destek talepleri"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "sponsor"],
                condition=Q(status__in=["beklemede", "kabul", "anlasma"]),
                name="tek_acik_talep",
            )
        ]

    def __str__(self):
        return f"{self.project} ↔ {self.sponsor}"

    def get_absolute_url(self):
        return reverse("matching:detail", args=[self.pk])

    # ---- Yetki yardımcıları (IDOR'a karşı her görünümde kullanılır) ----
    def side_of(self, user) -> str | None:
        if not getattr(user, "is_authenticated", False):
            return None
        if user.pk == self.sponsor.owner_id:
            return self.Initiator.SPONSOR
        if self.project.team.is_member(user):
            return self.Initiator.TEAM
        return None

    def is_participant(self, user) -> bool:
        return self.side_of(user) is not None

    def is_team_captain(self, user) -> bool:
        return self.project.team.is_captain(user)

    def awaiting_response_from(self) -> str:
        """Bekleyen talebe kimin yanıt vermesi gerekir? (Başlatmayan taraf.)"""
        return self.Initiator.SPONSOR if self.initiated_by == self.Initiator.TEAM else self.Initiator.TEAM

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def is_blocked(self) -> bool:
        return Block.exists_between(self.project.team, self.sponsor)

    @classmethod
    def for_user(cls, user):
        team = user.team_or_none
        flt = Q(sponsor__owner=user)
        if team is not None:
            flt |= Q(project__team=team)
        return cls.objects.filter(flt)


class Message(models.Model):
    request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField("Mesaj", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Mesaj"
        verbose_name_plural = "Mesajlar"

    def __str__(self):
        return f"Mesaj #{self.pk}"

    @classmethod
    def unread_for(cls, user):
        team = user.team_or_none
        flt = Q(request__sponsor__owner=user)
        if team is not None:
            flt |= Q(request__project__team=team)
        return cls.objects.filter(flt, read_at__isnull=True).exclude(sender=user)


class Agreement(models.Model):
    """
    Sponsorluk sözleşmesi. Talep silinse bile (ör. hesap kapatma) taraf adları ve metnin
    anlık kopyası saklanır; metnin SHA-256 özeti değişiklik olmadığını gösterir.
    """

    request = models.OneToOneField(
        SupportRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="agreement"
    )
    team_name = models.CharField(max_length=120)
    sponsor_name = models.CharField(max_length=120)
    project_title = models.CharField(max_length=120)
    support_summary = models.TextField("Destek kapsamı", max_length=1500)
    team_obligations = models.TextField("Takımın yükümlülükleri", max_length=1500)
    sponsor_obligations = models.TextField("Destekçinin yükümlülükleri", max_length=1500)
    payment_channel = models.CharField(
        "Ödeme / teslim kanalı", max_length=200,
        help_text="Örnek: üniversite döner sermaye hesabı, okul aile birliği, doğrudan ürün teslimi",
    )
    start_date = models.DateField("Başlangıç")
    end_date = models.DateField("Bitiş")
    template_version = models.CharField(max_length=10)
    body = models.TextField()
    body_hash = models.CharField(max_length=64)
    team_approved_at = models.DateTimeField(null=True, blank=True)
    sponsor_approved_at = models.DateTimeField(null=True, blank=True)
    team_ip_hash = models.CharField(max_length=64, blank=True)
    sponsor_ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sponsorluk sözleşmesi"
        verbose_name_plural = "Sponsorluk sözleşmeleri"

    def __str__(self):
        return f"{self.team_name} — {self.sponsor_name}"

    @property
    def fully_approved(self) -> bool:
        return bool(self.team_approved_at and self.sponsor_approved_at)

    def seal(self, body: str) -> None:
        """Metni günceller; metin değiştiyse önceki onaylar düşer."""
        new_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if new_hash != self.body_hash:
            self.team_approved_at = self.sponsor_approved_at = None
            self.team_ip_hash = self.sponsor_ip_hash = ""
        self.body, self.body_hash = body, new_hash


class MentorSession(models.Model):
    request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField("Tarih")
    hours = models.DecimalField(
        "Süre (saat)", max_digits=4, decimal_places=1,
        validators=[MinValueValidator(0.5), MaxValueValidator(8)],
    )
    topic = models.CharField("Konu", max_length=200)
    confirmed_at = models.DateTimeField("Takım onayı", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Mentörlük oturumu"
        verbose_name_plural = "Mentörlük oturumları"

    def __str__(self):
        return f"{self.topic} ({self.hours} sa)"


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam veya reklam"
        ABUSE = "taciz", "Taciz, hakaret veya tehdit"
        FRAUD = "dolandiricilik", "Dolandırıcılık şüphesi"
        PRIVACY = "mahremiyet", "Kişisel verilerin paylaşılması"
        MINOR = "cocuk", "Reşit olmayan bir üyeye uygunsuz yaklaşım"
        OTHER = "diger", "Diğer"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField("Neden", max_length=20, choices=Reason.choices)
    detail = models.CharField("Açıklama", max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["resolved", "-created_at"]
        verbose_name = "Şikâyet"
        verbose_name_plural = "Şikâyetler"

    def __str__(self):
        return f"{self.get_reason_display()} — #{self.request_id}"


class Block(models.Model):
    """
    Bir takım ile bir destekçi arasında engelleme. Engellenen taraflar birbirine yeni talep
    gönderemez, mesajlaşamaz ve önerilerde birbirini görmez. Yalnızca engelleyen taraf kaldırabilir.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="blocks")
    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="blocks")
    blocked_by = models.CharField(max_length=10, choices=SupportRequest.Initiator.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Engelleme"
        verbose_name_plural = "Engellemeler"
        constraints = [models.UniqueConstraint(fields=["team", "sponsor"], name="tek_engel")]

    def __str__(self):
        return f"{self.team} ⟂ {self.sponsor}"

    @classmethod
    def exists_between(cls, team, sponsor) -> bool:
        return cls.objects.filter(team=team, sponsor=sponsor).exists()
