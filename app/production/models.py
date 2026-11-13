"""Persistent, owner-scoped production jobs with explicit state transitions.

An M1 'prototype' job records the selected club and title only; it does NOT
render video or call a paid API. M2 will add a separate worker and artifacts.
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ProductionJob(models.Model):
    class Kind(models.TextChoices):
        PROTOTYPE = "prototype", "M1 selection test"
        FILM = "film", "Film production"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    TRANSITIONS = {
        Status.DRAFT: {Status.QUEUED},
        Status.QUEUED: {Status.RUNNING, Status.FAILED},
        Status.RUNNING: {Status.COMPLETED, Status.FAILED},
        Status.FAILED: {Status.QUEUED},
        Status.COMPLETED: set(),
    }

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="production_jobs",
    )
    club = models.ForeignKey(
        "clubs.Club", on_delete=models.PROTECT, related_name="production_jobs",
    )
    title = models.CharField(max_length=180)
    language = models.CharField(max_length=8, default="en")
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.PROTOTYPE
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT,
    )
    country_code = models.CharField(max_length=3)
    league_name = models.CharField(max_length=160)
    club_name = models.CharField(max_length=160)
    # Optional user-entered squad market-value estimate, in absolute units.
    # This is research input only; never an automatically verified film fact.
    manual_market_value_amount = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True,
    )
    manual_market_value_currency = models.CharField(
        max_length=3, choices=[("EUR", "Euro"), ("GBP", "British pound"),
                               ("USD", "US dollar")], default="EUR",
    )
    manual_market_value_as_of = models.DateField(null=True, blank=True)
    manual_market_value_source_url = models.URLField(max_length=500, blank=True)
    output_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(manual_market_value_amount__isnull=True)
                | models.Q(manual_market_value_amount__gt=0),
                name="production_job_manual_value_positive",
            ),
        ]

    def __str__(self):
        return f"{self.pk}: {self.club_name} – {self.title}"

    def clean(self):
        super().clean()
        self.title = " ".join((self.title or "").split())
        if not self.title:
            raise ValidationError({"title": "Enter a film title."})
        if self.manual_market_value_amount is None:
            if self.manual_market_value_as_of or self.manual_market_value_source_url:
                raise ValidationError({
                    "manual_market_value_amount": "A market value is required when entering its date or source.",
                })
        else:
            if self.manual_market_value_amount <= 0:
                raise ValidationError({
                    "manual_market_value_amount": "Market value must be positive.",
                })
            if (self.manual_market_value_as_of
                    and self.manual_market_value_as_of > timezone.localdate()):
                raise ValidationError({
                    "manual_market_value_as_of": "The market-value date cannot be in the future.",
                })
        if self.manual_market_value_source_url:
            from .market_values import _source_url
            try:
                self.manual_market_value_source_url = _source_url(
                    self.manual_market_value_source_url
                )
            except ValueError as exc:
                raise ValidationError({
                    "manual_market_value_source_url": str(exc),
                }) from None
        if self.kind == self.Kind.PROTOTYPE and self.status in (
            self.Status.RUNNING, self.Status.COMPLETED,
        ):
            raise ValidationError({
                "status": "M1 selection test jobs cannot run or finish a video."
            })
        if self.status == self.Status.COMPLETED and not self.output_path:
            raise ValidationError({
                "output_path": "Completed film jobs must have a result reference."
            })

    def transition_to(self, next_status, *, error_message=""):
        """Validate one step; a prototype test job never starts rendering."""
        allowed = self.TRANSITIONS.get(self.status, set())
        if next_status not in allowed:
            raise ValidationError(f"Invalid job transition: {self.status} -> {next_status}.")
        if self.kind == self.Kind.PROTOTYPE and next_status == self.Status.RUNNING:
            raise ValidationError("Prototype jobs have no render worker.")
        if next_status == self.Status.FAILED and not error_message.strip():
            raise ValidationError("Failed jobs require a meaningful error message.")
        old_status, old_error = self.status, self.error_message
        old_started, old_finished = self.started_at, self.finished_at
        self.status = next_status
        self.error_message = error_message if next_status == self.Status.FAILED else ""
        if next_status == self.Status.RUNNING:
            self.started_at = timezone.now()
        if next_status in (self.Status.COMPLETED, self.Status.FAILED):
            self.finished_at = timezone.now()
        if next_status == self.Status.QUEUED and old_status == self.Status.FAILED:
            self.finished_at = None
        try:
            self.full_clean()
        except ValidationError:
            self.status, self.error_message = old_status, old_error
            self.started_at, self.finished_at = old_started, old_finished
            raise
        self.save()


class FactDossier(models.Model):
    """A numbered research snapshot associated with a runtime-selected job."""

    job = models.ForeignKey(
        ProductionJob, on_delete=models.CASCADE, related_name="fact_dossiers",
    )
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("job", "version"), name="production_dossier_job_version_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="production_dossier_positive_version",
            ),
        ]


class SourceReference(models.Model):
    """A reference to an identifiable source, not proof of any particular claim."""

    class Kind(models.TextChoices):
        WIKIDATA = "wikidata", "Wikidata"
        WIKIPEDIA = "wikipedia", "Wikipedia"
        CLUB_OFFICIAL = "club_official", "Official club site"
        LEAGUE_OFFICIAL = "league_official", "Official league site"
        NEWS = "news", "News"
        OTHER = "other", "Other"

    class Access(models.TextChoices):
        ACCESSIBLE = "accessible", "Accessible"
        NOT_FOUND = "not_found", "Not found"
        UNAVAILABLE = "unavailable", "Unavailable"
        RESTRICTED = "restricted", "Restricted"
        ERROR = "error", "Error"

    dossier = models.ForeignKey(
        FactDossier, on_delete=models.CASCADE, related_name="sources",
    )
    url = models.URLField(max_length=750)
    source_kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=250, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    retrieved_at = models.DateTimeField()
    access_state = models.CharField(max_length=16, choices=Access.choices)




class SourceConfirmation(models.Model):
    """Audit of a manually checked source, NOT an HTTP fetch or fact review.

    A separate record allows a source entered by the user to be distinguished
    from Wikidata and the server's restricted official-site research. The
    reviewer attests to the site association and manual access, not truth.
    """
    source = models.OneToOneField(
        SourceReference, on_delete=models.CASCADE, related_name="manual_confirmation",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="football_source_confirmations",
    )
    checked_at = models.DateTimeField(default=timezone.now)
    confirmed_domain = models.CharField(max_length=253)
    identity_confirmed = models.BooleanField(default=False)
    terms_confirmed = models.BooleanField(default=False)
    access_confirmed = models.BooleanField(default=False)
    basis = models.CharField(max_length=300)

    def clean(self):
        super().clean()
        if self.source_id and self.reviewer_id:
            if self.source.dossier.job.owner_id != self.reviewer_id:
                raise ValidationError("Only the job owner may confirm a manual source.")
            if self.source.source_kind not in (
                SourceReference.Kind.CLUB_OFFICIAL,
                SourceReference.Kind.LEAGUE_OFFICIAL,
            ) or self.source.access_state != SourceReference.Access.ACCESSIBLE:
                raise ValidationError("Manual confirmation needs an accessible official-type source.")
            from .manual_source_import import validate_manual_source_url
            try:
                canonical, domain = validate_manual_source_url(self.source.url)
            except ValueError:
                raise ValidationError("The manual source URL is not permitted.") from None
            if canonical != self.source.url or domain != self.confirmed_domain:
                raise ValidationError("Confirmed domain does not match the source URL.")
        if (self.identity_confirmed is not True
                or self.terms_confirmed is not True
                or self.access_confirmed is not True):
            raise ValidationError("All three explicit manual source confirmations are required.")
        if (not isinstance(self.basis, str)
                or not 20 <= len(self.basis.strip()) <= 300
                or "<" in self.basis
                or any(ord(c) < 32 or ord(c) == 127 for c in self.basis)):
            raise ValidationError({"basis": "Add a short, plain-text explanation (20–300 characters)."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Fact(models.Model):
    """An atomic statement; never treated as verified without supporting evidence."""

    class Verification(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        VERIFIED = "verified", "Verified"
        CONFLICTED = "conflicted", "Conflicted"
        INSUFFICIENT = "insufficient_sources", "Insufficient sources"
        REJECTED = "rejected", "Rejected"

    dossier = models.ForeignKey(
        FactDossier, on_delete=models.CASCADE, related_name="facts",
    )
    predicate = models.CharField(max_length=100)
    value = models.JSONField(null=True, blank=True)
    assertion_text = models.TextField()
    verification_state = models.CharField(
        max_length=24, choices=Verification.choices, default=Verification.UNVERIFIED,
    )

    def clean(self):
        super().clean()
        if self.verification_state == self.Verification.VERIFIED:
            # A saved, accessible supporting evidence record is a precondition,
            # NOT itself sufficient proof that the assertion is true. Review of
            # evidence content is handled in FS-014c, not automatically here.
            has_support = (
                self.pk is not None
                and self.evidence.filter(
                    role=Evidence.Role.SUPPORTS,
                    source__access_state=SourceReference.Access.ACCESSIBLE,
                ).exists()
            )
            if not has_support:
                raise ValidationError({
                    "verification_state": "A verified fact requires accessible supporting evidence.",
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Evidence(models.Model):
    """A short evidence locator for one fact, tied to a source in its own dossier."""

    class Role(models.TextChoices):
        SUPPORTS = "supports", "Supports"
        CONTRADICTS = "contradicts", "Contradicts"
        CONTEXT_ONLY = "context_only", "Context only"
        UNKNOWN = "unknown", "Unknown"

    fact = models.ForeignKey(
        Fact, on_delete=models.CASCADE, related_name="evidence",
    )
    source = models.ForeignKey(
        SourceReference, on_delete=models.PROTECT, related_name="evidence",
    )
    locator = models.CharField(max_length=250)
    summary = models.TextField(blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.UNKNOWN)

    def clean(self):
        super().clean()
        if self.fact_id and self.source_id and (
            self.fact.dossier_id != self.source.dossier_id
        ):
            raise ValidationError("Fact and evidence source must belong to the same dossier.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class FactReview(models.Model):
    """Explicit, user-attributed decision on ONE fact in ONE dossier version.

    A successful source fetch or a support-role evidence record does not
    create this row. Only the explicit review service creates reviews.
    Historical reviews are copied when versioning a dossier.
    """

    fact = models.OneToOneField(
        Fact, on_delete=models.CASCADE, related_name="review",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="football_fact_reviews",
    )
    decision = models.CharField(
        max_length=24,
        choices=[
            (Fact.Verification.VERIFIED, "Verified"),
            (Fact.Verification.CONFLICTED, "Conflicted"),
            (Fact.Verification.INSUFFICIENT, "Insufficient sources"),
            (Fact.Verification.REJECTED, "Rejected"),
        ],
    )
    note = models.CharField(max_length=500)
    checked_source = models.BooleanField(default=False)
    checked_season = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(default=timezone.now)

    def clean(self):
        super().clean()
        if self.fact_id and self.reviewer_id:
            if self.fact.dossier.job.owner_id != self.reviewer_id:
                raise ValidationError("Only the job owner may review its facts.")
            if self.decision != self.fact.verification_state:
                raise ValidationError("Review decision must equal fact status.")
        if not isinstance(self.note, str) or not 30 <= len(self.note.strip()) <= 500:
            raise ValidationError({"note": "Enter a meaningful, concise review note."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)



class OfficialResearchRequest(models.Model):
    """Audited one-time *authorization* consumed only by an operator-run worker.

    A future independently reviewed worker must check the still-valid consent,
    owner, source, domain, version, robots and SSRF rules again before fetching.
    It does not enqueue tasks. State transitions occur only in the standalone
    operator command and never during a normal HTTP request.
    """

    class Status(models.TextChoices):
        PENDING = "pending_worker", "Recorded; no worker available"
        CANCELLED = "cancelled", "Cancelled by the job owner"
        EXPIRED = "expired", "Consent expired without execution"
        RUNNING = "running", "Research in progress"
        SUCCEEDED = "succeeded", "Bounded metadata research completed"
        FAILED = "failed", "Research stopped without imported pages"
        BLOCKED = "blocked", "Research blocked by site or security rules"

    job = models.ForeignKey(
        ProductionJob, on_delete=models.CASCADE, related_name="official_research_requests",
    )
    source = models.ForeignKey(
        SourceReference, on_delete=models.CASCADE, related_name="research_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="football_research_consents",
    )
    # Unique per job: retries with exactly this browser form UUID are safe.
    request_key = models.UUIDField()
    expected_version = models.PositiveIntegerField()
    confirmed_url = models.URLField(max_length=750)
    confirmed_domain = models.CharField(max_length=253)
    context = models.CharField(
        max_length=8, choices=[("club", "Club"), ("league", "League")],
    )
    # These flags are a *fresh* per-request attestation, not copied from
    # SourceConfirmation. A malicious form cannot opt-in implicitly.
    domain_rechecked = models.BooleanField(default=False)
    terms_rechecked = models.BooleanField(default=False)
    one_time_approved = models.BooleanField(default=False)
    consented_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_pages = models.PositiveSmallIntegerField(default=4)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    lease_key = models.UUIDField(null=True, blank=True)
    failure_code = models.CharField(max_length=40, blank=True)
    result_count = models.PositiveSmallIntegerField(default=0)
    result_dossier_version = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("job", "request_key"), name="production_research_req_key_uniq",
            ),
            models.UniqueConstraint(
                fields=("job",),
                condition=models.Q(status__in=("pending_worker", "running")),
                name="prod_res_one_active_job",
            ),
            models.CheckConstraint(
                condition=models.Q(expected_version__gte=1),
                name="production_research_positive_version",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=1),
                name="production_research_max_one_attempt",
            ),
            models.CheckConstraint(
                condition=models.Q(max_pages=4),
                name="production_research_four_pages",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("consented_at")),
                name="production_research_positive_ttl",
            ),
        ]
        indexes = [
            models.Index(
                fields=("requested_by", "confirmed_domain", "consented_at"),
                name="prod_res_owner_host_idx",
            ),
            models.Index(
                fields=("job", "created_at"), name="prod_res_job_time_idx",
            ),
        ]

    @property
    def visible_status(self):
        """Expiry is enforced even if no housekeeping worker runs."""
        now = timezone.now()
        if self.status == self.Status.PENDING and self.expires_at <= now:
            return self.Status.EXPIRED
        if (
            self.status == self.Status.RUNNING
            and self.lease_expires_at is not None
            and self.lease_expires_at <= now
        ):
            return self.Status.FAILED
        return self.status

    def clean(self):
        super().clean()
        if self.job_id and self.requested_by_id:
            if self.job.owner_id != self.requested_by_id:
                raise ValidationError("Only the job owner can approve this research.")
        if self.source_id and self.job_id:
            if (
                self.source.dossier.job_id != self.job_id
                or self.source.dossier.version != self.expected_version
            ):
                raise ValidationError("The source and research version must belong to the same job.")
            from .manual_source_import import validate_manual_source_url
            try:
                canonical, host = validate_manual_source_url(self.source.url)
            except ValueError:
                raise ValidationError("Source URL is not eligible.") from None
            if canonical != self.confirmed_url or host != self.confirmed_domain:
                raise ValidationError("The approved domain does not match the source.")
            match = {
                SourceReference.Kind.CLUB_OFFICIAL: "club",
                SourceReference.Kind.LEAGUE_OFFICIAL: "league",
            }
            if self.context != match.get(self.source.source_kind):
                raise ValidationError("The approved source context is invalid.")
            if self.source.access_state != SourceReference.Access.ACCESSIBLE:
                raise ValidationError("The approved source is not accessible.")
            try:
                confirmed = self.source.manual_confirmation
            except SourceConfirmation.DoesNotExist:
                raise ValidationError("A manual source confirmation is required.") from None
            if (
                confirmed.reviewer_id != self.requested_by_id
                or confirmed.confirmed_domain != self.confirmed_domain
                or not all((
                    confirmed.identity_confirmed, confirmed.terms_confirmed,
                    confirmed.access_confirmed,
                ))
            ):
                raise ValidationError("The manual source confirmation does not match.")
        if (
            self.domain_rechecked is not True
            or self.terms_rechecked is not True
            or self.one_time_approved is not True
        ):
            raise ValidationError("Fresh, explicit consent for exactly one research request is required.")
        if (
            not self.consented_at or not self.expires_at
            or timezone.is_naive(self.consented_at)
            or timezone.is_naive(self.expires_at)
            or not (
                timedelta(seconds=0)
                < self.expires_at - self.consented_at
                <= timedelta(minutes=15)
            )
        ):
            raise ValidationError("Consent must expire within fifteen minutes.")
        if self.status == self.Status.PENDING and self.cancelled_at is not None:
            raise ValidationError("Pending consent cannot have a cancellation date.")
        if self.status == self.Status.CANCELLED and self.cancelled_at is None:
            raise ValidationError("Cancellation needs a timestamp.")
        if self.attempt_count > 1 or self.max_pages != 4:
            raise ValidationError("This request can never exceed one attempt and four pages.")
        if self.result_count > 4:
            raise ValidationError("No research can contain more than four pages.")
        if self.status == self.Status.RUNNING and (
            self.attempt_count != 1 or self.lease_key is None
            or self.lease_expires_at is None or self.started_at is None
        ):
            raise ValidationError("A running request requires a consumed attempt and lease.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)



class OfficialResearchPage(models.Model):
    """Unverified metadata of one bounded, actually fetched official HTML page."""

    request = models.ForeignKey(
        OfficialResearchRequest, on_delete=models.CASCADE, related_name="pages",
    )
    saved_source = models.ForeignKey(
        SourceReference, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="official_research_page_metadata",
    )
    position = models.PositiveSmallIntegerField()
    url = models.URLField(max_length=750)
    title = models.CharField(max_length=160, blank=True)
    headings = models.JSONField(default=list)
    category = models.CharField(max_length=20, blank=True)
    retrieved_at = models.DateTimeField()
    verification_state = models.CharField(
        max_length=16, default="unverified", editable=False,
    )

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(
                fields=("request", "position"), name="prod_res_page_position_uq",
            ),
            models.UniqueConstraint(
                fields=("request", "url"), name="prod_res_page_url_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=0, position__lte=3),
                name="prod_res_page_four_max",
            ),
            models.CheckConstraint(
                condition=models.Q(verification_state="unverified"),
                name="prod_res_page_unverified",
            ),
        ]

    def clean(self):
        super().clean()
        if self.verification_state != "unverified" or not 0 <= self.position < 4:
            raise ValidationError("Only four unverified pages may be stored.")
        if (
            not isinstance(self.headings, list) or len(self.headings) > 5
            or any(not isinstance(h, str) or len(h) > 160 for h in self.headings)
            or len(self.title) > 160
        ):
            raise ValidationError("Only short title and heading metadata are allowed.")
        from .safe_official_fetch import WebsiteFetchError, _checked_url
        try:
            canonical, host = _checked_url(self.url)
        except WebsiteFetchError:
            raise ValidationError("Unsafe page URL.") from None
        if canonical != self.url or host != self.request.confirmed_domain:
            raise ValidationError("Page must match the confirmed domain.")
        if self.saved_source_id and self.saved_source.url != self.url:
            raise ValidationError("Linked source must refer to the same page.")
        if self.request_id:
            if self.request.status != OfficialResearchRequest.Status.SUCCEEDED:
                raise ValidationError("Results are stored only for a successful attempt.")
            if (
                self.saved_source_id and
                self.saved_source.dossier.job_id != self.request.job_id
            ):
                raise ValidationError("Page source must belong to the same job.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)



class SharedPaidApiBudgetLock(models.Model):
    """Permanent singleton: every provider/worker serializes budget here.

    Migration 0010 creates pk=1. A missing row fails closed; it is NEVER
    created lazily in application code (avoids a cross-worker creation race).
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="prod_paid_budget_singleton",
            ),
        ]


