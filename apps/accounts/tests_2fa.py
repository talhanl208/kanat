from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts import services, totp
from apps.accounts.models import ConsentRecord
from apps.core.testutils import PASSWORD, clear_cache, make_sponsor, make_team

User = get_user_model()


class TotpAlgorithmTests(TestCase):
    def test_rfc6238_vector(self):
        # RFC 6238 Ek B: ASCII "12345678901234567890", T=59 -> 8 hanede 94287082
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(totp.code_at(secret, 1, digits=8), "94287082")
        self.assertEqual(totp.verify(secret, "287082", now=59), 1)

    def test_replay_and_window(self):
        secret = totp.new_secret()
        code = totp.code_at(secret, totp.current_counter())
        counter = totp.verify(secret, code)
        self.assertIsNotNone(counter)
        self.assertIsNone(totp.verify(secret, code, last_counter=counter))
        self.assertIsNone(totp.verify(secret, "12345"))
        self.assertIsNone(totp.verify(secret, totp.code_at(secret, totp.current_counter() - 5)))

    def test_recovery_code_hashing_ignores_format(self):
        self.assertEqual(totp.hash_recovery_code("ABCDE-12345"), totp.hash_recovery_code("abcde12345"))


class TwoFactorFlowTests(TestCase):
    def setUp(self):
        clear_cache()
        self.user, _, _ = make_team("iki@ornek.test")

    def _enable(self):
        self.client.login(email="iki@ornek.test", password=PASSWORD)
        self.client.get(reverse("accounts:two_factor"))
        self.user.refresh_from_db()
        code = totp.code_at(self.user.totp_secret, totp.current_counter())
        response = self.client.post(reverse("accounts:two_factor"), {"code": code})
        self.user.refresh_from_db()
        self.client.logout()
        return response

    def test_enable_shows_recovery_codes_once(self):
        response = self._enable()
        self.assertTrue(self.user.totp_enabled)
        self.assertEqual(len(response.context["recovery_codes"]), 8)
        self.assertEqual(self.user.recovery_codes.count(), 8)

    def test_login_requires_second_factor(self):
        self._enable()
        response = self.client.post(reverse("accounts:login"), {"email": "iki@ornek.test", "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:login_2fa"))
        self.assertNotIn("_auth_user_id", self.client.session)  # henüz giriş yok

        bad = self.client.post(reverse("accounts:login_2fa"), {"code": "000000"})
        self.assertContains(bad, "Kod hatalı")
        self.assertNotIn("_auth_user_id", self.client.session)

        # Aynı zaman dilimindeki kod kurulumda kullanıldı; bir sonraki dilimin kodunu üret
        self.user.refresh_from_db()
        next_code = totp.code_at(self.user.totp_secret, self.user.totp_last_counter + 1)
        ok = self.client.post(reverse("accounts:login_2fa"), {"code": next_code})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertTrue(self.client.session["otp_verified"])

    def test_recovery_code_works_once(self):
        response = self._enable()
        code = response.context["recovery_codes"][0]
        for expected_login in (True, False):
            self.client.logout()
            self.client.post(reverse("accounts:login"), {"email": "iki@ornek.test", "password": PASSWORD})
            self.client.post(reverse("accounts:login_2fa"), {"code": code})
            self.assertEqual("_auth_user_id" in self.client.session, expected_login)

    def test_disable_requires_password_and_code(self):
        response = self._enable()
        recovery = response.context["recovery_codes"][1]
        self.client.login(email="iki@ornek.test", password=PASSWORD)
        self.client.post(reverse("accounts:two_factor"), {"disable": "1", "password": "yanlis", "code": recovery})
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        self.client.post(reverse("accounts:two_factor"), {"disable": "1", "password": PASSWORD, "code": recovery})
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.recovery_codes.count(), 0)


@override_settings(ADMIN_REQUIRE_2FA=True)
class AdminTwoFactorTests(TestCase):
    def setUp(self):
        clear_cache()
        self.admin = User.objects.create_superuser(email="yonetici@ornek.test", password=PASSWORD,
                                                   full_name="Yönetici")

    def test_admin_login_page_redirects_to_kanat_login(self):
        response = self.client.get("/yonetim-kapisi/login/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("accounts:login")))

    def test_staff_without_2fa_is_sent_to_setup(self):
        self.client.login(email="yonetici@ornek.test", password=PASSWORD)
        response = self.client.get("/yonetim-kapisi/")
        self.assertTrue(response["Location"].startswith(reverse("accounts:two_factor")))

    def test_staff_with_2fa_needs_verified_session(self):
        self.admin.totp_secret = totp.new_secret()
        self.admin.save()
        services.enable_totp(self.admin, totp.code_at(self.admin.totp_secret, totp.current_counter()))
        self.client.login(email="yonetici@ornek.test", password=PASSWORD)  # 2FA'sız oturum
        response = self.client.get("/yonetim-kapisi/")
        self.assertTrue(response["Location"].startswith(reverse("accounts:two_factor_verify")))
        session = self.client.session
        session["otp_verified"] = True
        session.save()
        self.assertEqual(self.client.get("/yonetim-kapisi/").status_code, 200)


class EmailChangeTests(TestCase):
    def setUp(self):
        clear_cache()
        self.user, _, _ = make_team("eski@ornek.test")
        self.client.login(email="eski@ornek.test", password=PASSWORD)

    def test_change_flow(self):
        self.client.post(reverse("accounts:email_change"), {"new_email": "Yeni@Ornek.test", "password": PASSWORD})
        self.assertEqual(mail.outbox[-1].to, ["yeni@ornek.test"])
        link = next(line for line in mail.outbox[-1].body.splitlines() if "/hesap/eposta/onayla/" in line)
        path = link[link.index("/hesap/"):].strip()
        self.client.get(path)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "yeni@ornek.test")
        self.assertEqual(mail.outbox[-1].to, ["eski@ornek.test"])  # eski adrese bilgi
        self.assertEqual(self.client.get(path).status_code, 302)  # ikinci kullanım geçersiz
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "yeni@ornek.test")

    def test_taken_email_is_not_revealed(self):
        make_sponsor("dolu@ornek.test")
        outbox = len(mail.outbox)
        response = self.client.post(reverse("accounts:email_change"),
                                    {"new_email": "dolu@ornek.test", "password": PASSWORD}, follow=True)
        self.assertContains(response, "onay bağlantısı gönderdik")
        self.assertEqual(len(mail.outbox), outbox)


class ReconsentTests(TestCase):
    def test_outdated_terms_are_prompted_and_recorded(self):
        user, _, _ = make_team("onay@ornek.test")
        ConsentRecord.objects.create(user=user, kind="aydinlatma", version="1.0", granted=True)
        ConsentRecord.objects.create(user=user, kind="kullanim", version="1.0", granted=True)
        self.client.login(email="onay@ornek.test", password=PASSWORD)
        self.assertContains(self.client.get(reverse("core:about")), "Değişiklikleri gör ve onayla")
        self.client.post(reverse("accounts:reconsent"), {"aydinlatma": "on"})  # eksik onay
        self.assertTrue(services.outdated_consents(user))
        self.client.post(reverse("accounts:reconsent"), {"aydinlatma": "on", "kullanim": "on"})
        self.assertEqual(services.outdated_consents(user), [])


class TokenPrivacyTests(TestCase):
    def test_verify_token_does_not_carry_email(self):
        import base64

        user, _, _ = make_team("gizli@ornek.test")
        token = services.make_verify_token(user)
        payload = token.split(":")[0]
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        self.assertNotIn(b"gizli", decoded)
        self.assertEqual(services.read_verify_token(token), user)
