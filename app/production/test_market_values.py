"""No-network contract tests for lawful, source-bound market-value facts."""
import json
from datetime import datetime, timezone
from decimal import Decimal

from django.test import SimpleTestCase

from .market_values import normalize_market_value


class MarketValueTests(SimpleTestCase):
    SOURCE = "https://www.example.org/market-values/club-123"
    RETRIEVED = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)

    def value(self, **changes):
        args = {
            "amount": "125000000.50",
            "currency": "EUR",
            "value_date": "2026-11-10",
            "retrieved_at": self.RETRIEVED,
            "source_url": self.SOURCE,
            "metric": "squad_total",
            "rights_basis": "licensed",
        }
        args.update(changes)
        return normalize_market_value(**args)

    def test_valid_squad_estimate_is_sourced_and_unverified(self):
        data = self.value()
        self.assertEqual(data["amount"], "125000000.50")
        self.assertEqual(data["currency"], "EUR")
        self.assertEqual(data["metric"], "squad_total")
        self.assertEqual(data["value_date"], "2026-11-10")
        self.assertEqual(data["source_url"], self.SOURCE)
        self.assertEqual(data["verification_state"], "unverified")
        json.dumps(data)

    def test_player_value_is_separate_from_squad_sum(self):
        data = self.value(metric="player_estimate", amount=Decimal("4000000"))
        self.assertEqual(data["metric"], "player_estimate")
        self.assertEqual(data["amount"], "4000000.00")

    def test_permitted_currencies_without_implicit_conversion(self):
        for currency in ("EUR", "USD", "GBP"):
            with self.subTest(currency=currency):
                self.assertEqual(self.value(currency=currency)["currency"], currency)
        for currency in ("eur", "BTC", None, ""):
            with self.subTest(currency=currency):
                with self.assertRaises(ValueError):
                    self.value(currency=currency)

    def test_missing_unauthorized_and_unscoped_data_fail_closed(self):
        for rights in (None, "unknown", "public", "scraped"):
            with self.subTest(rights=rights):
                with self.assertRaises(ValueError):
                    self.value(rights_basis=rights)
        for metric in ("club_enterprise_value", "transfer_fee", "annual_revenue"):
            with self.subTest(metric=metric):
                with self.assertRaises(ValueError):
                    self.value(metric=metric)

    def test_invalid_amounts_and_zero_are_not_treated_as_known(self):
        invalid = (None, False, 1.5, "€20m", "1,200,000",
                   "12.345", "0", 0, "-100", "", "NaN", float("inf"))
        for amount in invalid:
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    self.value(amount=amount)
        self.assertEqual(self.value(amount=1000000)["amount"], "1000000.00")

    def test_valuation_date_and_retrieval_time_are_required(self):
        for stamp in ("2027-01-01", "2026-02-30", None, ""):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ValueError):
                    self.value(value_date=stamp)
        for at in (None, datetime(2026, 11, 11, 3, 0), "2026-11-11T03:00Z"):
            with self.subTest(at=at):
                with self.assertRaises(ValueError):
                    self.value(retrieved_at=at)

    def test_sources_must_have_public_https_without_embedded_credentials(self):
        invalid = (
            "http://www.example.org/value", "https://127.0.0.1/value",
            "https://localhost/value", "https://internal.local/value",
            "https://user:pass@www.example.org/value",
            "https://www.example.org:8443/value", "https://www.example.org/value?session=1",
            "https://www.example.org/value#details", None,
        )
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.value(source_url=url)

    def test_supplier_permission_is_explicit_not_inferred(self):
        data = self.value(rights_basis="permission_granted")
        self.assertEqual(data["rights_basis"], "permission_granted")
