"""Foundational HTTP and database readiness tests for M1/#15/#17."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HomePageTests(SimpleTestCase):
    def test_home_responds_200(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FootballStudio")
        self.assertContains(response, "Land")
        self.assertContains(response, "Liga")
        self.assertContains(response, "Verein")


class HealthTests(TestCase):
    def test_ready_on_available_database(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
