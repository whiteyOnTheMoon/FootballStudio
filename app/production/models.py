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
    country_code = models.CharField(max_length=2)
    league_name = models.CharField(max_length=160)
    club_name = models.CharField(max_length=160)
    output_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.pk}: {self.club_name} – {self.title}"

    def clean(self):
        super().clean()
        self.title = " ".join((self.title or "").split())
        if not self.title:
            raise ValidationError({"title": "Enter a film title."})
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
