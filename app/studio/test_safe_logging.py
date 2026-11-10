"""Privacy regression tests for the error-logging and readiness boundary."""
import io
import json
import logging
from unittest.mock import patch

from django.http import HttpResponse, HttpResponseServerError
from django.test import RequestFactory, SimpleTestCase

from app.config.observability import SafeRequestLoggingMiddleware
from app.config.safe_logging import SafeJsonFormatter


class SafeJsonFormatterTests(SimpleTestCase):
    def test_drops_arbitrary_message_args_and_exception_details(self):
        record = logging.LogRecord(
            "django.security.DisallowedHost",
            logging.ERROR,
            "/private/server.py",
            1,
            "invalid host attacker.invalid with password=VERY-SECRET",
            (),
            None,
        )
        record.request = {"cookie": "very-private"}
        record.status_code = 500
        record.http_method = "POST"
        record.request_id = "abcdef0123456789"
        record.exc_text = "sensitive-exception"
        obj = json.loads(SafeJsonFormatter().format(record))
        self.assertEqual(obj["event"], "framework_error")
        self.assertEqual(obj["status_code"], 500)
        self.assertEqual(obj["request_id"], "abcdef0123456789")
        for secret in ("attacker.invalid", "VERY-SECRET", "very-private",
                       "sensitive-exception", "/private/server.py"):
            self.assertNotIn(secret, json.dumps(obj))

    def test_unknown_metadata_is_ignored(self):
        record = logging.LogRecord(
            "custom", logging.ERROR, "", 0, "raw-token=SECRET", (), None
        )
        record.event = "email=someone@example.com"
        record.http_method = "POST /user?api_key=SECRET"
        record.request_id = "attacker-supplied"
        record.status_code = "500;token"
        obj = json.loads(SafeJsonFormatter().format(record))
        self.assertEqual(set(obj), {"timestamp", "level", "event"})
        self.assertEqual(obj["event"], "framework_error")


class RequestLoggingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(SafeJsonFormatter())

    def _run_with_safe_handler(self, request, response):
        logger = logging.getLogger("footballstudio.http")
        with (
            patch.object(logger, "handlers", [self.handler]),
            patch.object(logger, "propagate", False),
            patch.object(logger, "level", logging.WARNING),
        ):
            result = SafeRequestLoggingMiddleware(lambda _: response)(request)
        return result

    def test_500_json_contains_status_method_and_random_id_only(self):
        request = self.factory.post(
            "/jobs/api/?token=SECRET-QUERY",
            data={"password": "SECRET-FORM", "email": "private@example.com"},
            HTTP_COOKIE="sessionid=SECRET-COOKIE",
            HTTP_X_REQUEST_ID="client-supplied-not-trusted",
            REMOTE_ADDR="192.0.2.5",
        )
        response = self._run_with_safe_handler(
            request, HttpResponseServerError("sensitive internal details")
        )
        entry = json.loads(self.stream.getvalue().strip())
        self.assertEqual(entry["event"], "http_error")
        self.assertEqual(entry["status_code"], 500)
        self.assertEqual(entry["method"], "POST")
        self.assertEqual(entry["request_id"], response["X-Request-ID"])
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{16}$")
        self.assertEqual(
            set(entry), {"timestamp", "level", "event",
                         "status_code", "method", "request_id"}
        )
        for secret in ("SECRET-QUERY", "SECRET-FORM", "SECRET-COOKIE",
                       "private@example.com", "192.0.2.5",
                       "client-supplied-not-trusted", "sensitive internal details"):
            self.assertNotIn(secret, self.stream.getvalue())

    def test_200_is_not_logged_but_has_correlation_id(self):
        request = self.factory.get("/healthz/")
        response = self._run_with_safe_handler(
            request, HttpResponse("ok")
        )
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{16}$")
        self.assertEqual(self.stream.getvalue(), "")

    def test_404_logs_only_warning_without_query_path(self):
        request = self.factory.get("/accounts/login/?email=private@example.com")
        response = self._run_with_safe_handler(
            request, HttpResponse("not found", status=404)
        )
        entry = json.loads(self.stream.getvalue().strip())
        self.assertEqual(entry["status_code"], 404)
        self.assertEqual(entry["level"], "WARNING")
        self.assertNotIn("private@example.com", self.stream.getvalue())

    def test_each_request_gets_new_id_even_with_same_header(self):
        request1 = self.factory.get("/", HTTP_X_REQUEST_ID="duplicate")
        request2 = self.factory.get("/", HTTP_X_REQUEST_ID="duplicate")
        r1 = self._run_with_safe_handler(request1, HttpResponse("ok"))
        r2 = self._run_with_safe_handler(request2, HttpResponse("ok"))
        self.assertNotEqual(r1["X-Request-ID"], r2["X-Request-ID"])
