from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testutils import (
    PASSWORD, add_member, clear_cache, make_sponsor, make_team, make_user, pdf_with,
)
from apps.matching.models import Agreement, SupportRequest
from apps.projects.models import Project, TeamInvite, TeamMembership


class MembershipTests(TestCase):
    def setUp(self):
        clear_cache()
        self.captain, self.team, self.project = make_team("kaptan@takim.test")
        self.c = self.client_class()
        self.c.login(email="kaptan@takim.test", password=PASSWORD)

    def _invite(self, email):
        self.c.post(reverse("projects:members"), {"invite": "1", "email": email})
        link = next(line for line in mail.outbox[-1].body.splitlines() if "/projeler/davet/" in line)
        return link[link.index("/projeler/"):].strip()

    def test_invite_and_accept(self):
        path = self._invite("uye@takim.test")
        invite = TeamInvite.objects.get()
        self.assertNotIn(path.rsplit("/", 2)[-2], invite.token_hash)  # belirteç açık saklanmaz
        make_user("uye@takim.test", "takim")
        member = self.client_class()
        member.login(email="uye@takim.test", password=PASSWORD)
        member.post(path)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user__email="uye@takim.test").exists())
        self.assertEqual(self.team.memberships.count(), 1)
        # Üye takım panelini görür, projeyi düzenleyebilir
        self.assertEqual(member.get(reverse("core:dashboard")).status_code, 200)
        self.assertEqual(member.get(reverse("projects:edit", args=[self.project.slug])).status_code, 200)

    def test_invite_requires_matching_email(self):
        path = self._invite("dogru@takim.test")
        make_user("baska@takim.test", "takim")
        other = self.client_class()
        other.login(email="baska@takim.test", password=PASSWORD)
        response = other.post(path)
        self.assertContains(response, "adresine gönderildi")
        self.assertFalse(TeamMembership.objects.exists())

    def test_sponsor_cannot_join_team(self):
        path = self._invite("firma@firma.test")
        make_sponsor("firma@firma.test")
        c = self.client_class()
        c.login(email="firma@firma.test", password=PASSWORD)
        self.assertContains(c.post(path), "destekçi hesabıyla")
        self.assertFalse(TeamMembership.objects.exists())

    def test_member_cannot_do_captain_things(self):
        member = add_member(self.team, "uye@takim.test")
        _, sponsor = make_sponsor("destek@firma.test")
        req = SupportRequest.objects.create(project=self.project, sponsor=sponsor, initiated_by="destekci",
                                            kind="malzeme", note="x", status="kabul")
        Agreement.objects.create(request=req, team_name="T", sponsor_name="S", project_title="P",
                                 support_summary="a", team_obligations="b", sponsor_obligations="c",
                                 payment_channel="d", start_date="2026-11-01", end_date="2027-01-01",
                                 template_version="1.0", body="metin", body_hash="h")
        c = self.client_class()
        c.login(email="uye@takim.test", password=PASSWORD)
        # Üye yazışmayı görebilir ve mesaj yazabilir
        self.assertEqual(c.get(req.get_absolute_url()).status_code, 200)
        c.post(reverse("matching:message", args=[req.pk]), {"body": "Merhaba"})
        self.assertEqual(req.messages.get().sender, member)
        # ama sözleşmeyi onaylayamaz, takım profilini düzenleyemez, üye çıkaramaz
        c.post(reverse("matching:agreement_approve", args=[req.pk]), {"password": PASSWORD, "body_hash": "h"})
        self.assertIsNone(Agreement.objects.get().team_approved_at)
        self.assertRedirects(c.get(reverse("projects:team_edit")), reverse("projects:members"))
        self.assertEqual(c.post(reverse("projects:status", args=[self.project.slug]), {"status": "arsiv"}).status_code, 403)

    def test_transfer_captaincy(self):
        member = add_member(self.team, "uye@takim.test")
        membership = member.team_membership
        self.c.post(reverse("projects:members"), {"transfer": "1", "member": membership.pk, "password": PASSWORD})
        self.team.refresh_from_db()
        self.assertEqual(self.team.owner, member)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.captain).exists())

    def test_captain_with_members_cannot_delete_account(self):
        add_member(self.team, "uye@takim.test")
        response = self.c.post(reverse("accounts:delete"), {"password": PASSWORD, "confirm": "SİL"})
        self.assertContains(response, "kaptanlığı bir üyeye devret")
        self.captain.refresh_from_db()
        self.assertTrue(self.captain.is_active)

    def test_remove_and_leave(self):
        m1 = add_member(self.team, "bir@takim.test")
        add_member(self.team, "iki@takim.test")
        self.c.post(reverse("projects:member_remove", args=[m1.team_membership.pk]))
        self.assertFalse(TeamMembership.objects.filter(user=m1).exists())
        c = self.client_class()
        c.login(email="iki@takim.test", password=PASSWORD)
        c.post(reverse("projects:leave"))
        self.assertFalse(self.team.memberships.exists())

    def test_other_team_cannot_cancel_invites(self):
        self._invite("uye@takim.test")
        invite = TeamInvite.objects.get()
        make_team("yabanci@diger.test")
        c = self.client_class()
        c.login(email="yabanci@diger.test", password=PASSWORD)
        self.assertEqual(c.post(reverse("projects:invite_cancel", args=[invite.pk])).status_code, 404)
        self.assertTrue(TeamInvite.objects.exists())


