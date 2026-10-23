import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from apps.core.constants import (
    CATEGORIES, CATEGORY_KEYWORDS, CATEGORY_LABELS, CITY_CHOICES, COMPETITION_LABELS, COMPETITIONS, MONETARY_KINDS,
    STAGES, SUPPORT_KINDS,
)
from apps.core.storage import private_storage
from apps.core.utils import search_text, tr_normalize

RESERVED_SLUGS = {"yeni", "takimim", "takim", "profilim", "panel", "admin", "davet", "cagrilar",
                  "etki-raporu", "uyeler"}
MAX_TEAM_MEMBERS = 30
INVITE_DAYS = 7


def unique_slug(model, text: str, max_length: int = 60) -> str:
    base = slugify(tr_normalize(text))[: max_length - 7] or "kanat"
    slug = base
    while slug in RESERVED_SLUGS or model.objects.filter(slug=slug).exists():
        slug = f"{base}-{get_random_string(5, 'abcdefghijkmnpqrstuvwxyz23456789')}"
    return slug


class Team(models.Model):
    class Kind(models.TextChoices):
        TEAM = "takim", "Takım"
        INDIVIDUAL = "bireysel", "Bireysel"

    class Verification(models.TextChoices):
        NONE = "", "—"
        EDU = "edu", "Kurumsal e-posta (edu.tr / k12.tr / meb.gov.tr)"
        ADMIN = "yonetici", "Yönetici incelemesi"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team",
        verbose_name="Kaptan",
    )
    kind = models.CharField("Başvuru şekli", max_length=10, choices=Kind.choices, default=Kind.TEAM)
    name = models.CharField("Takım adı", max_length=80)
    slug = models.SlugField(max_length=60, unique=True, editable=False)
    institution = models.CharField("Okul / üniversite / kurum", max_length=120)
    city = models.CharField("Şehir", max_length=20, choices=CITY_CHOICES)
    member_count = models.PositiveSmallIntegerField("Üye sayısı", default=1)
    has_minor_members = models.BooleanField(
        "Takımda 18 yaşından küçük üye var",
        default=False,
        help_text="Varsa hesabı danışman öğretmen yönetmelidir; üyelerin kişisel verilerini girmeyin.",
    )
    advisor_name = models.CharField("Danışman adı (isteğe bağlı)", max_length=120, blank=True)
    about = models.TextField("Takımı anlatın", max_length=1500)
    website = models.URLField("Web / sosyal medya (https)", blank=True, max_length=200)
    logo = models.ImageField("Logo", upload_to="", blank=True)
    founded_year = models.PositiveSmallIntegerField("Kuruluş yılı", null=True, blank=True)
    verified = models.BooleanField("Doğrulanmış takım", default=False)
    verification_method = models.CharField(
        "Doğrulama yolu", max_length=10, choices=Verification.choices, blank=True, default=""
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Takım"
        verbose_name_plural = "Takımlar"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Team, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("projects:team_detail", args=[self.slug])

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "K"

    @property
    def completed_support_count(self) -> int:
        from apps.matching.models import SupportRequest

        return SupportRequest.objects.filter(
            project__team=self, status=SupportRequest.Status.COMPLETED
        ).count()

    # ---- Üyelik ----------------------------------------------------------
    def is_member(self, user) -> bool:
        if not getattr(user, "is_authenticated", False):
            return False
        return user.pk == self.owner_id or self.memberships.filter(user_id=user.pk).exists()

    def is_captain(self, user) -> bool:
        return getattr(user, "is_authenticated", False) and user.pk == self.owner_id

    @property
    def all_users(self) -> list:
        return [self.owner] + [m.user for m in self.memberships.select_related("user")]


class TeamMembership(models.Model):
    """Kaptan dışındaki takım üyeleri. Her kullanıcı en fazla bir takımda olabilir."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_membership"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        verbose_name = "Takım üyesi"
        verbose_name_plural = "Takım üyeleri"

    def __str__(self):
        return f"{self.user} @ {self.team}"


class TeamInvite(models.Model):
    """E-posta ile takım daveti. Bağlantıdaki belirtecin yalnızca SHA-256 özeti saklanır."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField("E-posta")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Takım daveti"
        verbose_name_plural = "Takım davetleri"

    def __str__(self):
        return f"{self.email} → {self.team}"

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create_for(cls, team, email, invited_by):
        token = secrets.token_urlsafe(32)
        invite = cls.objects.create(
            team=team, email=email.lower(), token_hash=cls._hash(token), invited_by=invited_by,
            expires_at=timezone.now() + timedelta(days=INVITE_DAYS),
        )
        return invite, token

    @classmethod
    def find(cls, token: str):
        return cls.objects.select_related("team").filter(
            token_hash=cls._hash(token), accepted_at__isnull=True, expires_at__gt=timezone.now()
        ).first()

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.expires_at > timezone.now()


class ProjectQuerySet(models.QuerySet):
    def public(self):
        today = timezone.localdate()
        return (
            self.filter(status=Project.Status.ACTIVE, team__owner__is_active=True)
            .exclude(deadline__lt=today)
        )


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "aktif", "Destek arıyor"
        DONE = "tamamlandi", "Tamamlandı"
        ARCHIVED = "arsiv", "Arşivde"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField("Proje adı", max_length=100)
    slug = models.SlugField(max_length=70, unique=True, editable=False)
    summary = models.CharField("Tek cümlelik özet", max_length=200)
    description = models.TextField("Projeyi anlatın", max_length=6000)
    category = models.CharField("Alan", max_length=20, choices=CATEGORIES)
    competition = models.CharField("Yarışma / program", max_length=20, choices=COMPETITIONS)
    competition_detail = models.CharField(
        "Yarışma kategorisi / yılı", max_length=120, blank=True,
        help_text="Örnek: TEKNOFEST 2027 İnsansız Kara Aracı Yarışması",
    )
    stage = models.CharField("Aşama", max_length=10, choices=STAGES, default="tasarim")
    deadline = models.DateField("Desteğe ihtiyaç duyulan son tarih", null=True, blank=True)
    sponsor_benefits = models.TextField(
        "Destekçiye sunduklarımız", max_length=1500, blank=True,
        help_text="Örnek: araç gövdesinde logo, sosyal medyada teşekkür, yarışma sunumunda anılma",
    )
    dossier = models.FileField(
        "Sponsorluk dosyası (PDF)", storage=private_storage, upload_to="", blank=True, editable=False
    )
    dossier_uploaded_at = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    search_index = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Proje"
        verbose_name_plural = "Projeler"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Project, self.title, 70)
        self.search_index = self.build_search_index()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = list(set(kwargs["update_fields"]) | {"search_index"})
        super().save(*args, **kwargs)

    def build_search_index(self) -> str:
        needs = " ".join(f"{n.title} {n.detail}" for n in self.needs.all()) if self.pk else ""
        team = self.team if self.team_id else None
        return search_text(
            self.title, self.summary, self.description, self.competition_detail,
            CATEGORY_LABELS.get(self.category, ""), CATEGORY_KEYWORDS.get(self.category, ""),
            COMPETITION_LABELS.get(self.competition, ""),
            team.name if team else "", team.institution if team else "", team.city if team else "",
            needs,
        )

    def refresh_search_index(self) -> None:
        type(self).objects.filter(pk=self.pk).update(search_index=self.build_search_index())

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.slug])

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline and self.deadline < timezone.localdate())

    @property
    def open_needs(self):
        return [n for n in self.needs.all() if not n.fulfilled]

    @property
    def need_kinds(self) -> set[str]:
        return {n.kind for n in self.open_needs}

    @property
    def monetary_need(self) -> Decimal:
        return sum(
            (n.remaining_amount or Decimal(0)) for n in self.open_needs if n.kind in MONETARY_KINDS
        ) or Decimal(0)

    @property
    def largest_monetary_need(self) -> Decimal:
        values = [n.remaining_amount or Decimal(0) for n in self.open_needs if n.kind in MONETARY_KINDS]
        return max(values) if values else Decimal(0)

    @property
    def mentor_hours_needed(self) -> int:
        return sum(n.mentor_hours or 0 for n in self.open_needs if n.kind == "mentorluk")

    @property
    def progress_percent(self) -> int:
        needs = list(self.needs.all())
        if not needs:
            return 0
        return round(100 * sum(1 for n in needs if n.fulfilled) / len(needs))


