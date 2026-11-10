"""Country → league → club catalog, independent of any fixed pilot club."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower


class Country(models.Model):
    code = models.CharField(max_length=2, unique=True)  # ISO 3166-1 alpha-2
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def clean(self):
        super().clean()
        self.code = (self.code or "").strip().upper()
        self.name = " ".join((self.name or "").split())
        if len(self.code) != 2 or not self.code.isalpha() or not self.code.isascii():
            raise ValidationError({"code": "Use a two-letter ISO country code."})

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
