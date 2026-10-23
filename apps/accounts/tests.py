import json

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ConsentRecord, User
from apps.accounts.services import make_verify_token
from apps.core.models import AuditLog
from apps.core.testutils import PASSWORD, clear_cache, make_team

REGISTER = {
    "role": "takim", "full_name": "Ali Veli", "email": "Ali@Ornek.test",
    "password1": "Cok-Guclu-Parola-42", "password2": "Cok-Guclu-Parola-42",
    "adult": "on", "privacy_notice": "on", "terms": "on",
}


class RegisterTests(TestCase):
    def setUp(self):
        clear_cache()

    def test_register_records_separate_consents(self):
        response = self.client.post(reverse("accounts:register"), REGISTER)
        self.assertRedirects(response, reverse("core:onboarding"), fetch_redirect_response=False)
        user = User.objects.get(email="ali@ornek.test")
        self.assertFalse(user.email_verified)
        self.assertIsNotNone(user.adult_declared_at)
        kinds = dict(user.consents.values_list("kind", "granted"))
        self.assertEqual(kinds, {"aydinlatma": True, "kullanim": True, "yas": True, "acik-riza": False})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/hesap/dogrula/", mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(action="register", user=user).exists())

    def test_marketing_consent_is_optional_but_recorded(self):
        self.client.post(reverse("accounts:register"), {**REGISTER, "marketing": "on"})
        user = User.objects.get(email="ali@ornek.test")
        self.assertTrue(ConsentRecord.current(user, "acik-riza"))

    def test_required_declarations(self):
        data = {k: v for k, v in REGISTER.items() if k != "privacy_notice"}
        response = self.client.post(reverse("accounts:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_weak_password_rejected(self):
        data = {**REGISTER, "password1": "12345678901", "password2": "12345678901"}
        self.client.post(reverse("accounts:register"), data)
        self.assertFalse(User.objects.exists())

    def test_existing_email_does_not_leak(self):
        make_team("ali@ornek.test")
        response = self.client.post(reverse("accounts:register"), REGISTER)
        self.assertTemplateUsed(response, "accounts/verify_sent.html")
        self.assertEqual(User.objects.filter(email="ali@ornek.test").count(), 1)
        self.assertIn("zaten kayıtlı", mail.outbox[0].body)


class LoginTests(TestCase):
    def setUp(self):
        clear_cache()
        self.user, _, _ = make_team("giris@ornek.test")

    def test_login_and_generic_error(self):
        bad = self.client.post(reverse("accounts:login"), {"email": "giris@ornek.test", "password": "yanlis"})
        self.assertContains(bad, "E-posta veya parola hatalı.")
        ok = self.client.post(reverse("accounts:login"), {"email": "GIRIS@ornek.test", "password": PASSWORD})
        self.assertRedirects(ok, reverse("core:dashboard"), fetch_redirect_response=False)

    def test_bruteforce_is_throttled_per_email(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"email": "giris@ornek.test", "password": "yanlis"})
        response = self.client.post(reverse("accounts:login"), {"email": "giris@ornek.test", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)

    def test_open_redirect_blocked(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=https://kotu.example/",
            {"email": "giris@ornek.test", "password": PASSWORD, "next": "https://kotu.example/"},
        )
        self.assertEqual(response["Location"], reverse("core:dashboard"))

    def test_logout_requires_post(self):
        self.client.login(email="giris@ornek.test", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class VerifyEmailTests(TestCase):
    def test_valid_and_tampered_tokens(self):
        user, _, _ = make_team("dogrula@ornek.test", verified=False)
        token = make_verify_token(user)
        self.client.get(reverse("accounts:verify", args=[token + "x"]))
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
        self.client.get(reverse("accounts:verify", args=[token]))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)


class KvkkRightsTests(TestCase):
    def setUp(self):
        clear_cache()
        self.user, self.team, self.project = make_team("kvkk@ornek.test")
        self.client.login(email="kvkk@ornek.test", password=PASSWORD)

    def test_export_contains_own_data(self):
        response = self.client.get(reverse("accounts:export"))
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        data = json.loads(response.content)
        self.assertEqual(data["hesap"]["e_posta"], "kvkk@ornek.test")
        self.assertEqual(data["takim"]["projeler"][0]["baslik"], self.project.title)

    def test_delete_account_anonymizes(self):
        response = self.client.post(reverse("accounts:delete"), {"password": PASSWORD, "confirm": "SİL"})
        self.assertRedirects(response, reverse("core:home"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.email.endswith("@silinmis.invalid"))
        self.assertEqual(self.user.full_name, "Silinmiş kullanıcı")
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(hasattr(User.objects.get(pk=self.user.pk), "team"))

    def test_delete_requires_password(self):
        self.client.post(reverse("accounts:delete"), {"password": "yanlis", "confirm": "SİL"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_marketing_consent_can_be_withdrawn(self):
        self.client.post(reverse("accounts:settings"), {"consent": "1", "marketing": "on"})
        self.assertTrue(ConsentRecord.current(self.user, "acik-riza"))
        self.client.post(reverse("accounts:settings"), {"consent": "1"})
        self.assertFalse(ConsentRecord.current(self.user, "acik-riza"))
