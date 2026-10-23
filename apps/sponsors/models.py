from django.conf import settings
from django.db import models
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone

from apps.core.constants import (
    CATEGORIES, CATEGORY_LABELS, CITY_CHOICES, COMPETITION_LABELS, LEAGUES, SPONSOR_KINDS,
    SUPPORT_KINDS, SUPPORT_LABELS,
)
from apps.core.utils import search_text, tr_normalize
from apps.projects.models import unique_slug

ACTIVE_WORK_STATUSES = ("kabul", "anlasma")


class SponsorQuerySet(models.QuerySet):
    def active(self):
        return self.filter(accepting_requests=True, owner__is_active=True)

    def with_load(self):
        return self.annotate(
            active_load=Count("requests", filter=Q(requests__status__in=ACTIVE_WORK_STATUSES), distinct=True)
        )

    def available(self):
        """Talep alan ve kapasitesi dolmamış destekçiler."""
        return self.active().with_load().filter(
            Q(max_active_projects__isnull=True) | Q(active_load__lt=F("max_active_projects"))
        )


class Sponsor(models.Model):
    class Verification(models.TextChoices):
        NONE = "", "—"
        DOMAIN = "alan_adi", "Kurumsal e-posta alan adı"
        ADMIN = "yonetici", "Yönetici incelemesi"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sponsor"
    )
    kind = models.CharField("Destekçi türü", max_length=10, choices=SPONSOR_KINDS, default="firma")
    name = models.CharField("Firma / kurum / kişi adı", max_length=100)
    slug = models.SlugField(max_length=60, unique=True, editable=False)
    league = models.CharField(
        "Ölçek (sıralama ligi)", max_length=10, choices=LEAGUES, default="kobi",
        help_text="Küçük işletmeler büyük kurumlarla aynı ligde yarışmaz.",
    )
    sector = models.CharField("Sektör", max_length=80)
    city = models.CharField("Şehir", max_length=20, choices=CITY_CHOICES)
    serves_all_turkey = models.BooleanField("Tüm Türkiye'deki takımlara destek veririm", default=True)
    website = models.URLField(
        "Web sitesi (https)", blank=True, max_length=200,
        help_text="E-posta adresinin alan adıyla aynıysa profilin otomatik doğrulanır.",
    )
    logo = models.ImageField("Logo", upload_to="", blank=True)
    about = models.TextField("Kendinizi tanıtın", max_length=1500)

    support_types = models.JSONField("Sunduğunuz destek türleri", default=list)
    interest_categories = models.JSONField("İlgilendiğiniz alanlar", default=list, blank=True)
    competitions = models.JSONField("Desteklediğiniz yarışma/programlar", default=list, blank=True)
    budget_min = models.PositiveIntegerField("Proje başına en az bütçe (₺)", null=True, blank=True)
    budget_max = models.PositiveIntegerField("Proje başına en fazla bütçe (₺)", null=True, blank=True)
    mentor_hours_per_month = models.PositiveSmallIntegerField(
        "Aylık mentörlük kapasitesi (saat)", null=True, blank=True
    )
    max_active_projects = models.PositiveSmallIntegerField(
        "Aynı anda en fazla kaç takımla çalışabilirsin?", null=True, blank=True,
        help_text="Boş bırakırsan sınır yok. Dolunca yeni talep almazsın ve önerilerde görünmezsin.",
    )
    offerings = models.CharField(
        "Ürün ve hizmet anahtar kelimeleri", max_length=300, blank=True,
        help_text="Virgülle ayırın. Örnek: PCB baskı, 3D yazıcı, lityum batarya, CNC",
    )
    accepting_requests = models.BooleanField("Şu an destek talebi alıyorum", default=True)
    verified = models.BooleanField(
        "Doğrulanmış destekçi", default=False,
        help_text="Alan adı eşleşmesiyle otomatik ya da yönetici incelemesiyle verilir. "
                  "Sıralamaya yalnızca doğrulanmış destekçiler girer.",
    )
    verification_method = models.CharField(
        "Doğrulama yolu", max_length=10, choices=Verification.choices, blank=True, default=""
    )
    search_index = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SponsorQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Destekçi"
        verbose_name_plural = "Destekçiler"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Sponsor, self.name)
        self.search_index = search_text(
            self.name, self.sector, self.offerings, self.city, self.about,
            " ".join(self.support_type_labels), " ".join(self.interest_labels),
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = list(set(kwargs["update_fields"]) | {"search_index"})
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("sponsors:detail", args=[self.slug])

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "D"

    @property
    def offering_keywords(self) -> list[str]:
        return [k.strip() for k in self.offerings.split(",") if k.strip()]

    @property
    def offering_tokens(self) -> list[tuple[str, str]]:
        """(görünen, normalize) çiftleri."""
        return [(k, tr_normalize(k)) for k in self.offering_keywords]

    @property
    def support_type_labels(self) -> list[str]:
        return [SUPPORT_LABELS.get(s, s) for s in self.support_types or []]

    @property
    def interest_labels(self) -> list[str]:
        return [CATEGORY_LABELS.get(c, c) for c in self.interest_categories or []]

    @property
    def competition_labels(self) -> list[str]:
        return [COMPETITION_LABELS.get(c, c) for c in self.competitions or []]

    @property
    def active_project_count(self) -> int:
        if hasattr(self, "active_load"):
            return self.active_load
        return self.requests.filter(status__in=ACTIVE_WORK_STATUSES).count()

    @property
    def at_capacity(self) -> bool:
        return self.max_active_projects is not None and self.active_project_count >= self.max_active_projects

    @property
    def can_receive_requests(self) -> bool:
        return self.accepting_requests and self.owner.is_active and not self.at_capacity


class SponsorCallQuerySet(models.QuerySet):
    def open(self):
        today = timezone.localdate()
        return self.filter(status=SponsorCall.Status.OPEN, deadline__gte=today,
                           sponsor__owner__is_active=True)


class SponsorCall(models.Model):
    """Destek çağrısı: destekçi belirli bir destek için başvuru toplar (ör. '3 İHA takımına 10.000 ₺')."""

    class Status(models.TextChoices):
        OPEN = "acik", "Başvuruya açık"
        CLOSED = "kapandi", "Kapandı"

    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name="calls")
    title = models.CharField("Çağrı başlığı", max_length=120,
                             help_text="Örnek: İnsansız hava aracı takımlarına motor desteği")
    description = models.TextField("Çağrının ayrıntıları", max_length=3000,
                                   help_text="Kimler başvurabilir, neyi bekliyorsunuz, seçim nasıl yapılacak?")
    kind = models.CharField("Destek türü", max_length=12, choices=SUPPORT_KINDS)
    categories = models.JSONField("Alanlar (boşsa tüm alanlar)", default=list, blank=True)
    amount_per_team = models.DecimalField(
        "Takım başına değer (₺)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    mentor_hours = models.PositiveSmallIntegerField("Takım başına mentörlük saati", null=True, blank=True)
    slots = models.PositiveSmallIntegerField("Kaç takım desteklenecek?", default=1)
    deadline = models.DateField("Son başvuru tarihi")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SponsorCallQuerySet.as_manager()

    class Meta:
        ordering = ["deadline", "-created_at"]
        verbose_name = "Destek çağrısı"
        verbose_name_plural = "Destek çağrıları"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("sponsors:call_detail", args=[self.pk])

    @property
    def category_labels(self) -> list[str]:
        return [CATEGORY_LABELS.get(c, c) for c in self.categories or []]

    @property
    def accepted_count(self) -> int:
        return self.applications.filter(status__in=["kabul", "anlasma", "tamamlandi"]).count()

    @property
    def slots_left(self) -> int:
        return max(0, self.slots - self.accepted_count)

    @property
    def is_open(self) -> bool:
        return (self.status == self.Status.OPEN and self.deadline >= timezone.localdate()
                and self.slots_left > 0)

    @property
    def days_left(self) -> int:
        return (self.deadline - timezone.localdate()).days

    def accepts_category(self, category: str) -> bool:
        return not self.categories or category in self.categories


CALL_CATEGORY_CHOICES = CATEGORIES
