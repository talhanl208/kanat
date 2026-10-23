import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.core.images import sanitize_image
from apps.core.models import DataRequest
from apps.core.testutils import clear_cache
from apps.core.utils import tr_normalize


class SecurityHeaderTests(TestCase):
    def test_csp_is_strict_with_nonce(self):
        response = self.client.get(reverse("core:home"))
        csp = response["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertNotIn("unsafe-inline", csp.split("script-src")[1].split(";")[0])
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'none'", csp)
        # Sayfadaki tek satır içi betik aynı nonce'u taşır
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertContains(response, f'nonce="{nonce}"')

    def test_other_headers(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("camera=()", response["Permissions-Policy"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_no_inline_style_attributes_in_pages(self):
        for name in ("core:home", "core:about", "projects:list", "rankings:leaderboard"):
            body = self.client.get(reverse(name)).content.decode()
            self.assertNotIn(' style="', body, name)

    def test_security_txt_and_robots(self):
        self.assertContains(self.client.get("/.well-known/security.txt"), "Contact: mailto:")
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /hesap/")


class LegalPagesTests(TestCase):
    def test_all_documents_render(self):
        for slug in ("aydinlatma", "kullanim", "acik-riza", "cerez", "sponsorluk-sozlesmesi"):
            self.assertEqual(self.client.get(reverse("core:legal", args=[slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:legal", args=["yok"])).status_code, 404)


class DataRequestTests(TestCase):
    def setUp(self):
        clear_cache()

    def test_kvkk_request_is_saved_with_30_day_deadline(self):
        response = self.client.post(reverse("core:data_request"), {
            "full_name": "Ayşe Yılmaz", "email": "ayse@ornek.test", "kind": "silme",
            "message": "Verilerimin silinmesini istiyorum.", "identity_ack": "on",
        })
        self.assertRedirects(response, reverse("core:home"))
        req = DataRequest.objects.get()
        self.assertEqual((req.due_date - req.created_at).days, 30)

    def test_rate_limited(self):
        data = {"full_name": "X", "email": "x@ornek.test", "kind": "bilgi", "message": "m", "identity_ack": "on"}
        codes = [self.client.post(reverse("core:data_request"), data).status_code for _ in range(7)]
        self.assertEqual(codes[-1], 429)


class ImageSanitizeTests(TestCase):
    def _png(self, size=(800, 600), exif=False):
        buf = io.BytesIO()
        img = Image.new("RGB", size, "teal")
        if exif:
            ex = Image.Exif()
            ex[0x010E] = "gizli konum"
            img.save(buf, format="JPEG", exif=ex)
            return SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")
        img.save(buf, format="PNG")
        return SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png")

    def test_reencodes_to_small_webp_without_metadata(self):
        result = sanitize_image(self._png(exif=True), "test")
        self.assertTrue(result.name.endswith(".webp"))
        out = Image.open(io.BytesIO(result.read()))
        self.assertEqual(out.format, "WEBP")
        self.assertLessEqual(max(out.size), 512)
        self.assertFalse(dict(out.getexif()))

    def test_rejects_non_image(self):
        fake = SimpleUploadedFile("x.png", b"<script>alert(1)</script>", content_type="image/png")
        with self.assertRaises(ValidationError):
            sanitize_image(fake, "test")

    @override_settings(MAX_IMAGE_UPLOAD_BYTES=10)
    def test_rejects_big_files(self):
        with self.assertRaises(ValidationError):
            sanitize_image(self._png(), "test")


class UtilsTests(TestCase):
    def test_turkish_normalization(self):
        self.assertEqual(tr_normalize("İnsansız Işık Çağrı Şöyle Üğ"), "insansiz isik cagri soyle ug")
