"""
Haftalık öneri özeti (Pazartesi günleri `gunluk_bakim` içinden çağrılır):
- Destekçilere: son 7 günde yayınlanan ve profillerine uyan projeler
- Takım kaptanlarına: son 7 günde açılan, projelerine uyan destek çağrıları ve yeni destekçiler
Yalnızca e-posta bildirimlerini açık tutan ve adresini doğrulamış kullanıcılara gider.
"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.matching.engine import recommend_projects, recommend_sponsors
from apps.notifications.services import absolute, unsubscribe_token
from apps.projects.models import Project, Team
from apps.sponsors.models import Sponsor, SponsorCall


def _send(user, subject, template, context):
    unsubscribe = absolute(reverse("notifications:unsubscribe", args=[unsubscribe_token(user)]))
    body = render_to_string(template, {**context, "user": user, "unsubscribe": unsubscribe,
                                       "site": settings.KANAT, "base": settings.KANAT["SITE_URL"].rstrip("/")})
    EmailMessage(subject=f"{settings.KANAT['SITE_NAME']} — {subject}", body=body, to=[user.email],
                 headers={"List-Unsubscribe": f"<{unsubscribe}>",
                          "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}).send(fail_silently=True)


class Command(BaseCommand):
    help = "Haftalık eşleşme özeti e-postalarını gönderir."

    def handle(self, *args, **opts):
        since = timezone.now() - timedelta(days=7)
        sent = 0
        for sponsor in Sponsor.objects.filter(owner__is_active=True, owner__email_verified=True,
                                              owner__email_notifications=True).select_related("owner"):
            recs = [(p, m) for p, m in recommend_projects(sponsor, limit=30, min_score=50)
                    if p.created_at >= since][:5]
            if recs:
                _send(sponsor.owner, "bu hafta sana uygun yeni projeler", "notifications/digest_sponsor.txt",
                      {"sponsor": sponsor, "recs": recs})
                sent += 1

        new_calls = list(SponsorCall.objects.open().filter(created_at__gte=since).select_related("sponsor"))
        for team in Team.objects.filter(owner__is_active=True, owner__email_verified=True,
                                        owner__email_notifications=True).select_related("owner"):
            focus = Project.objects.public().filter(team=team).prefetch_related("needs__contributions").first()
            if focus is None:
                continue
            calls = [c for c in new_calls if c.accepts_category(focus.category) and c.kind in focus.need_kinds
                     and c.slots_left and not c.sponsor.blocks.filter(team=team).exists()][:3]
            sponsors = [(s, m) for s, m in recommend_sponsors(focus, limit=20, min_score=50)
                        if s.created_at >= since][:3]
            if calls or sponsors:
                _send(team.owner, "projen için bu haftanın fırsatları", "notifications/digest_team.txt",
                      {"team": team, "project": focus, "calls": calls, "sponsors": sponsors})
                sent += 1
        self.stdout.write(f"Haftalık özet: {sent} e-posta")
