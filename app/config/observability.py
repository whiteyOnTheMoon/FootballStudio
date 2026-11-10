"""Minimal structured HTTP error telemetry without personal information."""
import logging
import secrets

logger = logging.getLogger("footballstudio.http")


class SafeRequestLoggingMiddleware:
    """Attach a random correlation ID; log only non-sensitive error metadata.

    The request ID is always generated here (never trusted from an inbound
    header). Deliberately omit path, query string, identity, IP, body, headers,
    exception messages and tracebacks.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = secrets.token_hex(8)
        response = self.get_response(request)
        response["X-Request-ID"] = request_id

        if 400 <= response.status_code <= 599:
            method = request.method if request.method in {
                "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
            } else None
            logger.log(
                logging.ERROR if response.status_code >= 500 else logging.WARNING,
                "HTTP error",  # Never emitted by SafeJsonFormatter.
                extra={
                    "event": "http_error",
                    "status_code": response.status_code,
                    "http_method": method,
                    "request_id": request_id,
                },
            )
        return response
