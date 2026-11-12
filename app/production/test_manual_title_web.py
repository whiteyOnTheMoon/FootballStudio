"""FS-015b manual title update: ownership, stale, CSRF and no paid calls."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import ProductionJob


class ManualTitleBrowserTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="title-owner@example.org", password="Test-Password-123!"
        )
        self.other = User.objects.create_user(
            email="title-other@example.org", password="Test-Password-123!"
        )
        country = Country.objects.create(code="GB", name="Britain")
        league = League.objects.create(
            country=country, name="Demo League", tier=1,
            provider="manual", provider_id="",
        )
        club = Club.objects.create(
            league=league, name="Demo FC", provider="manual",
            provider_id="", is_manual=True,
        )
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="First Demo Title",
            country_code="GB", league_name="Demo League", club_name="Demo FC",
        )
        self.url = reverse("edit-manual-title", args=[self.job.pk])
        self.client.force_login(self.owner)

    def test_owner_can_edit_with_revision_and_no_network(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Demo Title")
        revision = self.job.updated_at.isoformat()
        with patch("urllib.request.urlopen") as network:
            changed = self.client.post(self.url, {
                "title": "  New   Demo   Title  ", "revision": revision,
            })
        self.assertEqual(changed.status_code, 302)
        network.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "New Demo Title")

    def test_stale_submission_does_not_overwrite(self):
        old = self.job.updated_at.isoformat()
        self.assertEqual(self.client.post(self.url, {
            "title": "Updated title", "revision": old,
        }).status_code, 302)
        response = self.client.post(self.url, {
            "title": "Stale title", "revision": old,
        })
        self.assertEqual(response.status_code, 409)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "Updated title")

    def test_invalid_title_rejected(self):
        for title in ("", "X", "<script>alert(1)</script>", "a\\nb"):
            with self.subTest(title=title):
                response = self.client.post(self.url, {
                    "title": title, "revision": self.job.updated_at.isoformat(),
                })
                self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "First Demo Title")

    def test_other_user_cannot_view_or_update(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {
            "title": "Forged title", "revision": self.job.updated_at.isoformat(),
        }).status_code, 404)

    def test_login_and_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {
            "title": "Another title", "revision": self.job.updated_at.isoformat(),
        }).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {
            "title": "Another title", "revision": self.job.updated_at.isoformat(),
        }).status_code, 302)

    def test_film_job_cannot_be_changed(self):
        self.job.kind = ProductionJob.Kind.FILM
        self.job.save(update_fields=["kind"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {
            "title": "Blocked title", "revision": self.job.updated_at.isoformat(),
        }).status_code, 404)
