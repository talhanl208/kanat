from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.testutils import PASSWORD, clear_cache, make_sponsor, make_team
from apps.matching.models import SupportRequest
from apps.notifications.models import Notification
from apps.notifications.services import notify, unsubscribe_token


class NotificationFlowTests(TestCase):
    def setUp(self):
        clear_cache()
        self.team_user, self.team, self.project = make_team("takim@takim.test")
        self.sp_user, self.sponsor = make_sponsor("destek@firma.test")
        self.s = self.client_class()
        self.s.login(email="destek@firma.test", password=PASSWORD)
        self.t = self.client_class()
        self.t.login(email="takim@takim.test", password=PASSWORD)

    def _offer(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.s.post(reverse("matching:offer", args=[self.project.slug]),
                        {"kind": "malzeme", "amount": "5000", "note": "Destek olalım."})
        return SupportRequest.objects.get()

    def test_offer_notifies_team_in_app_and_by_email(self):
        req = self._offer()
        n = Notification.objects.get(user=self.team_user)
        self.assertEqual(n.kind, Notification.Kind.REQUEST)
        self.assertEqual(n.url, req.get_absolute_url())
        self.assertIsNotNone(n.emailed_at)
        message = mail.outbox[-1]
        self.assertEqual(message.to, ["takim@takim.test"])
        self.assertIn("List-Unsubscribe", message.extra_headers)
        self.assertContains(self.t.get(reverse("core:about")), "1 okunmamış")

    def test_message_emails_are_throttled(self):
        req = self._offer()
        before = len(mail.outbox)
        for text in ("bir", "iki", "üç"):
            with self.captureOnCommitCallbacks(execute=True):
                self.s.post(reverse("matching:message", args=[req.pk]), {"body": text})
        self.assertEqual(Notification.objects.filter(user=self.team_user, kind="mesaj").count(), 3)
        self.assertEqual(len(mail.outbox) - before, 1)

    def test_opening_request_marks_its_notifications_read(self):
        req = self._offer()
        self.t.get(req.get_absolute_url())
        self.assertFalse(Notification.objects.filter(user=self.team_user, read_at__isnull=True).exists())

    def test_open_only_own_notification(self):
        n = notify([self.team_user], "sistem", "Merhaba", url="/panel/", email=False)[0]
        self.assertEqual(self.s.get(reverse("notifications:open", args=[n.pk])).status_code, 404)
        self.assertRedirects(self.t.get(reverse("notifications:open", args=[n.pk])), "/panel/",
                             fetch_redirect_response=False)

    def test_external_urls_are_rejected(self):
        with self.assertRaises(ValueError):
            notify([self.team_user], "sistem", "Kötü", url="https://kotu.example/")

    def test_unsubscribe_one_click(self):
        token = unsubscribe_token(self.team_user)
        self.assertEqual(self.client.get(reverse("notifications:unsubscribe", args=[token])).status_code, 200)
        self.client.post(reverse("notifications:unsubscribe", args=[token]))  # CSRF belirteci yok (RFC 8058)
        self.team_user.refresh_from_db()
        self.assertFalse(self.team_user.email_notifications)
        bad = self.client.post(reverse("notifications:unsubscribe", args=[token + "x"]))
        self.assertEqual(bad.status_code, 400)

    def test_no_email_when_disabled_or_unverified(self):
        self.team_user.email_notifications = False
        self.team_user.save()
        before = len(mail.outbox)
        self._offer()
        self.assertEqual(len(mail.outbox), before)
        self.assertTrue(Notification.objects.filter(user=self.team_user).exists())

    def test_mark_all_read(self):
        notify([self.team_user], "sistem", "A", email=False)
        notify([self.team_user], "sistem", "B", email=False)
        self.t.post(reverse("notifications:mark_all_read"))
        self.assertFalse(self.team_user.notifications.filter(read_at__isnull=True).exists())


class NotifyUrlTests(TestCase):
    def test_protocol_relative_urls_rejected(self):
        user, _, _ = make_team("x@takim.test")
        for bad in ("//kotu.example/", "/\\kotu.example"):
            with self.assertRaises(ValueError):
                notify([user], "sistem", "Kötü", url=bad)
