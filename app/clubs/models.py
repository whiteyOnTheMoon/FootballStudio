"""Country → league → club catalog, independent of any fixed pilot club."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower


class Confederation(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.code


class Country(models.Model):
    # Association IDs: ISO-2 where possible, legacy GB for England, and
    # ENG home-nation counterparts NIR/SCO/WAL; XK for Kosovo.
    code = models.CharField(max_length=3, unique=True)
    confederation = models.ForeignKey(
        Confederation, on_delete=models.PROTECT, null=True, blank=True,
        related_name="associations",
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def clean(self):
        super().clean()
        self.code = (self.code or "").strip().upper()
        self.name = " ".join((self.name or "").split())
        if len(self.code) not in (2, 3) or not self.code.isalpha() or not self.code.isascii():
            raise ValidationError({"code": "Use a 2–3-letter football-association code."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = " ".join((self.name or "").split())
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class League(models.Model):
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="leagues")
    name = models.CharField(max_length=160)
    tier = models.PositiveSmallIntegerField(default=1)
    provider = models.CharField(max_length=60, default="manual")
    provider_id = models.CharField(max_length=120, blank=True)
    coverage_status = models.CharField(max_length=16, default="reference")
    source_url = models.URLField(max_length=500, blank=True)
    catalog_season = models.CharField(max_length=10, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("country__name", "tier", "name")
        constraints = [
            models.UniqueConstraint(
                Lower("name"), F("country"), name="clubs_league_name_country_ci"
            )
        ]

    def save(self, *args, **kwargs):
        self.name = " ".join((self.name or "").split())
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.country.code})"


class Club(models.Model):
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="clubs")
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=60, default="manual")
    provider_id = models.CharField(max_length=120, blank=True)
    is_manual = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"), F("league"), name="clubs_club_name_league_ci"
            )
        ]

    def save(self, *args, **kwargs):
        self.name = " ".join((self.name or "").split())
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} — {self.league.name}"
