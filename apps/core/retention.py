"""KVKK saklama süreleri: süresi dolan kayıtları siler. Süreler settings.RETENTION_DAYS'te."""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


@transaction.atomic
def run_retention(now=None) -> dict:
    from apps.matching.models import Message, Report
    from apps.notifications.models import Notification

    from .models import AuditLog, DataRequest

    now = now or timezone.now()
    days = settings.RETENTION_DAYS

    def before(key):
        return now - timedelta(days=days[key])

    counts = {
        "guvenlik_kaydi": AuditLog.objects.filter(created_at__lt=before("audit_log")).delete()[0],
        "okunmus_bildirim": Notification.objects.filter(
            read_at__isnull=False, created_at__lt=before("notifications_read")).delete()[0],
        "eski_bildirim": Notification.objects.filter(created_at__lt=before("notifications_unread")).delete()[0],
        "kapanmis_sikayet": Report.objects.filter(resolved=True, created_at__lt=before("resolved_reports")).delete()[0],
        "yanitlanmis_kvkk_basvurusu": DataRequest.objects.filter(
            status=DataRequest.Status.DONE, created_at__lt=before("answered_data_requests")).delete()[0],
        "kapanmis_surec_mesaji": Message.objects.filter(
            request__status__in=["red", "geri_cekildi"], created_at__lt=before("closed_request_messages")
        ).delete()[0],
    }
    # Hiç doğrulanmamış ve profil oluşturulmamış hesaplar (veri minimizasyonu)
    User = get_user_model()
    stale = User.objects.filter(
        email_verified=False, is_staff=False, is_active=True,
        date_joined__lt=before("unverified_accounts"),
        team__isnull=True, sponsor__isnull=True, team_membership__isnull=True,
    ).filter(Q(last_login__isnull=True) | Q(last_login__lt=before("unverified_accounts")))
    counts["dogrulanmamis_hesap"] = stale.delete()[0]
    return counts
