"""HTTP and database checks for the protected studio."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=/", response.url)

    def test_authenticated_home_responds_200(self):
        user = get_user_model().objects.create_user(
            email="tester@example.com", password="ChangeMe-2026!"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "FootballStudio")
        self.assertContains(response, "Land")
        self.assertContains(response, "Liga")
        self.assertContains(response, "Verein")


class HealthTests(TestCase):
    def test_ready_on_available_database(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
