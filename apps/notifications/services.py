"""
Bildirim gönderimi.

- Her bildirim uygulama içinde (zil simgesi) görünür.
- E-posta yalnızca: kullanıcı e-posta bildirimlerini kapatmadıysa ve adresi doğrulanmışsa gider.
- Mesaj bildirimleri seyreltilir: aynı yazışma için 30 dakika içinde okunmamış bir bildirim
  e-postası gittiyse yenisi gönderilmez (posta kutusu selini önler).
- E-postalar işlem (transaction) tamamlandıktan sonra gönderilir; gönderim hatası işlemi bozmaz.
- Bu e-postalar hizmetin parçası olan işlem bildirimleridir; pazarlama içermez.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Notification

log = logging.getLogger("kanat")
UNSUBSCRIBE_SALT = "kanat.notifications.unsubscribe.v1"
MESSAGE_EMAIL_COOLDOWN = timedelta(minutes=30)


def absolute(path: str) -> str:
    return settings.KANAT["SITE_URL"].rstrip("/") + path


# --------------------------------------------------------------------------- #
# Alıcı yardımcıları
# --------------------------------------------------------------------------- #
def team_users(team) -> list:
    users = [team.owner] + [m.user for m in team.memberships.select_related("user")]
    return [u for u in users if u.is_active]


def captain_users(team) -> list:
    return [team.owner] if team.owner.is_active else []


def sponsor_users(sponsor) -> list:
    return [sponsor.owner] if sponsor.owner.is_active else []


def side_users(support_request, side: str) -> list:
    if side == "takim":
        return team_users(support_request.project.team)
    return sponsor_users(support_request.sponsor)


def staff_users() -> list:
    return list(get_user_model().objects.filter(is_staff=True, is_active=True))


# --------------------------------------------------------------------------- #
# Gönderim
# --------------------------------------------------------------------------- #
def notify(users, kind: str, title: str, body: str = "", url: str = "", email: bool = True,
           exclude=None) -> list[Notification]:
    if url and (not url.startswith("/") or url.startswith("//") or url.startswith("/\\")):
        raise ValueError("Bildirim bağlantısı site içi bir yol olmalı.")
    seen, recipients = set(), []
    for user in users:
        if user is None or user.pk in seen or (exclude is not None and user.pk == exclude.pk):
            continue
        seen.add(user.pk)
        recipients.append(user)
    if not recipients:
        return []
    created = Notification.objects.bulk_create([
        Notification(user=u, kind=kind, title=title[:150], body=body[:400], url=url[:200])
        for u in recipients
    ])
    if email:
        ids = [n.pk for n in created if n.pk]
        if not ids:  # bazı veritabanlarında bulk_create pk döndürmez
            ids = list(Notification.objects.filter(
                user__in=recipients, kind=kind, title=title[:150], emailed_at__isnull=True
            ).values_list("pk", flat=True))
        transaction.on_commit(lambda: send_pending_emails(ids))
    return created


def _should_email(n: Notification) -> bool:
    user = n.user
    if not (user.is_active and user.email_verified and user.email_notifications):
        return False
    if n.kind == Notification.Kind.MESSAGE:
        recent = Notification.objects.filter(
            user=user, kind=n.kind, url=n.url, read_at__isnull=True,
            emailed_at__gte=timezone.now() - MESSAGE_EMAIL_COOLDOWN,
        ).exclude(pk=n.pk)
        if recent.exists():
            return False
    return True


def unsubscribe_token(user) -> str:
    return signing.dumps({"u": user.pk}, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str):
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return get_user_model().objects.filter(pk=data.get("u"), is_active=True).first()


def send_pending_emails(ids) -> int:
    sent = 0
    for n in Notification.objects.filter(pk__in=ids, emailed_at__isnull=True).select_related("user"):
        if not _should_email(n):
            continue
        unsubscribe = absolute(reverse("notifications:unsubscribe", args=[unsubscribe_token(n.user)]))
        body = render_to_string("notifications/email.txt", {
            "n": n, "user": n.user, "link": absolute(n.url) if n.url else absolute("/bildirimler/"),
            "unsubscribe": unsubscribe, "site": settings.KANAT,
        })
        message = EmailMessage(
            subject=f"{settings.KANAT['SITE_NAME']} — {n.title}",
            body=body, to=[n.user.email],
            headers={
                "List-Unsubscribe": f"<{unsubscribe}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "Auto-Submitted": "auto-generated",
            },
        )
        try:
            message.send()
        except Exception:  # noqa: BLE001 - e-posta sorunu kullanıcı işlemini bozmamalı
            log.exception("Bildirim e-postası gönderilemedi (bildirim #%s)", n.pk)
            continue
        Notification.objects.filter(pk=n.pk).update(emailed_at=timezone.now())
        sent += 1
    return sent
