import secrets

from django.db import models
from django.urls import reverse

from apps.matching.models import SupportRequest
from apps.sponsors.models import Sponsor


class PointEntry(models.Model):
    """
    Kanat puanı defteri. Puanlar yalnızca TAKIMIN ONAYLADIĞI olaylardan doğar
    (teslim alındı, mentörlük oturumu onaylandı). Yönetici kayıtları geçersiz kılabilir.
    """

    class Kind(models.TextChoices):
        COMPLETION = "tamamlanan_destek", "Tamamlanan destek"
        VALUE = "destek_degeri", "Destek değeri"
        FIRST_TEAM = "firsat_esitligi", "Fırsat eşitliği bonusu"
        FAST = "hizli_yanit", "Hızlı yanıt bonusu"
        RATING = "memnuniyet", "Takım memnuniyeti"
        MENTOR = "mentorluk", "Onaylı mentörlük saati"
        CO_FUND = "ortak_kanat", "Ortak kanat bonusu"

    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="points")
    # Not: geçerli puan = is_void=False ve held=False
    request = models.ForeignKey(
        SupportRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="points"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    points = models.PositiveIntegerField()
    note = models.CharField(max_length=160, blank=True)
    is_void = models.BooleanField("Geçersiz", default=False)
    held = models.BooleanField(
        "İncelemede", default=False,
        help_text="Şüpheli görülen kayıtlar, yönetici onaylayana kadar sıralamaya yansımaz.",
    )
    hold_reason = models.CharField("İnceleme nedeni", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Puan kaydı"
        verbose_name_plural = "Puan kayıtları"

    def __str__(self):
        return f"{self.sponsor} +{self.points} ({self.get_kind_display()})"


def _verification_code() -> str:
    return secrets.token_hex(6).upper()


class Award(models.Model):
    class Kind(models.TextChoices):
        MONTH = "ayin_kanadi", "Ayın Kanadı"
        YEAR = "yilin_ankasi", "Yılın Ankası"
        MENTOR = "yilin_kilavuzu", "Yılın Kılavuzu"
        EQUITY = "firsat_esitligi", "Fırsat Eşitliği Ödülü"

    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="awards")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    period = models.CharField("Dönem", max_length=7, help_text="2026-10 veya 2026")
    league = models.CharField(max_length=10, blank=True)
    rank = models.PositiveSmallIntegerField(default=1)
    points = models.PositiveIntegerField(default=0)
    code = models.CharField(max_length=12, unique=True, default=_verification_code, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at", "rank"]
        verbose_name = "Ödül"
        verbose_name_plural = "Ödüller"
        constraints = [
            models.UniqueConstraint(
                fields=["sponsor", "kind", "period", "league"], name="tek_odul_donem"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.period} — {self.sponsor}"

    def get_absolute_url(self):
        return reverse("rankings:certificate", args=[self.code])

    @property
    def league_label(self) -> str:
        from apps.core.constants import LEAGUES

        return dict(LEAGUES).get(self.league, "")

    @property
    def period_label(self) -> str:
        months = [
            "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        ]
        if len(self.period) == 7:
            year, month = self.period.split("-")
            return f"{months[int(month) - 1]} {year}"
        return self.period