@override_settings(PRIVATE_MEDIA_ROOT="/tmp/claude-0/-home-claude/5b90493d-3686-504e-83d1-50e94de3b448/scratchpad/test_private")
class DossierTests(TestCase):
    def setUp(self):
        clear_cache()
        self.captain, self.team, self.project = make_team("kaptan@takim.test")
        self.c = self.client_class()
        self.c.login(email="kaptan@takim.test", password=PASSWORD)

    def _upload(self, data, name="dosya.pdf"):
        return self.c.post(reverse("projects:dossier_upload", args=[self.project.slug]),
                           {"dossier": SimpleUploadedFile(name, data, content_type="application/pdf")}, follow=True)

    def test_valid_pdf_is_stored_privately(self):
        self._upload(pdf_with())
        self.project.refresh_from_db()
        self.assertTrue(self.project.dossier.name.startswith("dosyalar/"))
        self.assertTrue(self.project.dossier.name.endswith(".pdf"))
        self.assertNotIn("dosya", self.project.dossier.name.split("/")[-1])  # rastgele ad

    def test_active_content_is_rejected(self):
        cases = [
            pdf_with(b"5 0 obj << /S /JavaScript /JS (app.alert(1)) >> endobj"),
            pdf_with(b"5 0 obj << /S /J#61vaScript >> endobj"),           # ad kaçışıyla gizlenmiş
            pdf_with(compressed=b"<< /S /JavaScript /JS (app.alert(1)) >>"),  # sıkıştırılmış akışta
            pdf_with(b"5 0 obj << /Type /EmbeddedFile >> endobj"),
            pdf_with(b"5 0 obj << /S /Launch /F (calc.exe) >> endobj"),
            pdf_with(b"trailer << /Encrypt 9 0 R >>"),
            b"<html><script>alert(1)</script></html>",
        ]
        for data in cases:
            response = self._upload(data)
            self.project.refresh_from_db()
            self.assertFalse(self.project.dossier, data[:40])
            self.assertEqual(response.status_code, 200)

    def test_non_pdf_extension_rejected(self):
        self._upload(pdf_with(), name="dosya.exe")
        self.project.refresh_from_db()
        self.assertFalse(self.project.dossier)

    def test_download_permissions(self):
        self._upload(pdf_with())
        url = reverse("projects:dossier", args=[self.project.slug])
        anonymous = self.client_class().get(url)
        self.assertEqual(anonymous.status_code, 302)
        make_team("baska@diger.test")
        other_team = self.client_class()
        other_team.login(email="baska@diger.test", password=PASSWORD)
        self.assertEqual(other_team.get(url).status_code, 403)
        make_sponsor("destek@firma.test")
        sponsor = self.client_class()
        sponsor.login(email="destek@firma.test", password=PASSWORD)
        response = sponsor.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertEqual(b"".join(response.streaming_content)[:5], b"%PDF-")


class TurkishSearchTests(TestCase):
    def test_search_handles_turkish_letters_and_suffixes(self):
        _, team, project = make_team("ara@takim.test")
        project.competition_detail = "TÜBİTAK 2209-A"
        project.save()
        url = reverse("projects:list")
        for q in ("tübitak", "TÜBİTAK", "tubitak", "motorlar", "insansız kara", "İKA"):
            self.assertContains(self.client.get(url, {"q": q}), project.title, msg_prefix=q)
        self.assertNotContains(self.client.get(url, {"q": "elektromotor"}), project.title)

    def test_sponsor_search(self):
        make_sponsor("pcb@firma.test", offerings="PCB baskı, lehimleme")
        self.assertContains(self.client.get(reverse("sponsors:list"), {"q": "baskı"}), "Firma pcb@firma.test")
        self.assertContains(self.client.get(reverse("sponsors:list"), {"q": "BASKI"}), "Firma pcb@firma.test")

    def test_expired_projects_are_hidden(self):
        from datetime import timedelta

        from django.utils import timezone

        _, _, project = make_team("eski@takim.test")
        Project.objects.filter(pk=project.pk).update(deadline=timezone.localdate() - timedelta(days=1))
        self.assertNotContains(self.client.get(reverse("projects:list")), project.title)
