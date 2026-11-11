"""No-network checks for pinned HTTPS, DNS/redirect and response limits."""
import socket
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .safe_official_fetch import (
    WebsiteFetchError, _PinnedHTTPSConnection, _approved_ip,
    _checked_url, _download_public_https,
)


def address(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


class SafeOfficialTransportTests(SimpleTestCase):
    def test_pinned_connect_uses_public_ip_but_sni_original_domain(self):
        tls = MagicMock()
        raw_socket = MagicMock()
        with patch("app.production.safe_official_fetch.socket.create_connection",
                   return_value=raw_socket) as connector:
            conn = _PinnedHTTPSConnection(
                "club.example.org", "8.8.8.8", timeout=5, context=tls,
            )
            conn.connect()
            connector.assert_called_once_with(("8.8.8.8", 443), timeout=5)
            tls.wrap_socket.assert_called_once_with(
                raw_socket, server_hostname="club.example.org",
            )
            self.assertEqual(conn.sock, tls.wrap_socket.return_value)

    def test_failed_tls_handshake_closes_underlying_socket(self):
        tls = MagicMock()
        tls.wrap_socket.side_effect = OSError("TLS error, never surfaced")
        raw_socket = MagicMock()
        with patch("app.production.safe_official_fetch.socket.create_connection",
                   return_value=raw_socket):
            conn = _PinnedHTTPSConnection(
                "club.example.org", "8.8.8.8", timeout=5, context=tls,
            )
            with self.assertRaises(OSError):
                conn.connect()
        raw_socket.close.assert_called_once()

    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_dns_rejects_private_and_mixed_public_private_records(self, dns):
        for ips in (
            ["127.0.0.1"],
            ["10.0.0.6"],
            ["169.254.169.254"],
            ["172.17.0.1"],
            ["192.168.0.1"],
            ["100.64.0.2"],
            ["::1"],
            ["fc00::7"],
            ["8.8.8.8", "10.0.0.1"],
        ):
            with self.subTest(ips=ips):
                dns.return_value = [address(ip) for ip in ips]
                with self.assertRaises(WebsiteFetchError) as e:
                    _approved_ip("club.example.org")
                self.assertEqual(e.exception.code, "unsafe_address")
        dns.assert_called()

    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_dns_public_only_sorted_and_failure_safe(self, dns):
        dns.return_value = [address("9.9.9.9"), address("8.8.8.8")]
        self.assertEqual(_approved_ip("club.example.org"), "8.8.8.8")
        dns.side_effect = OSError("Hidden resolver diagnostics")
        with self.assertRaises(WebsiteFetchError) as e:
            _approved_ip("club.example.org")
        self.assertEqual(e.exception.code, "dns_error")
        self.assertNotIn("Hidden", str(e.exception))

    def test_url_checks_prevent_http_and_request_smuggling(self):
        for url in (
            "http://club.example.org/",
            "https://127.0.0.1/",
            "https://localhost/",
            "https://club.local/",
            "https://example.org.evil.local/",
            "https://user:secret@club.example.org/",
            "https://club.example.org:443/",
            "https://club.example.org/history?key=1",
            "https://club.example.org/history#team",
            "https://club.example.org/%0D%0AHeader",
            "https://club.example.org/path\\extra",
            " https://club.example.org/",
            "https://club.example.org/a\nb",
        ):
            with self.subTest(url=url):
                with self.assertRaises(WebsiteFetchError):
                    _checked_url(url)
        self.assertEqual(_checked_url("https://club.example.org/en/history")[1],
                         "club.example.org")

    def _response(self, *, status=200, content_type="text/html",
                  body=b"<h1>Club history</h1>", headers=None):
        res = MagicMock()
        res.status = status
        headers = headers or {}
        res.getheader.side_effect = lambda name: (
            content_type if name == "Content-Type" else headers.get(name)
        )
        res.read.side_effect = lambda limit: body[:limit]
        return res

    @patch("app.production.safe_official_fetch._PinnedHTTPSConnection")
    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_success_download_uses_checked_ip_and_original_hostname(self, dns, conn):
        dns.return_value = [address("8.8.8.8")]
        conn.return_value.getresponse.return_value = self._response()
        html = _download_public_https("https://club.example.org/history", kind="html")
        self.assertEqual(html, "<h1>Club history</h1>")
        self.assertEqual(conn.call_args.args[:2], ("club.example.org", "8.8.8.8"))
        self.assertEqual(conn.call_args.kwargs["timeout"], 5)
        req = conn.return_value.request.call_args
        self.assertEqual(req.args, ("GET", "/history"))
        self.assertIn("FootballStudioResearchBot", req.kwargs["headers"]["User-Agent"])
        self.assertEqual(req.kwargs["headers"]["Accept-Encoding"], "identity")
        conn.return_value.close.assert_called_once()

    @patch("app.production.safe_official_fetch._PinnedHTTPSConnection")
    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_redirect_403_429_and_other_non_200_are_not_followed(self, dns, conn):
        dns.return_value = [address("8.8.8.8")]
        for status, code in ((301, "redirect_blocked"), (302, "redirect_blocked"),
                             (403, "access_restricted"), (429, "access_restricted"),
                             (500, "http_error"), (404, "http_error")):
            with self.subTest(status=status):
                conn.return_value.getresponse.return_value = self._response(status=status)
                with self.assertRaises(WebsiteFetchError) as e:
                    _download_public_https("https://club.example.org/", kind="html")
                self.assertEqual(e.exception.code, code)
        self.assertEqual(conn.return_value.request.call_count, 6)

    @patch("app.production.safe_official_fetch._PinnedHTTPSConnection")
    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_rejects_wrong_content_encoded_and_excessive_responses(self, dns, conn):
        dns.return_value = [address("8.8.8.8")]
        failures = [
            (self._response(content_type="application/pdf"), "wrong_content_type"),
            (self._response(headers={"Content-Encoding": "gzip"}), "encoded_response"),
            (self._response(headers={"Content-Length": "300001"}), "response_too_large"),
            (self._response(headers={"Content-Length": "garbage"}), "invalid_content_length"),
            (self._response(body=b"a" * 300001), "response_too_large"),
            (self._response(body=b"\xff"), "invalid_encoding"),
        ]
        for response, code in failures:
            with self.subTest(code=code):
                conn.return_value.getresponse.return_value = response
                with self.assertRaises(WebsiteFetchError) as e:
                    _download_public_https("https://club.example.org/", kind="html")
                self.assertEqual(e.exception.code, code)

    @patch("app.production.safe_official_fetch._PinnedHTTPSConnection")
    @patch("app.production.safe_official_fetch.socket.getaddrinfo")
    def test_robots_plain_text_and_binary_media_blocked(self, dns, conn):
        dns.return_value = [address("8.8.8.8")]
        conn.return_value.getresponse.return_value = self._response(
            body=b"User-agent: *\nDisallow: /private",
            content_type="text/plain",
        )
        self.assertIn("Disallow", _download_public_https(
            "https://club.example.org/robots.txt", kind="robots",
        ))
        with self.assertRaises(ValueError):
            _download_public_https("https://club.example.org", kind="binary")
