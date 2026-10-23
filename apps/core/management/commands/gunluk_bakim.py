"""
Her gün bir kez çalıştırın (cron, systemd timer ya da docker-compose'daki zamanlayıcı):

    python manage.py gunluk_bakim

Yaptıkları
- Son tarihi 3 gün sonra olan projelere hatırlatma, dün süresi dolanlara bilgi
- 30 gündür yanıtlanmayan talepleri zaman aşımıyla kapatma
- Süresi geçen destek çağrılarını kapatma, eski davetleri silme
- KVKK saklama süreleri dolan kayıtları silme
- Ayın ilk 3 günü: geçen ayın ödülleri; yılın ilk 3 günü: geçen yılın ödülleri (tekrar çalışması güvenli)
- Pazartesi günleri: haftalık öneri özeti e-postası
"""
from datetime import date, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.retention import run_retention
from apps.matching.models import SupportRequest
from apps.notifications.models import Notification
from apps.notifications.services import notify, side_users, team_users
from apps.projects.models import Project, TeamInvite
from apps.rankings.models import Award
from apps.rankings.services import MONTHS_TR, Period, issue_awards, month_bounds
from apps.sponsors.models import SponsorCall

STALE_REQUEST_DAYS = 30


class Command(BaseCommand):
    help = "Günlük bakım: hatırlatmalar, zaman aşımları, saklama süreleri, ödüller, haftalık özet."

    def add_arguments(self, parser):
        parser.add_argument("--bugun", help="Test için tarih (YYYY-AA-GG)")
        parser.add_argument("--ozet", action="store_true", help="Haftalık özeti bugün de gönder")
        parser.add_argument("--ozet-yok", action="store_true", help="Haftalık özeti gönderme")

    def handle(self, *args, **opts):
        today = date.fromisoformat(opts["bugun"]) if opts["bugun"] else timezone.localdate()
        out = self.stdout.write

        # 1) Son tarih hatırlatmaları
        soon = Project.objects.filter(status=Project.Status.ACTIVE, deadline=today + timedelta(days=3)) \
            .select_related("team__owner")
        for p in soon:
            notify(team_users(p.team), Notification.Kind.DEADLINE, f"{p.title}: son tarihe 3 gün kaldı",
                   "Son tarih geçince proje destek arayan listelerden kalkar. Gerekirse tarihi güncelle.",
                   url=reverse("projects:edit", args=[p.slug]))
        expired = Project.objects.filter(status=Project.Status.ACTIVE, deadline=today - timedelta(days=1)) \
            .select_related("team__owner")
        for p in expired:
            notify(team_users(p.team), Notification.Kind.DEADLINE, f"{p.title}: son tarih geçti",
                   "Proje artık listelerde görünmüyor. Yeni bir tarih girebilir ya da 'tamamlandı' yapabilirsin.",
                   url=reverse("projects:edit", args=[p.slug]))
        out(f"Son tarih: {soon.count()} hatırlatma, {expired.count()} süre doldu bildirimi")

        # 2) Zaman aşımına uğrayan talepler
        cutoff = timezone.now() - timedelta(days=STALE_REQUEST_DAYS)
        stale = list(SupportRequest.objects.filter(status="beklemede", created_at__lt=cutoff)
                     .select_related("project__team__owner", "sponsor__owner"))
        for req in stale:
            req.status = SupportRequest.Status.WITHDRAWN
            req.save(update_fields=["status"])
            notify(side_users(req, "takim") + side_users(req, "destekci"), Notification.Kind.RESPONSE,
                   "Bir talep yanıtsız kaldığı için kapandı",
                   f"{req.project.title} ↔ {req.sponsor.name} ({STALE_REQUEST_DAYS} gün)",
                   url=req.get_absolute_url(), email=False)
        out(f"Zaman aşımı: {len(stale)} talep kapatıldı")

        # 3) Çağrılar ve davetler
        closed = SponsorCall.objects.filter(status=SponsorCall.Status.OPEN, deadline__lt=today) \
            .update(status=SponsorCall.Status.CLOSED)
        old_invites = TeamInvite.objects.filter(
            Q(expires_at__lt=timezone.now() - timedelta(days=30)) |
            Q(accepted_at__lt=timezone.now() - timedelta(days=30))
        ).delete()[0]
        out(f"Çağrı: {closed} kapatıldı; eski davet: {old_invites} silindi")

        # 4) Saklama süreleri
        counts = run_retention()
        out("Saklama süresi temizliği: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

        # 5) Ödüller
        if today.day <= 3:
            prev = today.replace(day=1) - timedelta(days=1)
            start, end = month_bounds(prev.year, prev.month)
            awards = issue_awards(Period("ay", f"{MONTHS_TR[prev.month - 1]} {prev.year}", start, end),
                                  Award.Kind.MONTH)
            out(f"Ayın Kanadı ({MONTHS_TR[prev.month - 1]} {prev.year}): {len(awards)} ödül")
            if today.month == 1:
                y = today.year - 1
                awards = issue_awards(Period("yil", str(y), date(y, 1, 1), date(y + 1, 1, 1)), Award.Kind.YEAR)
                out(f"Yılın Ankası ({y}): {len(awards)} ödül")

        # 6) Haftalık özet
        if (today.weekday() == 0 or opts["ozet"]) and not opts["ozet_yok"]:
            call_command("haftalik_ozet", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Günlük bakım tamamlandı."))
