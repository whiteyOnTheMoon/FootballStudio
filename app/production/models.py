"""Persistent, owner-scoped production jobs with explicit state transitions.

An M1 'prototype' job records the selected club and title only; it does NOT
render video or call a paid API. M2 will add a separate worker and artifacts.
"""
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
