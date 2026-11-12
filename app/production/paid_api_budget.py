"""P0 FS-004c: provider-neutral USD guard for FUTURE paid adapters.

NO external API is called by this module. All paid calls are OFF by default.
Every future provider adapter MUST reserve first, and reconcile afterwards.
Concurrent workers/providers serialize on a pre-seeded singleton DB row.
The cap of USD 10/month is a product decision, not a guarantee about a
third-party bill. A new paid request must always use a fresh UUIDv4.
"""
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import os
import re
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PaidApiCharge, ProductionJob, SharedPaidApiBudgetLock


MICRO = Decimal("0.000001")
APPROVED_CAP_USD = Decimal("10.00")
WARNING_RATIO = Decimal("0.80")
PRICE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.:/@-]{0,119}$")
PROVIDER = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}$")
ENV_VAR = re.compile(r"^[A-Z][A-Z0-9_]{2,99}$")


class PaidApiBudgetError(ValueError):
    """Safe code, no provider secrets or response content."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class BudgetPermit:
    charge_id: int
    request_key: UUID
    reserved_usd: Decimal
    projected_month_total_usd: Decimal
    month_limit_usd: Decimal
    warning_80_percent: bool
    utc_month: str


def usd(value, *, allow_zero=False):
    """Decimal string only; never silently accept float/NaN or round down."""
    if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
        raise PaidApiBudgetError("invalid_cost")
    if isinstance(value, str) and (
        len(value) > 24 or not re.fullmatch(
            r"(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,12})?", value,
        )
    ):
        raise PaidApiBudgetError("invalid_cost")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
            raise PaidApiBudgetError("invalid_cost")
        return amount.quantize(MICRO, rounding=ROUND_CEILING)
    except (InvalidOperation, OverflowError):
        raise PaidApiBudgetError("invalid_cost") from None


def configured_cap():
    raw = getattr(settings, "API_MONTHLY_BUDGET_USD", "")
    if not raw:
        raise PaidApiBudgetError("budget_unconfigured")
    try:
        cap = usd(raw, allow_zero=True)
    except PaidApiBudgetError:
        raise PaidApiBudgetError("budget_unconfigured") from None
    if cap > APPROVED_CAP_USD:
        raise PaidApiBudgetError("budget_exceeds_approval")
    return cap


def utc_month(now=None):
    now = now or timezone.now()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise PaidApiBudgetError("invalid_timestamp")
    return now.astimezone(dt_timezone.utc).date().replace(day=1)


def approved_rate(rate_key):
    cards = getattr(settings, "PAID_API_RATE_CARDS", {})
    if (
        not isinstance(rate_key, str) or not PRICE_KEY.fullmatch(rate_key)
        or not isinstance(cards, dict)
        or not isinstance(cards.get(rate_key), dict)
    ):
        raise PaidApiBudgetError("price_unconfigured")
    card = cards[rate_key]
    provider, purpose = card.get("provider"), card.get("purpose")
    model, version = card.get("model"), card.get("price_version")
    unit_name, secret_name = card.get("unit_name"), card.get("credential_env")
    if (
        not isinstance(provider, str) or not PROVIDER.fullmatch(provider)
        or purpose not in PaidApiCharge.Purpose.values
        or not isinstance(model, str) or not 1 <= len(model) <= 100
        or not isinstance(version, str) or not 1 <= len(version) <= 60
        or not isinstance(unit_name, str) or not 1 <= len(unit_name) <= 30
        or not isinstance(secret_name, str) or not ENV_VAR.fullmatch(secret_name)
    ):
        raise PaidApiBudgetError("price_unconfigured")
    if not os.environ.get(secret_name):
        raise PaidApiBudgetError("provider_credentials_missing")
    try:
        price = usd(card.get("usd_per_unit_upper_bound"))
    except PaidApiBudgetError:
        raise PaidApiBudgetError("price_unconfigured") from None
    return card, price


def committed(row):
    if row.state == PaidApiCharge.State.RELEASED:
        return Decimal("0")
    if row.state == PaidApiCharge.State.SETTLED:
        return row.actual_usd
    return row.reserved_usd


def month_charges(period):
    total, uncertain = Decimal("0"), 0
    for row in PaidApiCharge.objects.filter(period_start=period).iterator(
        chunk_size=200,
    ):
        total += committed(row)
        if row.state in (PaidApiCharge.State.RESERVED, PaidApiCharge.State.UNCERTAIN):
            uncertain += 1
    return total, uncertain


def locked_gate():
    # The gate is created by migration 0010. Never create it on demand.
    gate = SharedPaidApiBudgetLock.objects.select_for_update().filter(pk=1).first()
    if gate is None:
        raise PaidApiBudgetError("budget_lock_missing")
    return gate


def reserve_paid_api_budget(*, owner_id, job_id, rate_key, max_units, request_key):
    """The one authorization point BEFORE a billable provider request.

    max_units is a conservative bound, not actual consumption. A rate card
    is operator-configured, with provider, purpose, model, price version and
    secret environment variable. Do not reuse UUIDs for retries or replays.
    """
    if not getattr(settings, "PAID_API_CALLS_ENABLED", False):
        raise PaidApiBudgetError("paid_calls_disabled")
    cap = configured_cap()
    if cap == 0:
        raise PaidApiBudgetError("budget_exhausted")
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(job_id) is not int or job_id <= 0
        or type(max_units) is not int or not 1 <= max_units <= 1_000_000
        or not isinstance(request_key, UUID) or request_key.version != 4
    ):
        raise PaidApiBudgetError("invalid_reservation")
    card, per_unit = approved_rate(rate_key)
    reservation = (per_unit * max_units).quantize(MICRO, rounding=ROUND_CEILING)
    month = utc_month()
    with transaction.atomic():
        locked_gate()
        if PaidApiCharge.objects.filter(request_key=request_key).exists():
            raise PaidApiBudgetError("already_reserved")
        job = ProductionJob.objects.filter(
            pk=job_id, owner_id=owner_id,
        ).first()
        if job is None:
            raise PaidApiBudgetError("not_authorized")
        used, _ = month_charges(month)
        projected = used + reservation
        if projected > cap:
            raise PaidApiBudgetError("budget_exhausted")
        charge = PaidApiCharge.objects.create(
            request_key=request_key, job=job, rate_key=rate_key,
            provider=card["provider"], purpose=card["purpose"],
            model_id=card["model"], price_version=card["price_version"],
            unit_name=card["unit_name"], unit_count=max_units,
            quoted_unit_usd=per_unit, reserved_usd=reservation,
            period_start=month,
        )
        return BudgetPermit(
            charge_id=charge.pk, request_key=request_key,
            reserved_usd=reservation, projected_month_total_usd=projected,
            month_limit_usd=cap,
            warning_80_percent=projected >= cap * WARNING_RATIO,
            utc_month=month.strftime("%Y-%m"),
        )


def mark_paid_api_dispatch_started(*, owner_id, job_id, request_key):
    """Irreversibly consume one permit immediately BEFORE any paid HTTP call.

    The operator may disable paid calls or replace a tariff between the
    initial reservation and dispatch. Re-check them here; never use the
    stale quote after the UTC period switches.
    """
    if not isinstance(request_key, UUID):
        raise PaidApiBudgetError("invalid_reservation")
    if not getattr(settings, "PAID_API_CALLS_ENABLED", False):
        raise PaidApiBudgetError("paid_calls_disabled")
    cap = configured_cap()
    with transaction.atomic():
        locked_gate()
        row = PaidApiCharge.objects.filter(
            request_key=request_key, job_id=job_id, job__owner_id=owner_id,
        ).first()
        if row is None:
            raise PaidApiBudgetError("not_authorized")
        if row.state != PaidApiCharge.State.RESERVED or row.dispatch_started_at:
            raise PaidApiBudgetError("already_dispatched_or_finished")
        if row.period_start != utc_month():
            raise PaidApiBudgetError("period_changed")
        card, per_unit = approved_rate(row.rate_key)
        if (
            card["provider"] != row.provider or card["purpose"] != row.purpose
            or card["model"] != row.model_id
            or card["price_version"] != row.price_version
            or card["unit_name"] != row.unit_name
            or per_unit != row.quoted_unit_usd
        ):
            raise PaidApiBudgetError("pricing_changed")
        total, _ = month_charges(row.period_start)
        if total > cap:
            raise PaidApiBudgetError("budget_exhausted")
        row.dispatch_started_at = timezone.now()
        row.save(update_fields=("dispatch_started_at",))
        return row


def reconcile_paid_api_budget(*, owner_id, job_id, request_key, actual_usd=None):
    """Known provider cost or conservatively UNKNOWN. Never default to zero.

    Unknown billing after a timeout or remote error stays committed until a
    trustworthy later settlement. Actual > reserved is recorded in full;
    the next paid request must fail closed if the cap is exceeded.
    """
    if not isinstance(request_key, UUID):
        raise PaidApiBudgetError("invalid_reservation")
    actual = usd(actual_usd, allow_zero=True) if actual_usd is not None else None
    with transaction.atomic():
        locked_gate()
        row = PaidApiCharge.objects.filter(
            request_key=request_key, job_id=job_id, job__owner_id=owner_id,
        ).first()
        if row is None:
            raise PaidApiBudgetError("not_authorized")
        if row.state == PaidApiCharge.State.RELEASED:
            raise PaidApiBudgetError("already_released")
        if row.state == PaidApiCharge.State.SETTLED:
            if row.actual_usd == actual:
                return row
            raise PaidApiBudgetError("already_reconciled")
        if row.state == PaidApiCharge.State.UNCERTAIN and actual is None:
            return row
        row.state = (
            PaidApiCharge.State.SETTLED if actual is not None
            else PaidApiCharge.State.UNCERTAIN
        )
        row.actual_usd = actual
        row.reconciled_at = timezone.now()
        row.save(update_fields=("state", "actual_usd", "reconciled_at"))
        return row


def release_unspent_paid_api_budget(*, owner_id, job_id, request_key,
                                    verified_no_dispatch=False):
    """Release ONLY when trusted adapter proves no external dispatch began.

    Timeouts, remote HTTP errors and uncertain billing cannot be released.
    """
    if verified_no_dispatch is not True or not isinstance(request_key, UUID):
        raise PaidApiBudgetError("release_not_proven")
    with transaction.atomic():
        locked_gate()
        row = PaidApiCharge.objects.filter(
            request_key=request_key, job_id=job_id, job__owner_id=owner_id,
        ).first()
        if row is None:
            raise PaidApiBudgetError("not_authorized")
        if row.state != PaidApiCharge.State.RESERVED or row.dispatch_started_at:
            raise PaidApiBudgetError("already_dispatched_or_finished")
        row.state = PaidApiCharge.State.RELEASED
        row.reconciled_at = timezone.now()
        row.save(update_fields=("state", "reconciled_at"))
        return row


def paid_api_budget_status(*, now=None):
    """Read-only, no HTTP/network, credentials or user/private details."""
    month = utc_month(now)
    used, uncertain = month_charges(month)
    try:
        cap = configured_cap()
    except PaidApiBudgetError:
        cap = None
    return {
        "utc_month": month.strftime("%Y-%m"),
        "enabled": bool(getattr(settings, "PAID_API_CALLS_ENABLED", False)),
        "limit_usd": cap,
        "committed_usd": used,
        "available_usd": max(cap - used, Decimal("0")) if cap is not None else None,
        "warning_80_percent": cap is not None and used >= cap * WARNING_RATIO,
        "open_or_uncertain": uncertain,
    }
