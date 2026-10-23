from django.test import TestCase
from django.urls import reverse

from apps.core.testutils import PASSWORD, clear_cache, make_sponsor, make_team
from apps.projects.models import Project


class ProjectOwnershipTests(TestCase):
    def setUp(self):
        clear_cache()
        self.owner, self.team, self.project = make_team("sahip@ornek.test")
        make_team("baska@ornek.test")

    def test_other_team_cannot_edit(self):
        self.client.login(email="baska@ornek.test", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("projects:edit", args=[self.project.slug])).status_code, 404)
        response = self.client.post(reverse("projects:status", args=[self.project.slug]), {"status": "arsiv"})
        self.assertEqual(response.status_code, 404)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "aktif")

    def test_sponsor_cannot_use_team_pages(self):
        make_sponsor("d@ornek.test")
        self.client.login(email="d@ornek.test", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("projects:create")).status_code, 403)

    def test_archived_project_hidden_from_public(self):
        self.project.status = Project.Status.ARCHIVED
        self.project.save()
        self.assertEqual(self.client.get(self.project.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("projects:list")), self.project.title)

    def test_create_project_with_needs(self):
        self.client.login(email="sahip@ornek.test", password=PASSWORD)
        data = {
            "title": "Yeni İHA", "summary": "Kısa", "category": "iha", "competition": "teknofest",
            "competition_detail": "", "stage": "fikir", "deadline": "", "description": "Açıklama",
            "sponsor_benefits": "",
            "ihtiyac-TOTAL_FORMS": "1", "ihtiyac-INITIAL_FORMS": "0",
            "ihtiyac-MIN_NUM_FORMS": "1", "ihtiyac-MAX_NUM_FORMS": "20",
            "ihtiyac-0-kind": "malzeme", "ihtiyac-0-title": "Batarya", "ihtiyac-0-detail": "",
            "ihtiyac-0-estimated_cost": "5000", "ihtiyac-0-mentor_hours": "",
        }
        response = self.client.post(reverse("projects:create"), data)
        project = Project.objects.get(title="Yeni İHA")
        self.assertRedirects(response, project.get_absolute_url())
        self.assertEqual(project.team, self.team)
        self.assertEqual(project.slug, "yeni-iha")
        self.assertEqual(project.needs.count(), 1)

    def test_https_only_website(self):
        self.client.login(email="sahip@ornek.test", password=PASSWORD)
        response = self.client.post(reverse("projects:team_edit"), {
            "kind": "takim", "name": "T", "institution": "O", "city": "Konya", "member_count": 3,
            "about": "a", "website": "http://ornek.test",
        })
        self.assertEqual(response.status_code, 200)
        self.team.refresh_from_db()
        self.assertEqual(self.team.website, "")

    def test_minor_members_require_advisor_declaration(self):
        self.client.login(email="sahip@ornek.test", password=PASSWORD)
        response = self.client.post(reverse("projects:team_edit"), {
            "kind": "takim", "name": "T", "institution": "O", "city": "Konya", "member_count": 3,
            "about": "a", "has_minor_members": "on",
        })
        self.assertContains(response, "Reşit olmayan üyeler için bu beyan zorunludur.")
