from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path, reverse

admin.site.site_header = "Kanat yönetim"
admin.site.site_title = "Kanat yönetim"
admin.site.index_title = "Platform yönetimi"


def admin_login_redirect(request, extra_context=None):
    """Django admin'in kendi giriş sayfası kapalı: giriş her zaman Kanat'ın hız sınırlı,
    iki adımlı doğrulamalı akışından geçer."""
    nxt = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('accounts:login')}?next={nxt}")


admin.site.login = admin_login_redirect

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.core.urls")),
    path("hesap/", include("apps.accounts.urls")),
    path("projeler/", include("apps.projects.urls")),
    path("destekciler/", include("apps.sponsors.urls")),
    path("eslesmeler/", include("apps.matching.urls")),
    path("siralama/", include("apps.rankings.urls")),
    path("bildirimler/", include("apps.notifications.urls")),
]

if settings.DEBUG:  # Üretimde medya dosyalarını web sunucusu (nginx/Caddy) sunmalı
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
