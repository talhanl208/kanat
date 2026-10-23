from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.testutils import PASSWORD, age_request, clear_cache, make_sponsor, make_team
from apps.matching.engine import recommend_projects, recommend_sponsors, score_match
from apps.matching.forms import TeamAskForm
from apps.matching.models import Agreement, MentorSession, SupportRequest
from apps.rankings.models import PointEntry


class EngineTests(TestCase):
    def test_strong_match_has_reasons(self):
        _, _, project = make_team("t@ornek.test", city="Konya")
        _, sponsor = make_sponsor("s@ornek.test", city="Konya")
        result = score_match(project, sponsor)
        self.assertGreaterEqual(result.score, 90)
        self.assertEqual(result.level, "guclu")
        self.assertIn("motor", [k.lower() for k in result.matched_keywords])
        self.assertTrue(any("Konya" in r for r in result.reasons))

    def test_no_shared_support_kind_stays_low(self):
        _, _, project = make_team("t@ornek.test")
        _, sponsor = make_sponsor("s@ornek.test", support_types=["ulasim"])
        self.assertLessEqual(score_match(project, sponsor).score, 15)

    def test_recommendations_skip_inactive_and_engaged(self):
        _, _, project = make_team("t@ornek.test")
        _, s1 = make_sponsor("s1@ornek.test")
        _, s2 = make_sponsor("s2@ornek.test", accepting_requests=False)
        _, s3 = make_sponsor("s3@ornek.test")
        SupportRequest.objects.create(project=project, sponsor=s3, initiated_by="takim", kind="malzeme", note="x")
        names = [s.pk for s, _ in recommend_sponsors(project)]
        self.assertEqual(names, [s1.pk])
        self.assertEqual([p.pk for p, _ in recommend_projects(s3)], [])


class FullFlowTests(TestCase):
    """Teklif → kabul → sözleşme → iki onay → teslim → puan."""

    def setUp(self):
        clear_cache()
        self.team_user, self.team, self.project = make_team("takim@takim-ornek.test")
        self.sp_user, self.sponsor = make_sponsor("destek@firma-ornek.test")
        self.t = self.client_class()
        self.t.login(email="takim@takim-ornek.test", password=PASSWORD)
        self.s = self.client_class()
        self.s.login(email="destek@firma-ornek.test", password=PASSWORD)

    def _offer(self):
        response = self.s.post(reverse("matching:offer", args=[self.project.slug]), {
            "kind": "malzeme", "amount": "10000", "note": "Motorları biz verelim.",
        })
        req = SupportRequest.objects.get()
        self.assertRedirects(response, req.get_absolute_url())
        return req

    def test_complete_flow_awards_points_once(self):
        req = self._offer()
        self.assertEqual(req.initiated_by, "destekci")
        # Teklifi veren taraf kendi teklifini kabul edemez
        self.assertEqual(self.s.post(reverse("matching:respond", args=[req.pk]), {"karar": "kabul"}).status_code, 404)
        self.t.post(reverse("matching:respond", args=[req.pk]), {"karar": "kabul"})
        req.refresh_from_db()
        self.assertEqual(req.status, "kabul")

        self.t.post(reverse("matching:agreement_edit", args=[req.pk]), {
            "support_summary": "Motor desteği", "team_obligations": "Logo", "sponsor_obligations": "Teslim",
            "payment_channel": "Ürün olarak", "start_date": "2026-11-01", "end_date": "2027-03-01",
        })
        agreement = Agreement.objects.get(request=req)
        self.assertIn("SPONSORLUK VE DESTEK SÖZLEŞMESİ", agreement.body)
        self.assertEqual(len(agreement.body_hash), 64)

        url = reverse("matching:agreement_approve", args=[req.pk])
        self.t.post(url, {"password": "yanlis", "body_hash": agreement.body_hash})
        agreement.refresh_from_db()
        self.assertIsNone(agreement.team_approved_at)
        self.t.post(url, {"password": PASSWORD, "body_hash": "eski-ozet"})
        agreement.refresh_from_db()
        self.assertIsNone(agreement.team_approved_at)
        self.t.post(url, {"password": PASSWORD, "body_hash": agreement.body_hash})
        self.s.post(url, {"password": PASSWORD, "body_hash": agreement.body_hash})
        req.refresh_from_db()
        agreement.refresh_from_db()
        self.assertTrue(agreement.fully_approved)
        self.assertEqual(req.status, "anlasma")

        # Destekçi teslimi kendisi onaylayamaz
        self.assertEqual(self.s.get(reverse("matching:complete", args=[req.pk])).status_code, 404)
        age_request(req)
        motor = self.project.needs.get(kind="malzeme")
        self.t.post(reverse("matching:complete", args=[req.pk]), {
            "delivered_value": "10000", "rating": "5", "thanks_note": "Teşekkürler!",
            "thanks_public": "on", "received": "on", "fulfilled_needs": [motor.pk],
        })
        req.refresh_from_db()
        motor.refresh_from_db()
        self.assertEqual(req.status, "tamamlandi")
        self.assertTrue(motor.fulfilled)
        kinds = set(PointEntry.objects.values_list("kind", flat=True))
        self.assertEqual(kinds, {"tamamlanan_destek", "destek_degeri", "firsat_esitligi", "memnuniyet"})
        total = sum(PointEntry.objects.values_list("points", flat=True))
        self.assertEqual(total, 40 + 38 + 25 + 15)
        self.assertFalse(PointEntry.objects.filter(held=True).exists())

        from apps.rankings.services import award_completion
        self.assertEqual(award_completion(req), [])  # ikinci kez puan yok

    def test_text_change_resets_approvals(self):
        req = self._offer()
        self.t.post(reverse("matching:respond", args=[req.pk]), {"karar": "kabul"})
        form = {
            "support_summary": "A", "team_obligations": "B", "sponsor_obligations": "C",
            "payment_channel": "D", "start_date": "2026-11-01", "end_date": "2027-03-01",
        }
        self.t.post(reverse("matching:agreement_edit", args=[req.pk]), form)
        agreement = Agreement.objects.get()
        self.t.post(reverse("matching:agreement_approve", args=[req.pk]),
                    {"password": PASSWORD, "body_hash": agreement.body_hash})
        self.s.post(reverse("matching:agreement_edit", args=[req.pk]), {**form, "support_summary": "Değişti"})
        agreement.refresh_from_db()
        self.assertIsNone(agreement.team_approved_at)

    def test_third_party_gets_404_everywhere(self):
        req = self._offer()
        make_team("yabanci@ornek.test")
        other = self.client_class()
        other.login(email="yabanci@ornek.test", password=PASSWORD)
        for name in ("detail", "agreement"):
            self.assertEqual(other.get(reverse(f"matching:{name}", args=[req.pk])).status_code, 404)
        for name, data in (("message", {"body": "selam"}), ("respond", {"karar": "kabul"}),
                           ("withdraw", {}), ("report", {"reason": "spam"})):
            self.assertEqual(other.post(reverse(f"matching:{name}", args=[req.pk]), data).status_code, 404)
        req.refresh_from_db()
        self.assertEqual(req.status, "beklemede")
        self.assertFalse(req.messages.exists())

    def test_unverified_user_cannot_offer(self):
        user, sponsor = make_sponsor("dogrulanmamis@ornek.test", verified=False)
        c = self.client_class()
        c.login(email="dogrulanmamis@ornek.test", password=PASSWORD)
        response = c.post(reverse("matching:offer", args=[self.project.slug]),
                          {"kind": "malzeme", "note": "x"})
        self.assertRedirects(response, reverse("accounts:settings"))
        self.assertFalse(SupportRequest.objects.filter(sponsor=sponsor).exists())

    def test_team_cannot_ask_for_someone_elses_project(self):
        _, _, foreign = make_team("diger@ornek.test")
        form = TeamAskForm(data={"project": foreign.pk, "kind": "malzeme", "note": "x"},
                           team=self.team, sponsor=self.sponsor)
        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_message_is_escaped(self):
        req = self._offer()
        self.s.post(reverse("matching:message", args=[req.pk]), {"body": "<script>alert(1)</script>"})
        page = self.t.get(req.get_absolute_url()).content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_mentor_session_points_need_team_confirmation(self):
        req = SupportRequest.objects.create(project=self.project, sponsor=self.sponsor, initiated_by="takim",
                                            kind="mentorluk", mentor_hours=5, note="x", status="anlasma")
        self.s.post(reverse("matching:session_add", args=[req.pk]),
                    {"date": "2026-10-20", "hours": "2", "topic": "ROS"})
        session = MentorSession.objects.get()
        self.assertFalse(PointEntry.objects.exists())
        # Destekçi kendi oturumunu onaylayamaz
        self.assertEqual(self.s.post(reverse("matching:session_confirm", args=[req.pk, session.pk])).status_code, 404)
        self.t.post(reverse("matching:session_confirm", args=[req.pk, session.pk]))
        self.assertEqual(PointEntry.objects.get().points, 20)


class RequestModelTests(TestCase):
    def test_only_one_open_request_per_pair(self):
        _, _, project = make_team("t@ornek.test")
        _, sponsor = make_sponsor("s@ornek.test")
        SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="takim", kind="malzeme", note="x")
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="destekci",
                                          kind="malzeme", note="y")
        SupportRequest.objects.update(status="red")
        SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="destekci",
                                      kind="malzeme", note="z", amount=Decimal(1))
