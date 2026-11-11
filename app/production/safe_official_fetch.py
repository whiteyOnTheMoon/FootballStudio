"""HTTPS-only transport for explicitly confirmed, public official-site research.

No generic URL proxy. Always resolve and check EVERY address, then pin the
socket to an approved IP while validating TLS against the original hostname.
Redirects are NOT followed. Never use this for Transfermarkt or other sites
whose terms prohibit automated access.
"""
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit

from .official_site_links import _homepage


_TIMEOUT_SECONDS = 5
_MAX_HTML_BYTES = 300_000
_MAX_ROBOTS_BYTES = 512 * 1024  # RFC 9309 parsing minimum: 500 KiB
_USER_AGENT = "FootballStudioResearchBot/0.1 (+https://github.com/whiteyOnTheMoon/FootballStudio)"


class WebsiteFetchError(Exception):
    """Non-sensitive failure code. Do not expose DNS, TLS or upstream details."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _checked_url(url):
    """Canonical public DNS hostname, no credentials, port, query or controls."""
    if not isinstance(url, str) or not url.startswith("https://"):
        raise WebsiteFetchError("unsafe_url")
    if any(ord(char) < 33 or char == "\\" for char in url):
        raise WebsiteFetchError("unsafe_url")
    try:
        normalized, host = _homepage(url)
        path = urlsplit(normalized).path or "/"
    except ValueError:
        raise WebsiteFetchError("unsafe_url") from None
    # No hidden CRLF or host-traversal directives may reach an HTTP request.
    if (
        len(url) > 750 or not path.isascii()
        or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)", path, re.I)
    ):
        raise WebsiteFetchError("unsafe_url")
    return normalized, host


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS with a vetted IP, but Host/SNI/certificate tied to DNS hostname."""

    def __init__(self, host, address, *, timeout, context):
        super().__init__(host, port=443, timeout=timeout, context=context)
        self._approved_ip = address

    def connect(self):
        # No DNS lookup occurs here: the hostname is only used for TLS/SNI.
        raw_socket = socket.create_connection(
            (self._approved_ip, 443), timeout=self.timeout,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _approved_ip(host):
    try:
        records = socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP,
        )
    except (OSError, socket.gaierror):
        raise WebsiteFetchError("dns_error") from None
    if not records:
        raise WebsiteFetchError("dns_error")
    addresses = []
    for record in records:
        try:
            ip = ipaddress.ip_address(record[4][0])
        except (ValueError, IndexError, TypeError):
            raise WebsiteFetchError("unsafe_address") from None
        # Reject mixed public/private DNS, loopback, multicast, reserved,
        # cloud metadata ranges, IP-mapped IPv6 and all non-global IPs.
        if not ip.is_global or getattr(ip, "ipv4_mapped", None) is not None:
            raise WebsiteFetchError("unsafe_address")
        addresses.append(str(ip))
    return sorted(set(addresses))[0]


def _download_public_https(url, *, kind):
    """One capped no-redirect HTTPS GET; return UTF-8 decoded text.

    This transport does not decide whether a domain is official, permitted
    to crawl or appropriate for a particular club. The caller must gate it.
    """
    if kind not in ("robots", "html"):
        raise ValueError("Unsupported content kind.")
    canonical, host = _checked_url(url)
    limit = _MAX_ROBOTS_BYTES if kind == "robots" else _MAX_HTML_BYTES
    ip = _approved_ip(host)
    connection = _PinnedHTTPSConnection(
        host, ip, timeout=_TIMEOUT_SECONDS, context=ssl.create_default_context(),
    )
    try:
        path = urlsplit(canonical).path or "/"
        connection.request("GET", path, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/plain" if kind == "robots" else "text/html",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise WebsiteFetchError("redirect_blocked")
        if response.status in (401, 403, 429):
            raise WebsiteFetchError("access_restricted")
        if response.status != 200:
            raise WebsiteFetchError("http_error")

        content_type = (response.getheader("Content-Type") or "").lower().split(";", 1)[0].strip()
        if content_type != ("text/plain" if kind == "robots" else "text/html"):
            raise WebsiteFetchError("wrong_content_type")
        if (response.getheader("Content-Encoding") or "identity").lower() != "identity":
            raise WebsiteFetchError("encoded_response")
        length = response.getheader("Content-Length")
        if length is not None:
            try:
                declared_length = int(length)
            except ValueError:
                raise WebsiteFetchError("invalid_content_length") from None
            if declared_length < 0 or declared_length > limit:
                raise WebsiteFetchError("response_too_large")

        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise WebsiteFetchError("response_too_large")
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeError:
            raise WebsiteFetchError("invalid_encoding") from None
    except WebsiteFetchError:
        raise
    except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException):
        raise WebsiteFetchError("network_error") from None
    finally:
        connection.close()
