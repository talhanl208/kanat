from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.models import AuditLog
from apps.core.testutils import age_request, make_sponsor, make_team
from apps.matching.models import MentorSession, SupportRequest
from apps.rankings.models import PointEntry
from apps.rankings.services import award_completion, award_mentor_session, suspicion_reasons


def complete(project, sponsor, value=10000, rating=5):
    req = SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="destekci", kind="malzeme",
                                        note="x", amount=Decimal(value), status="anlasma")
    age_request(req)
    req.status, req.delivered_value, req.rating, req.completed_at = "tamamlandi", Decimal(value), rating, timezone.now()
    req.save()
    award_completion(req)
    return req


class AntiGamingTests(TestCase):
    def setUp(self):
        self.tu, self.team, self.project = make_team("takim@takim.test")
        self.su, self.sponsor = make_sponsor("destek@firma.test")

    def _points(self, req):
        return sum(PointEntry.objects.filter(request=req).values_list("points", flat=True))

    def test_repeat_support_to_same_team_diminishes(self):
        first = complete(self.project, self.sponsor)
        second = complete(self.project, self.sponsor)
        third = complete(self.project, self.sponsor)
        self.assertEqual(self._points(first), 40 + 38 + 25 + 15)
        self.assertEqual(self._points(second), 20 + 19 + 15)
        self.assertEqual(self._points(third), 0)

    def test_first_team_bonus_requires_verified_team(self):
        self.team.verified = False
        self.team.save()
        req = complete(self.project, self.sponsor)
        self.assertFalse(PointEntry.objects.filter(request=req, kind="firsat_esitligi").exists())

    def test_same_network_is_held_for_review(self):
        AuditLog.objects.create(user=self.tu, action="login", ip_hash="ayni")
        AuditLog.objects.create(user=self.su, action="login", ip_hash="ayni")
        req = complete(self.project, self.sponsor)
        entries = PointEntry.objects.filter(request=req)
        self.assertTrue(entries.exists())
        self.assertTrue(all(e.held for e in entries))
        self.assertIn("aynı ağ", entries.first().hold_reason)

    def test_same_company_domain_and_fast_completion_flagged(self):
        _, team, project = make_team("ali@firma.test")
        req = SupportRequest.objects.create(project=project, sponsor=self.sponsor, initiated_by="destekci",
                                            kind="malzeme", note="x", status="tamamlandi",
                                            completed_at=timezone.now())
        reasons = suspicion_reasons(req)
        self.assertTrue(any("alan adı" in r for r in reasons))
        self.assertTrue(any("24 saat" in r for r in reasons))

    def test_free_email_domains_are_not_flagged(self):
        _, team, project = make_team("ali@gmail.com")
        _, sponsor = make_sponsor("veli@gmail.com")
        req = SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="destekci",
                                            kind="malzeme", note="x", status="tamamlandi")
        age_request(req, days=5)
        req.completed_at = timezone.now()
        self.assertEqual(suspicion_reasons(req), [])

    def test_high_value_to_unverified_team_is_held(self):
        self.team.verified = False
        self.team.save()
        req = complete(self.project, self.sponsor, value=80000)
        self.assertTrue(PointEntry.objects.filter(request=req, held=True).exists())

    def test_mentor_hours_capped_per_month(self):
        req = SupportRequest.objects.create(project=self.project, sponsor=self.sponsor, initiated_by="takim",
                                            kind="mentorluk", note="x", status="anlasma")
        day = date.today().replace(day=1)
        total = 0
        for i in range(12):  # 12 x 2 saat = 24 saat; ayda en çok 20 saat sayılır
            s = MentorSession.objects.create(request=req, date=day + timedelta(days=i), hours=Decimal(2),
                                             topic="t", confirmed_at=timezone.now())
            entry = award_mentor_session(s)
            total += entry.points if entry else 0
        self.assertEqual(total, 200)
