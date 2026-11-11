"""Validated, source-bound estimated football market-value observations.

No Transfermarkt scraping, no HTTP access, no implied permission to reuse
provider data. The caller must establish lawful rights to reuse the value.
This structure is groundwork for a future source/evidence-linked dossier fact.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit
import re

_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,2})?\Z")

_KINDS = {"squad_total", "player_estimate"}
_CURRENCIES = {"EUR", "GBP", "USD"}
_RIGHTS = {"licensed", "permission_granted"}


def _source_url(url):
    if not isinstance(url, str):
        raise ValueError("A source HTTPS URL is required.")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid source URL.") from None
    if (
        parsed.scheme != "https" or not hostname or port is not None
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or not hostname.isascii()
        or "." not in hostname or len(hostname) > 253
        or hostname.endswith((".local", ".localhost", ".internal"))
        or not all(_HOST_LABEL.fullmatch(label) for label in hostname.lower().split("."))
        or hostname.rsplit(".", 1)[-1].isdigit()
    ):
        raise ValueError("Only a public HTTPS source URL without credentials is allowed.")
    return urlunsplit(("https", hostname.lower(), parsed.path or "/", "", ""))


def normalize_market_value(*, amount, currency, value_date, retrieved_at,
                           source_url, metric="squad_total", rights_basis=None):
    """Return JSON-serializable metadata for a sourced *estimate*.

    A squad_total is an estimated sum of player values, NEVER a club
    enterprise value, transfer fee, annual revenue or official accounting.
    'rights_basis' is caller-supplied provenance, not independently verified
    by this helper. Never use it to authorize scraping.
    """
    if rights_basis not in _RIGHTS:
        raise ValueError("Permission or license must be confirmed before use.")
    if metric not in _KINDS:
        raise ValueError("Unsupported market value metric.")
    if currency not in _CURRENCIES:
        raise ValueError("Explicit supported ISO currency required; do not convert implicitly.")
    if isinstance(amount, bool) or not isinstance(amount, (int, str, Decimal)):
        raise ValueError("Use an exact decimal or integer amount, never float.")
    if isinstance(amount, int):
        amount = str(amount)
    elif isinstance(amount, Decimal):
        if not amount.is_finite():
            raise ValueError("Finite decimal amount required.")
        amount = format(amount, "f")
    if not _AMOUNT.fullmatch(amount):
        raise ValueError("Use a positive ungrouped numeric amount, no abbreviated millions.")
    try:
        number = Decimal(amount)
    except InvalidOperation:
        raise ValueError("Invalid market value amount.") from None
    if number <= 0:
        raise ValueError("Unknown values must remain absent, never be recorded as zero.")

    if not isinstance(value_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value_date):
        raise ValueError("Value date must be YYYY-MM-DD.")
    try:
        effective_date = date.fromisoformat(value_date)
    except ValueError:
        raise ValueError("Invalid value date.") from None
    if not isinstance(retrieved_at, datetime) or (
        retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None
    ):
        raise ValueError("Retrieval time must be timezone-aware.")
    if effective_date > retrieved_at.date():
        raise ValueError("Market-value date cannot be after the retrieval date.")
    return {
        "metric": metric,
        "amount": format(number, ".2f"),
        "currency": currency,
        "value_date": effective_date.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "source_url": _source_url(source_url),
        "rights_basis": rights_basis,
        "verification_state": "unverified",
    }
