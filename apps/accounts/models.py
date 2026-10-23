from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("E-posta zorunludur.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, email_verified=True, role=User.Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """E-posta ile giriş yapılan kullanıcı. Her hesabın tek bir rolü vardır."""

    class Role(models.TextChoices):
        TEAM = "takim", "Takım / proje sahibi"
        SPONSOR = "destekci", "Destekçi (firma, kurum, mentör)"
        ADMIN = "yonetici", "Yönetici"

    username = None
    first_name = None
    last_name = None
    email = models.EmailField("E-posta", unique=True)
    full_name = models.CharField("Ad soyad (iletişim kişisi)", max_length=120)
    role = models.CharField("Rol", max_length=16, choices=Role.choices)
    email_verified = models.BooleanField("E-posta doğrulandı", default=False)
    adult_declared_at = models.DateTimeField("18 yaş beyanı", null=True, blank=True)
    email_notifications = models.BooleanField(
        "E-posta bildirimleri", default=True,
        help_text="Yeni talep, mesaj, sözleşme ve teslim bildirimleri (pazarlama içermez).",
    )

    # İki adımlı doğrulama (TOTP)
    totp_secret = models.CharField(max_length=64, blank=True, editable=False)
    totp_enabled_at = models.DateTimeField("İki adımlı doğrulama", null=True, blank=True, editable=False)
    totp_last_counter = models.BigIntegerField(default=0, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "Kullanıcı"
        verbose_name_plural = "Kullanıcılar"

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_team(self) -> bool:
        return self.role == self.Role.TEAM

    @property
    def is_sponsor(self) -> bool:
        return self.role == self.Role.SPONSOR

    @property
    def totp_enabled(self) -> bool:
        return bool(self.totp_enabled_at and self.totp_secret)

    @property
    def owned_team(self):
        return getattr(self, "team", None) if self.is_team else None

    @property
    def team_or_none(self):
        """Kullanıcının kaptanı ya da üyesi olduğu takım."""
        if not self.is_team:
            return None
        owned = getattr(self, "team", None)
        if owned is not None:
            return owned
        membership = getattr(self, "team_membership", None)
        return membership.team if membership is not None else None

    @property
    def is_team_captain(self) -> bool:
        return self.owned_team is not None

    @property
    def sponsor_or_none(self):
        return getattr(self, "sponsor", None) if self.is_sponsor else None


class RecoveryCode(models.Model):
    """İki adımlı doğrulama kurtarma kodları; yalnızca özetleri saklanır, her biri tek kullanımlık."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kurtarma kodu"
        verbose_name_plural = "Kurtarma kodları"

    def __str__(self):
        return f"Kurtarma kodu #{self.pk}"


class ConsentRecord(models.Model):
    """
    Onay/rıza kayıtları — yalnızca eklenir, değiştirilmez.
    Bir türün güncel durumu, o türdeki en son kayıttır.
    """

    class Kind(models.TextChoices):
        PRIVACY_NOTICE = "aydinlatma", "Aydınlatma metnini okudum"
        TERMS = "kullanim", "Kullanım koşullarını kabul ettim"
        MARKETING = "acik-riza", "Bülten ve duyurular için açık rıza"
        ADULT = "yas", "18 yaşını doldurdum beyanı"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    version = models.CharField(max_length=10)
    granted = models.BooleanField()
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Onay kaydı"
        verbose_name_plural = "Onay kayıtları"

    def __str__(self):
        state = "verildi" if self.granted else "geri alındı"
        return f"{self.get_kind_display()} v{self.version} {state}"

    @classmethod
    def current(cls, user, kind) -> bool:
        last = cls.objects.filter(user=user, kind=kind).order_by("-created_at", "-id").first()
        return bool(last and last.granted)
