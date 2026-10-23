"""
Önbellek tabanlı basit hız sınırlayıcı.

Kaba kuvvet (brute-force) giriş denemelerini, spam kayıtları ve mesaj selini yavaşlatır.
Birden çok sunucu işleminde tutarlı çalışması için REDIS_URL ile Redis önbelleği kullanın.
"""
from __future__ import annotations

import functools
import hashlib
import time

from django.core.cache import cache
from django.shortcuts import render

from .utils import client_ip


def _bucket_key(scope: str, ident: str, window: int) -> str:
    slot = int(time.time() // window)
    digest = hashlib.sha256(f"{scope}:{ident}".encode()).hexdigest()[:40]
    return f"rl:{scope}:{digest}:{slot}"


def hit(scope: str, ident: str, limit: int, window: int) -> bool:
    """Sayaç artırır; sınır aşıldıysa True döner."""
    key = _bucket_key(scope, ident, window)
    added = cache.add(key, 1, timeout=window + 5)
    if added:
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # anahtar arada süresi dolmuş olabilir
            cache.set(key, 1, timeout=window + 5)
            count = 1
    return count > limit


def is_limited(scope: str, ident: str, limit: int, window: int) -> bool:
    count = cache.get(_bucket_key(scope, ident, window)) or 0
    return count >= limit


def too_many(request):
    response = render(request, "errors/429.html", status=429)
    response["Retry-After"] = "300"
    return response


def ratelimit(scope: str, limit: int, window: int, methods: tuple[str, ...] = ("POST",)):
    """Görünüm dekoratörü: aynı IP'den belirtilen süre içinde en fazla `limit` istek."""

    def decorator(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods and hit(scope, client_ip(request), limit, window):
                return too_many(request)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
