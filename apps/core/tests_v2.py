from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.checks import run_checks
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog, VerificationRequest
from apps.core.retention import run_retention
from apps.core.testutils import PASSWORD, clear_cache, make_sponsor, make_team, make_user
from apps.core.verification import auto_verify_sponsor, auto_verify_team, domains_match
from apps.matching.models import SupportRequest
from apps.notifications.models import Notification

User = get_user_model()


class AutoVerificationTests(TestCase):
    def test_team_with_edu_email(self):
        _, team, _ = make_team("ali@ogr.subu.edu.tr", team_verified=False)
        self.assertTrue(auto_verify_team(team))
        self.assertEqual(team.verification_method, "edu")

    def test_team_with_unverified_edu_email_is_not_verified(self):
        _, team, _ = make_team("ali@ogr.subu.edu.tr", verified=False, team_verified=False)
        self.assertFalse(auto_verify_team(team))

    def test_sponsor_domain_match(self):
        _, sponsor = make_sponsor("info@anadoludevre.com.tr", sponsor_verified=False,
                                  website="https://www.anadoludevre.com.tr")
        self.assertTrue(auto_verify_sponsor(sponsor))
        sponsor.website = "https://baskasite.com"
        self.assertFalse(auto_verify_sponsor(sponsor))  # koşul kalkınca otomatik rozet düşer

    def test_domain_tricks_rejected(self):
        self.assertFalse(domains_match("gmail.com", "gmail.com"))
        self.assertFalse(domains_match("evil.com.tr", "com.tr"))
        self.assertTrue(domains_match("mail.firma.com", "firma.com"))
        self.assertFalse(domains_match("firma.com", "mail.firma.com"))

    def test_verification_request_and_admin_approval(self):
        clear_cache()
        _, sponsor = make_sponsor("mentor@gmail.com", sponsor_verified=False)
        c = self.client_class()
        c.login(email="mentor@gmail.com", password=PASSWORD)
        c.post(reverse("core:verification"), {"evidence_url": "https://linkedin.example/ben", "note": "Mentörüm."})
        vr = VerificationRequest.objects.get()
        admin = User.objects.create_superuser(email="admin@kanat.test", password=PASSWORD, full_name="Yönetici")
        from apps.core.admin import _decide

        class R:
            user = admin
        self.assertEqual(_decide(R, VerificationRequest.objects.all(), True), 1)
        sponsor.refresh_from_db()
        self.assertTrue(sponsor.verified)
        self.assertEqual(sponsor.verification_method, "yonetici")
        self.assertTrue(Notification.objects.filter(user=sponsor.owner, kind="dogrulama").exists())
        self.assertEqual(vr.pk, VerificationRequest.objects.get(status="onaylandi").pk)

    def test_http_evidence_rejected(self):
        clear_cache()
        make_sponsor("m2@gmail.com", sponsor_verified=False)
        c = self.client_class()
        c.login(email="m2@gmail.com", password=PASSWORD)
        c.post(reverse("core:verification"), {"evidence_url": "javascript:alert(1)", "note": "x"})
        self.assertFalse(VerificationRequest.objects.exists())


class RetentionTests(TestCase):
    def test_old_records_are_removed(self):
        old = timezone.now() - timedelta(days=800)
        log = AuditLog.objects.create(action="login")
        AuditLog.objects.filter(pk=log.pk).update(created_at=old)
        fresh = AuditLog.objects.create(action="login")
        stale = make_user("hayalet@ornek.test", "takim", verified=False)
        User.objects.filter(pk=stale.pk).update(date_joined=timezone.now() - timedelta(days=30))
        keeper = make_user("yeni@ornek.test", "takim", verified=False)
        counts = run_retention()
        self.assertEqual(counts["guvenlik_kaydi"], 1)
        self.assertTrue(AuditLog.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(User.objects.filter(pk=stale.pk).exists())
        self.assertTrue(User.objects.filter(pk=keeper.pk).exists())


class MaintenanceCommandTests(TestCase):
    def test_daily_job(self):
        _, team, project = make_team("takim@takim.test")
        project.deadline = timezone.localdate() + timedelta(days=3)
        project.save()
        _, sponsor = make_sponsor("destek@firma.test")
        req = SupportRequest.objects.create(project=project, sponsor=sponsor, initiated_by="takim",
                                            kind="malzeme", note="x")
        SupportRequest.objects.filter(pk=req.pk).update(created_at=timezone.now() - timedelta(days=31))
        out = StringIO()
        call_command("gunluk_bakim", "--ozet-yok", stdout=out)
        req.refresh_from_db()
        self.assertEqual(req.status, "geri_cekildi")
        self.assertTrue(Notification.objects.filter(kind="son_tarih", user=team.owner).exists())
        self.assertIn("tamamlandı", out.getvalue())

    def test_weekly_digest_runs(self):
        make_team("takim@takim.test")
        make_sponsor("destek@firma.test")
        out = StringIO()
        call_command("haftalik_ozet", stdout=out)
        self.assertIn("Haftalık özet", out.getvalue())


class HealthAndChecksTests(TestCase):
    def test_health(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.json(), {"durum": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_deploy_check_warns_about_local_cache(self):
        ids = {m.id for m in run_checks(include_deployment_checks=True)}
        self.assertIn("kanat.W001", ids)
