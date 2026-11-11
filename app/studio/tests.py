"""HTTP and database checks for the protected studio."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{16}$")

    def test_database_unavailable_is_503_without_sensitive_details(self):
        from unittest.mock import patch
        from django.db.utils import DatabaseError

        class BrokenConnection:
            def cursor(self):
                raise DatabaseError("sensitive-database-host-or-password")

        with patch("app.studio.views.connections", {"default": BrokenConnection()}):
            response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"unavailable")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn(b"sensitive-database", response.content)


@override_settings(
    ALLOWED_HOSTS=["studio2.ap-pixels.com"],
    SECURE_SSL_REDIRECT=True,
    SECURE_REDIRECT_EXEMPT=[r"^healthz/$"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    CSRF_TRUSTED_ORIGINS=["https://studio2.ap-pixels.com"],
)
class ProductionTunnelReadinessTests(TestCase):
    def test_healthcheck_with_explicit_allowed_production_host_returns_200(self):
        response = self.client.get(
            reverse("healthz"),
            HTTP_HOST="studio2.ap-pixels.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_regular_plain_http_request_redirects_to_public_https(self):
        response = self.client.get(
            reverse("login"),
            HTTP_HOST="studio2.ap-pixels.com",
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"], "https://studio2.ap-pixels.com/accounts/login/"
        )
