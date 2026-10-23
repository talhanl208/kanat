"""
HTTP güvenlik başlıkları.

- Content-Security-Policy: yalnızca kendi alan adımızdan betik/stil/font; satır içi betikler
  yalnızca istek başına üretilen nonce ile çalışır. Üçüncü taraf CDN yok, izleme yok.
- Permissions-Policy: kamera, mikrofon, konum vb. tarayıcı yetkileri kapalı.
- Giriş yapmış kullanıcıların sayfaları paylaşılan önbelleklerde saklanmaz.
"""
from __future__ import annotations

import secrets

from django.conf import settings

PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer", "autoplay", "camera", "display-capture", "geolocation", "gyroscope",
        "magnetometer", "microphone", "midi", "payment", "usb", "xr-spatial-tracking",
    )
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_prefix = "/" + settings.ADMIN_URL

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)

        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self.build_csp(request)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and "Cache-Control" not in response:
            response["Cache-Control"] = "private, no-store"
        return response

    def build_csp(self, request) -> str:
        # Django admin satır içi stil özniteliği kullandığı için yalnızca orada gevşetiyoruz.
        style_src = "'self'"
        if request.path.startswith(self.admin_prefix):
            style_src = "'self' 'unsafe-inline'"
        directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{request.csp_nonce}'",
            f"style-src {style_src}",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "media-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "manifest-src 'self'",
            "worker-src 'none'",
        ]
        if not settings.DEBUG:
            directives.append("upgrade-insecure-requests")
        return "; ".join(directives)
