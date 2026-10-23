"""
RFC 6238 TOTP (zamana dayalı tek kullanımlık parola) — ek bağımlılık olmadan.

Google Authenticator, Microsoft Authenticator, Aegis, 1Password vb. ile uyumludur
(SHA-1, 6 hane, 30 saniye). Aynı kodun ikinci kez kullanılması (replay) engellenir.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    secret = secret.replace(" ", "").upper()
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def code_at(secret: str, counter: int, digits: int = DIGITS) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** digits)).zfill(digits)


def current_counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def verify(secret: str, code: str, last_counter: int = 0, window: int = 1,
           now: float | None = None) -> int | None:
    """Kod geçerliyse kullanılan sayaç değerini, değilse None döner."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if not secret or len(code) != DIGITS:
        return None
    current = current_counter(now)
    for counter in range(current - window, current + window + 1):
        if counter <= last_counter:  # daha önce kullanılmış ya da daha eski kod
            continue
        if hmac.compare_digest(code_at(secret, counter), code):
            return counter
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def grouped(secret: str) -> str:
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


def new_recovery_codes(count: int = 8) -> list[str]:
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(5)
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    normalized = "".join(ch for ch in code.lower() if ch.isalnum())
    return hashlib.sha256(normalized.encode()).hexdigest()
