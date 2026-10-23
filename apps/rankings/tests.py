from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.core.testutils import make_sponsor, make_team
from apps.matching.models import SupportRequest
from apps.rankings.models import Award, PointEntry
from apps.rankings.services import Period, issue_awards, leaderboard, resolve_period, title_for, value_points


class PointsTests(TestCase):
    def test_square_root_scaling(self):
        self.assertEqual(value_points(1000), 12)
        self.assertEqual(value_points(10000), 38)
        self.assertEqual(value_points(100000), 120)
        self.assertEqual(value_points(10_000_000), 150)
        self.assertEqual(value_points(None), 0)

    def test_titles(self):
        self.assertEqual(title_for(0)["name"], "Kanat adayı")
        self.assertEqual(title_for(150)["name"], "Doğan")
        self.assertEqual(title_for(150)["to_next"], 150)
        self.assertEqual(title_for(5000)["name"], "Anka")
        self.assertIsNone(title_for(5000)["next_name"])


class LeaderboardTests(TestCase):
    def setUp(self):
        _, _, project = make_team("t@ornek.test")
        self.a_user, self.a = make_sponsor("a@ornek.test", league="kobi")
        self.b_user, self.b = make_sponsor("b@ornek.test", league="buyuk")
        req = SupportRequest.objects.create(project=project, sponsor=self.a, initiated_by="takim",
                                            kind="malzeme", note="x", status="tamamlandi")
        PointEntry.objects.create(sponsor=self.a, request=req, kind="tamamlanan_destek", points=40)
        PointEntry.objects.create(sponsor=self.b, kind="tamamlanan_destek", points=90)
        PointEntry.objects.create(sponsor=self.b, kind="mentorluk", points=500, is_void=True)

    def test_void_entries_ignored_and_leagues_filter(self):
        rows = leaderboard(resolve_period("ay"))
        self.assertEqual([(r.pk, r.total) for r in rows], [(self.b.pk, 90), (self.a.pk, 40)])
        self.assertEqual([r.pk for r in leaderboard(resolve_period("ay"), league="kobi")], [self.a.pk])

    def test_awards_are_issued_once(self):
        today = date.today()
        period = resolve_period("ay")
        first = issue_awards(period, Award.Kind.MONTH)
        self.assertTrue(first)
        self.assertEqual(issue_awards(period, Award.Kind.MONTH), [])
        award = Award.objects.filter(league="").order_by("rank").first()
        self.assertEqual(award.sponsor, self.b)
        page = self.client.get(reverse("rankings:certificate", args=[award.code.lower()]))
        self.assertContains(page, self.b.name)
        self.assertIsInstance(period, Period)
        self.assertEqual(period.start.month, today.month)

    def test_badge_svg_escapes_names(self):
        self.a.name = '<script>alert("x")</script>'
        self.a.save()
        response = self.client.get(reverse("rankings:badge", args=[self.a.slug]))
        self.assertEqual(response["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertNotIn(b"<script>", response.content)
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])

    def test_unverified_sponsor_not_ranked(self):
        self.b.verified = False
        self.b.save()
        rows = leaderboard(resolve_period("ay"))
        self.assertEqual([r.pk for r in rows], [self.a.pk])

    def test_held_points_not_counted(self):
        PointEntry.objects.filter(sponsor=self.b).update(held=True)
        self.assertEqual([r.pk for r in leaderboard(resolve_period("ay"))], [self.a.pk])

    def test_leaderboard_page(self):
        response = self.client.get(reverse("rankings:leaderboard") + "?donem=yil&lig=kobi")
        self.assertContains(response, self.a.name)
        self.assertNotContains(response, self.b.name)