class Need(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="needs")
    kind = models.CharField("Tür", max_length=12, choices=SUPPORT_KINDS)
    title = models.CharField("İhtiyaç", max_length=100, help_text="Örnek: 4 adet fırçasız DC motor")
    detail = models.CharField("Ayrıntı", max_length=300, blank=True)
    estimated_cost = models.DecimalField(
        "Tahmini tutar (₺)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    mentor_hours = models.PositiveSmallIntegerField("Mentörlük saati", null=True, blank=True)
    fulfilled = models.BooleanField("Karşılandı", default=False)

    class Meta:
        ordering = ["fulfilled", "id"]
        verbose_name = "İhtiyaç"
        verbose_name_plural = "İhtiyaçlar"

    def __str__(self):
        return self.title

    # ---- Ortak kanat: bir ihtiyacı birden fazla destekçi paylaşabilir --------
    def _contributions(self):
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "contributions" in cache:
            return list(cache["contributions"])
        return list(self.contributions.all()) if self.pk else []

    @property
    def committed_amount(self) -> Decimal:
        """Sözleşmesi onaylanmış ve teslim edilmiş katkıların toplamı."""
        total = Decimal(0)
        for r in self._contributions():
            if r.status == "anlasma":
                total += r.amount or 0
            elif r.status == "tamamlandi":
                total += r.delivered_value or r.amount or 0
        return total

    @property
    def delivered_amount(self) -> Decimal:
        return sum(
            ((r.delivered_value or r.amount or 0) for r in self._contributions() if r.status == "tamamlandi"),
            Decimal(0),
        )

    @property
    def contributor_count(self) -> int:
        return len({r.sponsor_id for r in self._contributions() if r.status in ("anlasma", "tamamlandi")})

    @property
    def remaining_amount(self) -> Decimal | None:
        if self.estimated_cost is None:
            return None
        return max(Decimal(0), self.estimated_cost - self.committed_amount)

    @property
    def funded_percent(self) -> int:
        if not self.estimated_cost:
            return 100 if self.fulfilled else 0
        return min(100, round(100 * self.committed_amount / self.estimated_cost))

    @property
    def is_shareable(self) -> bool:
        return self.kind in MONETARY_KINDS and bool(self.estimated_cost) and not self.fulfilled


class ProgressUpdate(models.Model):
    """Proje günlüğü: destekçiler katkılarının nereye gittiğini görür."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="updates")
    title = models.CharField("Başlık", max_length=100)
    body = models.TextField("Neler oldu?", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Proje günlüğü"
        verbose_name_plural = "Proje günlükleri"

    def __str__(self):
        return self.title
