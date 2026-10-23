from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        REQUEST = "talep", "Yeni destek talebi"
        RESPONSE = "yanit", "Talebe yanıt"
        MESSAGE = "mesaj", "Yeni mesaj"
        AGREEMENT = "sozlesme", "Sözleşme"
        COMPLETED = "teslim", "Teslim ve teşekkür"
        MENTOR = "mentorluk", "Mentörlük oturumu"
        TEAM = "takim", "Takım"
        VERIFY = "dogrulama", "Doğrulama"
        CALL = "cagri", "Destek çağrısı"
        DEADLINE = "son_tarih", "Son tarih"
        POINTS = "puan", "Puan ve ödül"
        SYSTEM = "sistem", "Sistem"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=400, blank=True)
    url = models.CharField(max_length=200, blank=True, help_text="Yalnızca site içi yol, örn. /eslesmeler/3/")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]
        verbose_name = "Bildirim"
        verbose_name_plural = "Bildirimler"

    def __str__(self):
        return self.title

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
