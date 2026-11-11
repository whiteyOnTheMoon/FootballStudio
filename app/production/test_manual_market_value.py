"""End-to-end tests for optional manually researched squad values on test jobs."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League
from .models import ProductionJob


class ManualMarketValueJobTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="value-owner@example.com", password="Test-Only-Long-Password-2026",
        )
        self.other = User.objects.create_user(
            email="value-other@example.com", password="Test-Only-Other-Password-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Premier League")
        self.club = Club.objects.create(league=league, name="Example FC")
        self.client.force_login(self.owner)
        self.url = reverse("production:create-test")
        self.list_url = reverse("production:list")
        self.payload = {
            "country": "GB", "league": str(league.pk),
            "club": str(self.club.pk), "title": "The History of Example FC",
        }

    def post(self, **extra):
        return self.client.post(self.url, {**self.payload, **extra})

    def test_homepage_exposes_optional_market_value_fields(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'id="market-value-millions"')
        self.assertContains(response, 'id="market-value-currency"')
        self.assertContains(response, 'id="market-value-as-of"')
        self.assertContains(response, 'id="market-value-source-url"')
        self.assertContains(response, "Kader-Marktwert manuell ergänzen")

    def test_absent_value_keeps_previous_job_workflow_unchanged(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["job"]["manual_market_value"])
        job = ProductionJob.objects.get()
        self.assertIsNone(job.manual_market_value_amount)
        self.assertIsNone(job.manual_market_value_as_of)
        self.assertEqual(job.manual_market_value_source_url, "")
        self.assertIsNone(self.client.get(self.list_url).json()["jobs"][0]["manual_market_value"])

    def test_manual_million_amount_saved_as_absolute_rounded_value(self):
        date = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.post(
            market_value_millions="125.50",
            market_value_currency="EUR",
            market_value_as_of=date,
            market_value_source_url="https://example.org/club/squad-value",
        )
        self.assertEqual(response.status_code, 201, response.content)
        job = ProductionJob.objects.get()
        self.assertEqual(job.manual_market_value_amount, Decimal("125500000.00"))
        self.assertEqual(job.manual_market_value_currency, "EUR")
        self.assertEqual(job.manual_market_value_as_of.isoformat(), date)
        self.assertEqual(
            job.manual_market_value_source_url,
            "https://example.org/club/squad-value",
        )
        data = response.json()["job"]["manual_market_value"]
        self.assertEqual(data["metric"], "squad_total")
        self.assertEqual(data["amount"], "125500000.00")
        self.assertEqual(data["millions"], "125.50")
        self.assertEqual(data["currency"], "EUR")
        self.assertEqual(data["as_of"], date)
        self.assertEqual(data["provenance"], "user_entered")
        self.assertEqual(data["verification_state"], "unverified")
        self.assertEqual(self.client.get(self.list_url).json()["jobs"][0]["manual_market_value"], data)

    def test_value_without_date_or_source_remains_explicitly_unverified(self):
        response = self.post(
            market_value_millions="25.25", market_value_currency="GBP",
        )
        self.assertEqual(response.status_code, 201)
        market = response.json()["job"]["manual_market_value"]
        self.assertIsNone(market["as_of"])
        self.assertIsNone(market["source_url"])
        self.assertEqual(market["currency"], "GBP")
        self.assertEqual(market["amount"], "25250000.00")
        self.assertEqual(market["verification_state"], "unverified")

    def test_missing_currency_defaults_eur_and_usd_can_be_selected(self):
        response = self.post(market_value_millions="1")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["job"]["manual_market_value"]["currency"], "EUR")
        response = self.post(market_value_millions="1", market_value_currency="USD")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["job"]["manual_market_value"]["currency"], "USD")

    def test_invalid_or_excessive_amount_is_rejected_and_never_saved(self):
        for amount in ("0", "-1", "1200000", "1.234", "NaN", "1,200",
                       "€120m", "1e6", "0.001"):
            with self.subTest(amount=amount):
                response = self.post(market_value_millions=amount)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ProductionJob.objects.exists())

    def test_orphan_date_or_source_without_value_is_rejected(self):
        today = timezone.localdate().isoformat()
        for extras in (
            {"market_value_as_of": today},
            {"market_value_source_url": "https://example.org/club"},
        ):
            with self.subTest(extras=extras):
                self.assertEqual(self.post(**extras).status_code, 400)
        self.assertFalse(ProductionJob.objects.exists())

    def test_future_or_malformed_date_is_rejected(self):
        for when in (
            (timezone.localdate() + timedelta(days=1)).isoformat(),
            "2026-02-30", "invalid",
        ):
            with self.subTest(when=when):
                response = self.post(
                    market_value_millions="10", market_value_as_of=when,
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ProductionJob.objects.exists())

    def test_unsafe_source_urls_are_rejected(self):
        for url in (
            "http://example.org/value",
            "https://127.0.0.1/value",
            "https://localhost/value",
            "https://bad.local/value",
            "https://user:secret@example.org/value",
            "https://example.org:8443/value",
            "https://example.org/value?secret=1",
            "https://example.org/value#note",
        ):
            with self.subTest(url=url):
                response = self.post(
                    market_value_millions="10", market_value_source_url=url,
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ProductionJob.objects.exists())

    def test_other_user_cannot_read_another_users_saved_estimate(self):
        self.assertEqual(self.post(market_value_millions="42").status_code, 201)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.list_url).json()["jobs"], [])

    def test_model_validation_and_db_constraint_reject_nonpositive_estimate(self):
        self.assertEqual(self.post().status_code, 201)
        job = ProductionJob.objects.get()
        job.manual_market_value_amount = Decimal("0")
        with self.assertRaises(ValidationError):
            job.full_clean()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                ProductionJob.objects.filter(pk=job.pk).update(
                    manual_market_value_amount=Decimal("-1.00"),
                )

    @patch("urllib.request.urlopen")
    def test_manual_submission_does_not_fetch_provider_pages(self, opener):
        response = self.post(
            market_value_millions="80",
            market_value_source_url="https://example.org/market-values",
        )
        self.assertEqual(response.status_code, 201)
        opener.assert_not_called()
