from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme

_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u", "â": "a", "î": "i", "û": "u",
})


def tr_normalize(text: str) -> str:
    """Türkçe karakterleri sadeleştirip küçük harfe çevirir ('İnsansız' -> 'insansiz')."""
    return (text or "").translate(_TR_MAP).lower()


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", tr_normalize(text)) if len(t) >= 2}


def search_text(*parts) -> str:
    """Arama dizini: Türkçe karakterler sadeleştirilmiş, küçük harf, tek boşluklu metin.
    Böylece 'tübitak', 'TÜBİTAK' ve 'Tubitak' aynı sonucu verir (SQLite ve PostgreSQL'de)."""
    words = re.split(r"[^a-z0-9]+", tr_normalize(" ".join(str(p) for p in parts if p)))
    return " " + " ".join(w for w in words if w) + " "


_TR_SUFFIXES = (
    "lerinden", "larindan", "lerinin", "larinin", "lerini", "larini", "leri", "lari", "ler", "lar",
    "nin", "nun", "den", "dan", "ten", "tan", "de", "da", "te", "ta", "si", "su", "yi", "yu",
)


def stem_tr(word: str) -> str:
    """Çok hafif Türkçe ek atma (yalnızca arama sorgusu için): 'motorlar' -> 'motor'."""
    for suffix in _TR_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    if word[-1:] in ("i", "u") and len(word) >= 6:
        return word[:-1]
    return word


def search_tokens(query: str, limit: int = 6) -> list[str]:
    words = [w for w in re.split(r"[^a-z0-9]+", tr_normalize(query or "")) if len(w) >= 2]
    return [stem_tr(w) for w in words[:limit]]


def apply_search(qs, query: str, field: str = "search_index"):
    """Her kelime için 'kelime başı' eşleşmesi arar: 'motor' -> 'motorlar' bulur, 'elektromotor' bulmaz."""
    for token in search_tokens(query):
        qs = qs.filter(**{f"{field}__contains": " " + token})
    return qs


def client_ip(request) -> str:
    """İstemci IP'si. X-Forwarded-For yalnızca güvenilir vekil arkasında okunur (sahtecilik riski)."""
    ip = ""
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
    if not ip:
        ip = request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return "0.0.0.0"


def hash_ip(ip: str) -> str:
    """IP adresini anahtarlı özetle takma adlandırır (KVKK: veri minimizasyonu)."""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"ip:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


def request_ip_hash(request) -> str:
    return hash_ip(client_ip(request))


def safe_next_url(request, fallback: str) -> str:
    """Açık yönlendirme (open redirect) saldırılarına karşı 'next' parametresini doğrular."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback
