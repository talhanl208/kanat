from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.testutils import PASSWORD, age_request, clear_cache, make_sponsor, make_team
from apps.matching.engine import keyword_in, recommend_projects, recommend_sponsors
from apps.matching.models import Block, SupportRequest
from apps.notifications.models import Notification
from apps.rankings.models import PointEntry
from apps.rankings.services import award_completion
from apps.sponsors.models import SponsorCall


class KeywordTests(TestCase):
    def test_word_start_matching(self):
        self.assertTrue(keyword_in("motor", "4 adet motorlar ve surucu"))
        self.assertFalse(keyword_in("motor", "elektromotor seti"))
        self.assertTrue(keyword_in("pcb baski", "kart icin pcb baskisi"))
        self.assertFalse(keyword_in("ai", "aile destegi"))  # 2 harfliler tam kelime olmalı
        self.assertTrue(keyword_in("ai", "ai modeli"))


class BlockTests(TestCase):
    def setUp(self):
        clear_cache()
        self.tu, self.team, self.project = make_team("takim@takim.test")
        self.su, self.sponsor = make_sponsor("destek@firma.test")
        self.req = SupportRequest.objects.create(project=self.project, sponsor=self.sponsor,
                                                 initiated_by="destekci", kind="malzeme", note="x")
        self.t = self.client_class()
        self.t.login(email="takim@takim.test", password=PASSWORD)
        self.s = self.client_class()
        self.s.login(email="destek@firma.test", password=PASSWORD)

    def test_block_closes_pending_and_prevents_contact(self):
        self.t.post(reverse("matching:block", args=[self.req.pk]))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "geri_cekildi")
        self.assertEqual(self.s.get(reverse("matching:offer", args=[self.project.slug])).status_code, 404)
        self.assertEqual(self.s.post(reverse("matching:message", args=[self.req.pk]), {"body": "x"}).status_code, 404)
        self.assertEqual(recommend_sponsors(self.project), [])
        self.assertEqual(recommend_projects(self.sponsor), [])
        self.assertNotContains(self.s.get(reverse("projects:list")), self.project.title)

    def test_only_blocker_can_unblock(self):
        self.t.post(reverse("matching:block", args=[self.req.pk]))
        self.s.post(reverse("matching:unblock", args=[self.req.pk]))
        self.assertTrue(Block.objects.exists())
        self.t.post(reverse("matching:unblock", args=[self.req.pk]))
        self.assertFalse(Block.objects.exists())


class CapacityTests(TestCase):
    def test_full_sponsor_is_not_recommended_and_cannot_be_asked(self):
        clear_cache()
        _, team, project = make_team("takim@takim.test")
        _, other_team_project = make_team("diger@diger.test")[1:]
        _, sponsor = make_sponsor("destek@firma.test", max_active_projects=1)
        SupportRequest.objects.create(project=other_team_project, sponsor=sponsor, initiated_by="takim",
                                      kind="malzeme", note="x", status="anlasma")
        self.assertTrue(sponsor.at_capacity)
        self.assertEqual(recommend_sponsors(project), [])
        c = self.client_class()
        c.login(email="takim@takim.test", password=PASSWORD)
        response = c.get(reverse("matching:ask", args=[sponsor.slug]))
        self.assertRedirects(response, sponsor.get_absolute_url())


class CoFundingTests(TestCase):
    def test_two_sponsors_share_a_need(self):
        _, team, project = make_team("takim@takim.test")
        need = project.needs.get(kind="malzeme")  # 10.000 ₺
        _, s1 = make_sponsor("bir@birinci.test")
        _, s2 = make_sponsor("iki@ikinci.test")
        r1 = SupportRequest.objects.create(project=project, sponsor=s1, initiated_by="destekci", kind="malzeme",
                                           note="x", amount=Decimal(6000), need=need, status="anlasma")
        need.refresh_from_db()
        self.assertEqual(need.remaining_amount, Decimal(4000))
        self.assertEqual(need.funded_percent, 60)
        r1.status, r1.delivered_value, r1.completed_at = "tamamlandi", Decimal(6000), timezone.now()
        r1.save()
        age_request(r1)
        award_completion(r1)
        self.assertFalse(PointEntry.objects.filter(kind="ortak_kanat").exists())

        r2 = SupportRequest.objects.create(project=project, sponsor=s2, initiated_by="destekci", kind="malzeme",
                                           note="y", amount=Decimal(4000), need=need, status="anlasma")
        age_request(r2)
        r2.status, r2.delivered_value, r2.completed_at = "tamamlandi", Decimal(4000), timezone.now()
        r2.save()
        award_completion(r2)
        self.assertEqual(set(PointEntry.objects.filter(kind="ortak_kanat").values_list("sponsor", flat=True)),
                         {s1.pk, s2.pk})
        need.refresh_from_db()
        self.assertEqual(need.delivered_amount, Decimal(10000))

    def test_completion_view_auto_closes_funded_need(self):
        clear_cache()
        _, team, project = make_team("takim@takim.test")
        need = project.needs.get(kind="malzeme")
        _, sponsor = make_sponsor("destek@firma.test")
        req = SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="destekci",
                                            kind="malzeme", note="x", amount=Decimal(10000), need=need,
                                            status="anlasma")
        age_request(req)
        c = self.client_class()
        c.login(email="takim@takim.test", password=PASSWORD)
        c.post(reverse("matching:complete", args=[req.pk]), {
            "delivered_value": "10000", "rating": "5", "thanks_note": "", "received": "on",
        })
        need.refresh_from_db()
        self.assertTrue(need.fulfilled)


class CallTests(TestCase):
    def setUp(self):
        clear_cache()
        self.tu, self.team, self.project = make_team("takim@takim.test")
        self.su, self.sponsor = make_sponsor("destek@firma.test")
        self.s = self.client_class()
        self.s.login(email="destek@firma.test", password=PASSWORD)
        self.t = self.client_class()
        self.t.login(email="takim@takim.test", password=PASSWORD)

    def _create_call(self, **extra):
        data = {"title": "Motor desteği", "kind": "malzeme", "description": "Açıklama", "categories": ["ika"],
                "amount_per_team": "5000", "mentor_hours": "", "slots": "1",
                "deadline": (timezone.localdate() + timedelta(days=10)).isoformat()}
        data.update(extra)
        self.s.post(reverse("sponsors:call_create"), data)
        return SponsorCall.objects.order_by("-pk").first()

    def test_call_notifies_matching_team_and_accepts_application(self):
        call = self._create_call()
        self.assertTrue(Notification.objects.filter(user=self.tu, kind="cagri").exists())
        self.t.post(reverse("matching:call_apply", args=[call.pk]),
                    {"project": self.project.pk, "need": "", "note": "Biz uygunuz."})
        req = SupportRequest.objects.get()
        self.assertEqual((req.call, req.kind, req.amount), (call, "malzeme", Decimal(5000)))
        # aynı çağrıya ikinci başvuru olmaz
        self.t.post(reverse("matching:call_apply", args=[call.pk]),
                    {"project": self.project.pk, "need": "", "note": "Tekrar"})
        self.assertEqual(SupportRequest.objects.count(), 1)

    def test_slots_are_enforced(self):
        call = self._create_call()
        _, other_team, other_project = make_team("diger@diger.test")
        SupportRequest.objects.create(project=other_project, sponsor=self.sponsor, initiated_by="takim",
                                      kind="malzeme", note="x", call=call, status="kabul")
        self.assertFalse(call.is_open)
        self.t.post(reverse("matching:call_apply", args=[call.pk]),
                    {"project": self.project.pk, "need": "", "note": "Biz de"})
        self.assertFalse(SupportRequest.objects.filter(project=self.project).exists())

    def test_past_deadline_rejected_and_other_sponsor_cannot_edit(self):
        self._create_call(deadline=(timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertFalse(SponsorCall.objects.exists())
        call = self._create_call()
        make_sponsor("baska@baska.test")
        c = self.client_class()
        c.login(email="baska@baska.test", password=PASSWORD)
        self.assertEqual(c.get(reverse("sponsors:call_edit", args=[call.pk])).status_code, 404)
        self.assertEqual(c.post(reverse("sponsors:call_close", args=[call.pk])).status_code, 404)

    def test_category_mismatch_cannot_apply(self):
        call = self._create_call(categories=["roket"])
        self.t.post(reverse("matching:call_apply", args=[call.pk]),
                    {"project": self.project.pk, "need": "", "note": "x"})
        self.assertFalse(SupportRequest.objects.exists())
