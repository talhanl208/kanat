"""
Kanat — proje takımlarını destekçilerle buluşturan platform.

Tüm gizli/ortama bağlı değerler ortam değişkenlerinden okunur (.env.example'a bakın).
Varsayılanlar GÜVENLİ taraftadır: DEBUG kapalıdır, üretimde SECRET_KEY zorunludur.
"""
from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Basit .env okuyucu (ek bağımlılık olmadan). Var olan ortam değişkenlerini ezmez."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "evet"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Temel
# --------------------------------------------------------------------------- #
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        # Yalnızca yerel geliştirme için. Üretimde asla kullanılmaz.
        SECRET_KEY = "dev-only-insecure-key-change-me-0123456789abcdefghijklmnopqrstuvwxyz"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY ortam değişkeni tanımlı değil.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.sponsors",
    "apps.matching",
    "apps.rankings",
    "apps.notifications",
]

try:  # whitenoise yüklüyse statik dosyaları güvenli başlıklarla sunar
    import whitenoise  # noqa: F401

    _WHITENOISE = True
except ImportError:  # pragma: no cover
    _WHITENOISE = False

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    *(["whitenoise.middleware.WhiteNoiseMiddleware"] if _WHITENOISE else []),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.accounts.middleware.AdminTwoFactorMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------- #
# Veritabanı — üretimde PostgreSQL, yerelde SQLite
# --------------------------------------------------------------------------- #
if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", "kanat"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": env("POSTGRES_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Kimlik doğrulama ve parola güvenliği
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
TWO_FACTOR_LOGIN_TIMEOUT = 300  # parola sonrası doğrulama kodu için süre (sn)
LOGOUT_REDIRECT_URL = "core:home"

try:  # Argon2id (OWASP önerisi); argon2-cffi yoksa PBKDF2'ye düşer
    import argon2  # noqa: F401

    _ARGON2 = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
except ImportError:  # pragma: no cover
    _ARGON2 = []

PASSWORD_HASHERS = [
    *_ARGON2,
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_RESET_TIMEOUT = 60 * 60 * 2  # 2 saat
EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24 * 3  # 3 gün

# --------------------------------------------------------------------------- #
# Dil, saat
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Statik ve yüklenen dosyalar
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
# Herkese açık OLMAYAN dosyalar (sponsorluk dosyaları). Web sunucusu bu klasörü SUNMAMALI;
# dosyalar yalnızca yetki kontrolü yapan görünüm üzerinden indirilir.
PRIVATE_MEDIA_ROOT = Path(env("DJANGO_PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")))
MAX_PDF_UPLOAD_BYTES = 5 * 1024 * 1024

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if (_WHITENOISE and not DEBUG)
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

# İstek boyutu sınırları (DoS ve büyük dosya saldırılarına karşı)
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 400
MAX_IMAGE_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 4096 * 4096
FILE_UPLOAD_PERMISSIONS = 0o640

# --------------------------------------------------------------------------- #
# Çerez, oturum ve HTTP güvenlik başlıkları
# --------------------------------------------------------------------------- #
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 1 hafta
SESSION_COOKIE_NAME = "kanat_oturum"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "kanat_csrf"
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)

# Ters vekil (nginx, Caddy vb.) arkasındaysanız ve vekil bu başlığı kendisi yazıyorsa açın.
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# İstemci IP'si için X-Forwarded-For'a yalnızca güvenilir vekil arkasında güvenilir.
TRUST_X_FORWARDED_FOR = env_bool("DJANGO_TRUST_X_FORWARDED_FOR", False)

# --------------------------------------------------------------------------- #
# Önbellek (hız sınırlama sayaçları burada tutulur)
# Sayaçların tüm sunucu işlemleri arasında PAYLAŞILMASI gerekir; aksi hâlde her işlem kendi
# sayacını tutar ve sınır fiilen işlem sayısı kadar katlanır.
#   REDIS_URL varsa  -> Redis (önerilen)
#   üretimde yoksa   -> veritabanı önbelleği (paylaşılır; `manage.py createcachetable` gerekir)
#   geliştirmede     -> bellek içi önbellek
# --------------------------------------------------------------------------- #
if env("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
        }
    }
elif DEBUG:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "kanat_onbellek",
        }
    }

# --------------------------------------------------------------------------- #
# E-posta
# --------------------------------------------------------------------------- #
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Kanat <no-reply@kanat.local>")

# --------------------------------------------------------------------------- #
# Günlük kaydı — kişisel veri yazmayın
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "kanat": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# --------------------------------------------------------------------------- #
# Hata izleme (isteğe bağlı). Kişisel veri GÖNDERİLMEZ.
# --------------------------------------------------------------------------- #
if env("SENTRY_DSN"):
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=env("SENTRY_DSN"),
            send_default_pii=False,
            traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0")),
            environment=env("SENTRY_ENVIRONMENT", "uretim"),
        )
    except ImportError:  # pragma: no cover
        pass

# --------------------------------------------------------------------------- #
# Kanat'a özel ayarlar
# --------------------------------------------------------------------------- #
ADMIN_URL = env("DJANGO_ADMIN_URL", "yonetim-kapisi/").strip("/") + "/"
# Yönetim paneline girmek için iki adımlı doğrulama (üretimde varsayılan olarak zorunlu)
ADMIN_REQUIRE_2FA = env_bool("KANAT_ADMIN_REQUIRE_2FA", not DEBUG)

# KVKK: saklama süreleri (gün). `manage.py gunluk_bakim` bu sürelere göre temizlik yapar.
RETENTION_DAYS = {
    "audit_log": int(env("KANAT_RETENTION_AUDIT_DAYS", "730")),
    "notifications_read": int(env("KANAT_RETENTION_NOTIFICATION_DAYS", "90")),
    "notifications_unread": 365,
    "resolved_reports": 730,
    "answered_data_requests": 1095,
    "closed_request_messages": 730,
    "unverified_accounts": 14,
}

KANAT = {
    "SITE_NAME": env("KANAT_SITE_NAME", "Kanat"),
    "SITE_TAGLINE": env("KANAT_SITE_TAGLINE", "Geleceğin Yönünü Değiştiren Hayatlar"),
    "SITE_URL": env("KANAT_SITE_URL", "http://localhost:8000"),
    # KVKK veri sorumlusu bilgileri — yayına almadan önce doldurun.
    "DATA_CONTROLLER_NAME": env("KANAT_DATA_CONTROLLER_NAME", "[Veri sorumlusunun adı / unvanı]"),
    "DATA_CONTROLLER_ADDRESS": env("KANAT_DATA_CONTROLLER_ADDRESS", "[Açık adres]"),
    "DATA_CONTROLLER_EMAIL": env("KANAT_DATA_CONTROLLER_EMAIL", "kvkk@kanat.local"),
    "DATA_CONTROLLER_KEP": env("KANAT_DATA_CONTROLLER_KEP", ""),
    "SECURITY_CONTACT": env("KANAT_SECURITY_CONTACT", "guvenlik@kanat.local"),
    # Hukuki metinler henüz bir hukukçu tarafından incelenmediyse uyarı göster.
    "LEGAL_DRAFT_NOTICE": env_bool("KANAT_LEGAL_DRAFT_NOTICE", True),
}