class PaidApiCharge(models.Model):
    """Immutable-in-practice shared USD budget ledger, no secrets or prompts.

    A reservation is not confirmation that a paid provider was called.
    An unknown provider charge stays reserved until manually reconciled.
    """

    class State(models.TextChoices):
        RESERVED = "reserved", "Budget reserved; dispatch not confirmed"
        SETTLED = "settled", "Provider cost confirmed"
        UNCERTAIN = "uncertain", "Provider cost unknown; reserve retained"
        RELEASED = "released", "Confirmed no paid request was sent"

    class Purpose(models.TextChoices):
        LLM = "llm", "Text generation"
        TTS = "tts", "Speech generation"
        MEDIA = "media", "Paid media"
        RESEARCH = "research", "Paid research"

    request_key = models.UUIDField(unique=True)
    job = models.ForeignKey(
        ProductionJob, on_delete=models.PROTECT, related_name="paid_api_charges",
    )
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    provider = models.CharField(max_length=48)
    rate_key = models.CharField(max_length=120)
    model_id = models.CharField(max_length=100)
    price_version = models.CharField(max_length=60)
    unit_name = models.CharField(max_length=30)
    unit_count = models.PositiveIntegerField()
    quoted_unit_usd = models.DecimalField(max_digits=14, decimal_places=6)
    reserved_usd = models.DecimalField(max_digits=14, decimal_places=6)
    actual_usd = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True,
    )
    period_start = models.DateField()  # UTC first of calendar month
    state = models.CharField(
        max_length=12, choices=State.choices, default=State.RESERVED,
    )
    reserved_at = models.DateTimeField(default=timezone.now)
    dispatch_started_at = models.DateTimeField(null=True, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("period_start", "state"), name="prod_paid_month_state_ix",
            ),
            models.Index(
                fields=("job", "reserved_at"), name="prod_paid_job_time_ix",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(unit_count__gte=1),
                name="prod_paid_units_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(quoted_unit_usd__gt=0),
                name="prod_paid_unit_cost_gt0",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_usd__gt=0),
                name="prod_paid_reserve_gt0",
            ),
            models.CheckConstraint(
                condition=models.Q(actual_usd__isnull=True) |
                models.Q(actual_usd__gte=0),
                name="prod_paid_actual_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(state="settled", actual_usd__isnull=False) |
                ~models.Q(state="settled"),
                name="prod_paid_settle_has_cost",
            ),
        ]


class ScenePlanSnapshot(models.Model):
    """Private, immutable-by-service, versioned offline storyboard snapshot.

    PostgreSQL retains the small JSON artifact across web container restarts.
    A consistent SHA-256 is a corruption/staleness check, not authentication.
    """

    job = models.ForeignKey(
        ProductionJob, on_delete=models.CASCADE, related_name="scene_plan_snapshots",
    )
    dossier_version = models.PositiveIntegerField()
    words_per_minute = models.PositiveSmallIntegerField()
    source_script_fingerprint_sha256 = models.CharField(max_length=64)
    plan_fingerprint_sha256 = models.CharField(max_length=64)
    plan_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("dossier_version", "words_per_minute", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("job", "dossier_version", "words_per_minute"),
                name="prod_scene_job_ver_wpm_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(dossier_version__gte=1),
                name="prod_scene_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(words_per_minute__gte=100, words_per_minute__lte=200),
                name="prod_scene_wpm_100_200",
            ),
        ]
