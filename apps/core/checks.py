"""`manage.py check --deploy` sırasında Kanat'a özgü üretim kontrolleri."""
from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def kanat_deploy_checks(app_configs, **kwargs):
    issues = []
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend.endswith("LocMemCache"):
        issues.append(Warning(
            "Hız sınırı sayaçları bellek içi önbellekte; birden çok sunucu işleminde paylaşılmaz.",
            hint="REDIS_URL tanımlayın ya da veritabanı önbelleğini kullanın (createcachetable).",
            id="kanat.W001",
        ))
    if settings.KANAT.get("DATA_CONTROLLER_NAME", "").startswith("["):
        issues.append(Warning(
            "KVKK veri sorumlusu bilgileri doldurulmamış.",
            hint="KANAT_DATA_CONTROLLER_NAME / ADDRESS / EMAIL ortam değişkenlerini ayarlayın.",
            id="kanat.W002",
        ))
    if settings.ADMIN_URL == "yonetim-kapisi/":
        issues.append(Warning(
            "Yönetim paneli varsayılan adreste.", hint="DJANGO_ADMIN_URL ile tahmin edilmesi zor bir yol seçin.",
            id="kanat.W003",
        ))
    if not getattr(settings, "ADMIN_REQUIRE_2FA", True):
        issues.append(Warning(
            "Yönetim paneli için iki adımlı doğrulama zorunlu değil.", hint="KANAT_ADMIN_REQUIRE_2FA=1",
            id="kanat.W004",
        ))
    if "localhost" in settings.KANAT.get("SITE_URL", ""):
        issues.append(Warning(
            "KANAT_SITE_URL localhost gösteriyor; e-postalardaki bağlantılar çalışmaz.",
            id="kanat.W005",
        ))
    return issues
