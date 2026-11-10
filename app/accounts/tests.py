"""Email login, CSRF, session and brute-force tests for FS-009a/b."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse


class EmailLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.email = "viewer@example.com"
        cls.password = "Secure-sample-passphrase-2026!"
        cls.user = get_user_model().objects.create_user(email=cls.email, password=cls.password)

    def test_email_is_unique_identity(self):
        self.assertEqual(get_user_model().USERNAME_FIELD, "email")
        self.assertIsNone(self.user.username)  # no username column; inherited attr is None
        with self.assertRaises(ValidationError):
            get_user_model().objects.create_user(
                email="VIEWER@EXAMPLE.COM", password="Different-passphrase-2026!"
            )

    def test_superuser_uses_email(self):
        user = get_user_model().objects.create_superuser(
            "Owner@Example.com", "Secure-admin-passphrase-2026!"
        )
        self.assertEqual(user.email, "owner@example.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_correct_email_login_allows_private_home(self):
        response = self.client.post(
            reverse("login"), {"username": "VIEWER@EXAMPLE.COM", "password": self.password}
        )
        self.assertRedirects(response, reverse("home"))
        self.assertContains(self.client.get(reverse("home")), self.email)

    def test_incorrect_password_does_not_authenticate(self):
        response = self.client.post(reverse("login"), {
            "username": self.email, "password": "not-the-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)

    def test_no_public_registration(self):
        self.assertEqual(self.client.get("/accounts/signup/").status_code, 404)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)

    def test_csrf_required_for_login(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("login"), {
            "username": self.email, "password": self.password,
        })
        self.assertEqual(response.status_code, 403)

    def test_repeated_failed_logins_are_limited(self):
        responses = [
            self.client.post(reverse("login"), {
                "username": self.email, "password": "wrong",
            }, REMOTE_ADDR="203.0.113.45").status_code
            for _ in range(settings.AXES_FAILURE_LIMIT)
        ]
        self.assertIn(settings.AXES_HTTP_RESPONSE_CODE, responses)
        locked = self.client.post(reverse("login"), {
            "username": self.email, "password": self.password,
        }, REMOTE_ADDR="203.0.113.45")
        self.assertEqual(locked.status_code, settings.AXES_HTTP_RESPONSE_CODE)

    def test_session_config(self):
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertEqual(settings.AXES_LOCKOUT_PARAMETERS[0], "ip_address")
