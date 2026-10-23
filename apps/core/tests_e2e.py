"""
Tarayıcı (uçtan uca) testleri — gerçek Chromium ile.

    pip install playwright && playwright install chromium
    KANAT_E2E=1 python manage.py test apps.core.tests_e2e

KANAT_E2E tanımlı değilse atlanır (normal test koşusunu yavaşlatmasın diye).
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from apps.accounts import totp
from apps.core.testutils import PASSWORD, make_sponsor, make_team

E2E = os.environ.get("KANAT_E2E") == "1"


@unittest.skipUnless(E2E, "KANAT_E2E=1 ile çalıştırın")
@override_settings(DEBUG=False, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"  # Playwright kendi olay döngüsünü açar
        super().setUpClass()
        from playwright.sync_api import sync_playwright

        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()
        self.problems = []
        self.page.on("console", lambda m: self.problems.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.problems.append(str(e)))

    def tearDown(self):
        self.context.close()

    def url(self, path):
        return self.live_server_url + path

    def login(self, email):
        self.page.goto(self.url("/hesap/giris/"))
        self.page.fill("#id_email", email)
        self.page.fill("#id_password", PASSWORD)
        self.page.click("form button[type=submit]")
        self.page.wait_for_load_state("networkidle")

    def test_home_has_no_csp_or_script_errors_and_theme_toggles(self):
        make_team("takim@takim.test")
        self.page.goto(self.url("/"))
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.problems, [])
        self.page.click("[data-tema-degistir]")
        # Tema, View Transitions API ile bir sonraki karede (en geç 400 ms'de) uygulanır.
        # Not: wait_for_function burada kullanılamaz; katı CSP 'unsafe-eval'e izin vermez (bu da bir test).
        self.page.wait_for_timeout(600)
        theme = self.page.evaluate("document.documentElement.getAttribute('data-theme')")
        self.assertIn(theme, ("dark", "light"))
        self.assertEqual(self.page.locator(".soz-noktalar button").count() > 1, True)

    def test_add_need_row_in_project_form(self):
        make_team("takim@takim.test")
        self.login("takim@takim.test")
        self.page.goto(self.url("/projeler/yeni/"))
        before = int(self.page.input_value("#id_ihtiyac-TOTAL_FORMS"))
        self.page.click("[data-satir-ekle]")
        self.assertEqual(int(self.page.input_value("#id_ihtiyac-TOTAL_FORMS")), before + 1)
        self.assertEqual(self.page.locator(f"#id_ihtiyac-{before}-title").count(), 1)
        self.assertEqual(self.problems, [])

    def test_mobile_has_no_horizontal_overflow(self):
        make_team("takim@takim.test")
        make_sponsor("destek@firma.test")
        mobile = self.browser.new_context(viewport={"width": 375, "height": 800})
        page = mobile.new_page()
        for path in ("/", "/projeler/", "/destekciler/", "/destekciler/cagrilar/", "/siralama/", "/hakkinda/"):
            page.goto(self.url(path))
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            self.assertLessEqual(overflow, 1, path)
        mobile.close()

    def test_two_factor_login_in_browser(self):
        user, _, _ = make_team("iki@takim.test")
        user.totp_secret = totp.new_secret()
        user.save()
        from apps.accounts.services import enable_totp

        enable_totp(user, totp.code_at(user.totp_secret, totp.current_counter()))
        user.refresh_from_db()
        self.login("iki@takim.test")
        self.assertIn("/hesap/giris/dogrula/", self.page.url)
        self.page.fill("input[name=code]", totp.code_at(user.totp_secret, user.totp_last_counter + 1))
        self.page.click("form button[type=submit]")
        self.page.wait_for_load_state("networkidle")
        self.assertIn("/panel/", self.page.url)
        self.assertEqual(self.problems, [])
