"""
Yönetim paneline yalnızca iki adımlı doğrulamadan geçmiş personel girebilir.

- 2FA kurulmamışsa kurulum sayfasına yönlendirilir.
- Kuruluysa ama bu oturumda kod girilmemişse (ör. oturum başka yoldan açıldıysa) kod istenir.
Django admin'in kendi giriş sayfası devre dışıdır (config/urls.py), giriş her zaman Kanat
giriş akışından geçer.
"""
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class AdminTwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.prefix = "/" + settings.ADMIN_URL

    def __call__(self, request):
        if (
            getattr(settings, "ADMIN_REQUIRE_2FA", True)
            and request.path.startswith(self.prefix)
            and not request.path.endswith("/logout/")
        ):
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and user.is_staff:
                nxt = quote(request.get_full_path())
                if not user.totp_enabled:
                    messages.warning(request, "Yönetim paneli için önce iki adımlı doğrulamayı açmalısın.")
                    return redirect(f"{reverse('accounts:two_factor')}?next={nxt}")
                if not request.session.get("otp_verified"):
                    return redirect(f"{reverse('accounts:two_factor_verify')}?next={nxt}")
        return self.get_response(request)
