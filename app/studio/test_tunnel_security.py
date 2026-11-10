"""Regression checks for the Cloudflare → Django HTTPS boundary."""
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=["studio2.ap-pixels.com"],
    SECURE_SSL_REDIRECT=True,
    SECURE_REDIRECT_EXEMPT=[r"^healthz/$"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    CSRF_TRUSTED_ORIGINS=["https://studio2.ap-pixels.com"],
)
class CloudflareTunnelSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SecurityMiddleware(
            lambda request: HttpResponse("private origin", content_type="text/plain")
        )

    def test_plain_http_redirects_to_https(self):
        request = self.factory.get(
            "/accounts/login/", HTTP_HOST="studio2.ap-pixels.com"
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"], "https://studio2.ap-pixels.com/accounts/login/"
        )

    def test_trusted_proxy_https_header_prevents_redirect_loop(self):
        request = self.factory.get(
            "/accounts/login/",
            HTTP_HOST="studio2.ap-pixels.com",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertTrue(request.is_secure())
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_healthcheck_stays_usable_by_private_http_container(self):
        request = self.factory.get(
            "/healthz/", HTTP_HOST="127.0.0.1"
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_client_reported_http_does_not_bypass_https_enforcement(self):
        request = self.factory.get(
            "/accounts/login/",
            HTTP_HOST="studio2.ap-pixels.com",
            HTTP_X_FORWARDED_PROTO="http",
        )
        self.assertFalse(request.is_secure())
        self.assertEqual(self.middleware(request).status_code, 301)
