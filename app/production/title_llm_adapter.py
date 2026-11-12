"""FS-015a: gated, provider-neutral title dispatch seam.

No provider SDK, HTTP client, endpoint, credentials, web route or background
worker is included. The injected backend is a trusted application collaborator
(fake in tests), NEVER taken from a request or untrusted plugin. Production
defaults to disabled, independently of the shared paid-API gate.
"""
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from .dossiers import load_fact_dossier
from .models import PaidApiCharge, ProductionJob
from .paid_api_budget import (
    PaidApiBudgetError, approved_rate, mark_paid_api_dispatch_started,
    reconcile_paid_api_budget, release_unspent_paid_api_budget,
    reserve_paid_api_budget, usd,
)
from .title_contract import build_title_brief, validate_title_candidates


class TitleGenerationError(ValueError):
    """Only safe error codes; never include provider error or returned text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TitleBackendResult:
    """Trusted adapter output; provider raw JSON and secrets are not retained."""

    candidates: dict
    actual_usd: str | None = None
    billing_confirmed: bool = False


@dataclass(frozen=True)
class GeneratedTitles:
    titles: tuple[str, str, str]
    charge_id: int
    dossier_version: int
    warning_80_percent: bool
    requires_editorial_review: bool = True


def generate_title_candidates(*, owner, job_id, version, rate_key,
                              max_units, request_key, backend):
    """One explicitly authorized request with no transparent retries.

    Caller must be privileged application code (not an HTTP GET). A future
    approved provider adapter must attest to actual billing; without trusted
    billing the pessimistic reservation remains UNCERTAIN, even for a
    syntactically valid response. No automatically accepted film title.
    """
    if not getattr(settings, "TITLE_LLM_ENABLED", False):
        raise TitleGenerationError("title_llm_disabled")
    if not getattr(settings, "PAID_API_CALLS_ENABLED", False):
        raise TitleGenerationError("paid_calls_disabled")
    if (
        owner is None or type(job_id) is not int or job_id <= 0
        or type(version) is not int or version <= 0
        or type(max_units) is not int or not 1 <= max_units <= 1_000_000
        or not isinstance(request_key, UUID) or request_key.version != 4
        or not callable(getattr(backend, "generate", None))
    ):
        raise TitleGenerationError("invalid_request")
    # The caller is trusted; identity & snapshot scope are rechecked here.
    owner_id = getattr(owner, "pk", None)
    if type(owner_id) is not int or owner_id <= 0:
        raise TitleGenerationError("not_authorized")
    job = ProductionJob.objects.filter(pk=job_id, owner_id=owner_id).first()
    if job is None:
        raise TitleGenerationError("not_authorized")
    try:
        snapshot = load_fact_dossier(owner=owner, job_id=job_id, version=version)
    except ObjectDoesNotExist:
        raise TitleGenerationError("dossier_not_found") from None
    brief = build_title_brief(snapshot, club_name=job.club_name)
    # Explicit LLM-only tariff. A TTS or media rate card is not reusable.
    card, _price = approved_rate(rate_key)
    if card["purpose"] != PaidApiCharge.Purpose.LLM:
        raise TitleGenerationError("wrong_rate_purpose")
    permit = reserve_paid_api_budget(
        owner_id=owner_id, job_id=job_id, rate_key=rate_key,
        max_units=max_units, request_key=request_key,
    )
    try:
        mark_paid_api_dispatch_started(
            owner_id=owner_id, job_id=job_id, request_key=request_key,
        )
    except Exception:
        # This reservation was not dispatched, as the durable marker failed.
        # Releasing is safe only if the ledger itself proves no dispatch.
        release_unspent_paid_api_budget(
            owner_id=owner_id, job_id=job_id, request_key=request_key,
            verified_no_dispatch=True,
        )
        raise

    # From here on: the external call MAY have been billed. All exceptions
    # become UNCERTAIN, and an unknown charge must never be released as zero.
    try:
        result = backend.generate(brief=brief, max_units=max_units)
    except Exception:
        reconcile_paid_api_budget(
            owner_id=owner_id, job_id=job_id, request_key=request_key,
            actual_usd=None,
        )
        raise TitleGenerationError("backend_failed") from None
    if not isinstance(result, TitleBackendResult):
        reconcile_paid_api_budget(
            owner_id=owner_id, job_id=job_id, request_key=request_key,
            actual_usd=None,
        )
        raise TitleGenerationError("invalid_backend_result")

    if result.billing_confirmed is True:
        try:
            cost = usd(result.actual_usd, allow_zero=True)
        except (PaidApiBudgetError, TypeError):
            cost = None
    else:
        cost = None
    reconcile_paid_api_budget(
        owner_id=owner_id, job_id=job_id, request_key=request_key,
        actual_usd=cost,
    )
    if cost is None:
        raise TitleGenerationError("billing_uncertain")
    try:
        titles = validate_title_candidates(
            result.candidates, club_name=job.club_name,
            reviewed_sentences=[row["sentence"] for row in brief["reviewed_facts"]],
        )
    except ValueError:
        raise TitleGenerationError("invalid_title_candidates") from None
    return GeneratedTitles(
        titles=titles, charge_id=permit.charge_id,
        dossier_version=version,
        warning_80_percent=permit.warning_80_percent,
    )
