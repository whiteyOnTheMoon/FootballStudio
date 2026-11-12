"""Offline regressions for the global, provider-neutral monthly paid API budget.

No real API keys, paid requests or provider endpoints. SQLite checks all
functional cases, PostgreSQL also checks two concurrent workers serializing
against the SAME shared budget lock.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
import os
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .models import PaidApiCharge, ProductionJob, SharedPaidApiBudgetLock
from .paid_api_budget import (
    PaidApiBudgetError, configured_cap, mark_paid_api_dispatch_started,
    paid_api_budget_status, reconcile_paid_api_budget,
    release_unspent_paid_api_budget, reserve_paid_api_budget, usd,
)


CARDS = {
    "fixture:text:rev1": {
        "provider": "fixture_a", "purpose": "llm",
        "model": "frozen-fixture-model", "price_version": "rev1",
        "unit_name": "max_input_output_token_block",
        "usd_per_unit_upper_bound": "0.01",
        "credential_env": "FS_TEST_FIXTURE_API_KEY",
    },
    "fixture:voice:rev1": {
        "provider": "fixture_b", "purpose": "tts",
        "model": "fixture-voice", "price_version": "rev1",
        "unit_name": "max_char_block",
        "usd_per_unit_upper_bound": "0.50",
        "credential_env": "FS_TEST_FIXTURE_API_KEY",
    },
}
ENABLED = override_settings(
    PAID_API_CALLS_ENABLED=True,
    API_MONTHLY_BUDGET_USD="10.00",
    PAID_API_RATE_CARDS=CARDS,
)


class BudgetFixtures:
    def setUp(self):
        super().setUp()
        self.credential_patch = patch.dict(
            os.environ, {"FS_TEST_FIXTURE_API_KEY": "fake-fixture-only-no-real-token"},
        )
        self.credential_patch.start()
        self.addCleanup(self.credential_patch.stop)
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="cost-owner@example.org", password="No-Real-Paid-API-2026",
        )
        self.foreign = User.objects.create_user(
            email="cost-other@example.org", password="No-Real-Paid-API-Other-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Cost-safe story",
            country_code="AT", league_name=league.name, club_name=club.name,
        )
        self.job2 = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Second cost-safe story",
            country_code="AT", league_name=league.name, club_name=club.name,
        )

    def reserve(self, units=1, *, rate="fixture:text:rev1", job=None,
                key=None, owner=None):
        return reserve_paid_api_budget(
            owner_id=(owner or self.owner).pk,
            job_id=(job or self.job).pk,
            rate_key=rate, max_units=units, request_key=key or uuid4(),
        )

    def assert_rejected(self, code, fn, *args, **kwargs):
        with self.assertRaises(PaidApiBudgetError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class PaidBudgetTests(BudgetFixtures, TestCase):
    def test_gate_is_migrated_as_one_permanent_singleton(self):
        self.assertEqual(
            list(SharedPaidApiBudgetLock.objects.values_list("pk", flat=True)), [1],
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SharedPaidApiBudgetLock.objects.create(pk=2)

    def test_paid_apis_default_to_disabled_even_with_budget_and_price(self):
        with override_settings(PAID_API_CALLS_ENABLED=False):
            self.assert_rejected("paid_calls_disabled", self.reserve)
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_month_total_and_warning_at_exactly_8_dollars(self):
        first = self.reserve(799)
        self.assertEqual(first.reserved_usd, Decimal("7.990000"))
        self.assertFalse(first.warning_80_percent)
        second = self.reserve(1, job=self.job2)
        self.assertEqual(second.projected_month_total_usd, Decimal("8.000000"))
        self.assertTrue(second.warning_80_percent)
        status = paid_api_budget_status()
        self.assertEqual(status["committed_usd"], Decimal("8.000000"))
        self.assertEqual(status["available_usd"], Decimal("2.000000"))
        self.assertTrue(status["warning_80_percent"])
        self.assertEqual(status["open_or_uncertain"], 2)
        self.assertEqual(
            PaidApiCharge.objects.get(pk=first.charge_id).price_version, "rev1",
        )

    @ENABLED
    def test_shared_across_jobs_and_all_providers_not_per_provider(self):
        self.reserve(900, job=self.job)
        self.reserve(1, rate="fixture:voice:rev1", job=self.job2)
        self.assert_rejected(
            "budget_exhausted", self.reserve, 2,
            rate="fixture:voice:rev1", job=self.job2,
        )
        self.assertEqual(PaidApiCharge.objects.count(), 2)
        self.assertEqual(
            paid_api_budget_status()["committed_usd"], Decimal("9.500000"),
        )

    @ENABLED
    def test_exact_cap_allows_and_one_more_cent_blocks(self):
        self.reserve(999)
        self.assert_rejected("budget_exhausted", self.reserve, 2)
        last = self.reserve(1)
        self.assertEqual(last.projected_month_total_usd, Decimal("10.000000"))
        self.assert_rejected("budget_exhausted", self.reserve, 1)
        self.assertEqual(PaidApiCharge.objects.count(), 2)

    @ENABLED
    def test_zero_budget_and_disabled_budget_are_fail_closed(self):
        with override_settings(API_MONTHLY_BUDGET_USD="0"):
            self.assert_rejected("budget_exhausted", self.reserve)
        for raw in ("", "-1", "NaN", "100.00", "10.01", "Infinity"):
            with self.subTest(raw=raw):
                with override_settings(API_MONTHLY_BUDGET_USD=raw):
                    code = "budget_exceeds_approval" if raw in ("100.00", "10.01") else "budget_unconfigured"
                    self.assert_rejected(code, self.reserve)
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_missing_price_token_credentials_and_tariff_disable_request(self):
        self.assert_rejected("price_unconfigured", self.reserve, rate="unknown")
        with override_settings(PAID_API_RATE_CARDS={}):
            self.assert_rejected("price_unconfigured", self.reserve)
        with patch.dict(os.environ, {"FS_TEST_FIXTURE_API_KEY": ""}):
            self.assert_rejected("provider_credentials_missing", self.reserve)
        corrupt = {**CARDS, "fixture:text:rev1": {
            **CARDS["fixture:text:rev1"],
            "usd_per_unit_upper_bound": "0",
        }}
        with override_settings(PAID_API_RATE_CARDS=corrupt):
            self.assert_rejected("price_unconfigured", self.reserve)
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_float_nan_infinity_unsafe_units_and_wrong_user_are_denied(self):
        for number in (float("nan"), float("inf"), -1, True, 1e-20, "1e-5", "0.0000000000001"):
            with self.subTest(number=repr(number)):
                self.assert_rejected("invalid_cost", usd, number)
        for units in (0, -1, 1000001, 1.5, True, "5"):
            with self.subTest(units=units):
                self.assert_rejected("invalid_reservation", self.reserve, units)
        self.assert_rejected(
            "not_authorized", self.reserve, owner=self.foreign,
        )
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_billing_must_be_real_unknown_keeps_conservative_reserve(self):
        permit = self.reserve(100)
        row = reconcile_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key,
        )
        self.assertEqual(row.state, "uncertain")
        self.assertIsNone(row.actual_usd)
        self.assertEqual(
            paid_api_budget_status()["committed_usd"], Decimal("1.000000"),
        )
        self.assert_rejected(
            "release_not_proven", release_unspent_paid_api_budget,
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key,
        )
        self.assert_rejected(
            "already_dispatched_or_finished", release_unspent_paid_api_budget,
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, verified_no_dispatch=True,
        )
        row = reconcile_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, actual_usd="0.25",
        )
        self.assertEqual(row.state, "settled")
        self.assertEqual(paid_api_budget_status()["committed_usd"], Decimal("0.250000"))
        again = reconcile_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, actual_usd="0.25",
        )
        self.assertEqual(again.pk, row.pk)
        self.assert_rejected(
            "already_reconciled", reconcile_paid_api_budget,
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, actual_usd="0.50",
        )

    @ENABLED
    def test_actual_overquote_is_fully_charged_and_blocks_future_calls(self):
        permit = self.reserve(100)
        row = reconcile_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, actual_usd="11.00",
        )
        self.assertEqual(row.actual_usd, Decimal("11.000000"))
        self.assertEqual(paid_api_budget_status()["committed_usd"], Decimal("11.000000"))
        self.assert_rejected("budget_exhausted", self.reserve)
        self.assertEqual(PaidApiCharge.objects.count(), 1)

    @ENABLED
    def test_dispatch_must_be_explicit_and_can_only_happen_once(self):
        permit = self.reserve(1)
        row = mark_paid_api_dispatch_started(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key,
        )
        self.assertIsNotNone(row.dispatch_started_at)
        self.assert_rejected(
            "already_dispatched_or_finished", mark_paid_api_dispatch_started,
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key,
        )
        self.assert_rejected(
            "already_dispatched_or_finished", release_unspent_paid_api_budget,
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=permit.request_key, verified_no_dispatch=True,
        )
        with override_settings(PAID_API_CALLS_ENABLED=False):
            self.assert_rejected(
                "paid_calls_disabled", mark_paid_api_dispatch_started,
                owner_id=self.owner.pk, job_id=self.job.pk,
                request_key=uuid4(),
            )

    @ENABLED
    def test_no_dispatch_release_and_same_uuid_replay_are_terminal(self):
        key = uuid4()
        self.reserve(100, key=key)
        row = release_unspent_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk,
            request_key=key, verified_no_dispatch=True,
        )
        self.assertEqual(row.state, "released")
        self.assertEqual(paid_api_budget_status()["committed_usd"], Decimal("0"))
        self.assert_rejected("already_reserved", self.reserve, 1, key=key)
        self.assertEqual(PaidApiCharge.objects.count(), 1)

    @ENABLED
    def test_dispatch_rechecks_tariff_credentials_and_product_cap(self):
        key = self.reserve(1).request_key
        with patch.dict(os.environ, {"FS_TEST_FIXTURE_API_KEY": ""}):
            self.assert_rejected(
                "provider_credentials_missing", mark_paid_api_dispatch_started,
                owner_id=self.owner.pk, job_id=self.job.pk, request_key=key,
            )
        changed = {**CARDS, "fixture:text:rev1": {
            **CARDS["fixture:text:rev1"], "price_version": "rev2",
        }}
        with override_settings(PAID_API_RATE_CARDS=changed):
            self.assert_rejected(
                "pricing_changed", mark_paid_api_dispatch_started,
                owner_id=self.owner.pk, job_id=self.job.pk, request_key=key,
            )
        with override_settings(API_MONTHLY_BUDGET_USD="0.005"):
            self.assert_rejected(
                "budget_exhausted", mark_paid_api_dispatch_started,
                owner_id=self.owner.pk, job_id=self.job.pk, request_key=key,
            )
        self.assertIsNone(PaidApiCharge.objects.get(request_key=key).dispatch_started_at)

    @ENABLED
    def test_utc_month_rollover_does_not_delete_prior_charges(self):
        dec = datetime(2026, 12, 1, 0, 0, 1, tzinfo=dt_timezone.utc)
        nov = datetime(2026, 11, 30, 23, 59, 59, tzinfo=dt_timezone.utc)
        with patch("app.production.paid_api_budget.timezone.now", return_value=nov):
            self.reserve(1000)
        with patch("app.production.paid_api_budget.timezone.now", return_value=dec):
            december = self.reserve(1000, job=self.job2)
            december_status = paid_api_budget_status()
        self.assertEqual(december.utc_month, "2026-12")
        self.assertEqual(december_status["committed_usd"], Decimal("10.000000"))
        self.assertEqual(
            list(PaidApiCharge.objects.order_by("period_start").values_list(
                "period_start", flat=True,
            )),
            [nov.date().replace(day=1), dec.date().replace(day=1)],
        )
        self.assertEqual(PaidApiCharge.objects.count(), 2)

    @ENABLED
    def test_unknown_error_does_not_reset_usage_on_retry(self):
        key = self.reserve(800).request_key
        self.assert_rejected(
            "already_reserved", self.reserve, 1, key=key,
        )
        reconcile_paid_api_budget(
            owner_id=self.owner.pk, job_id=self.job.pk, request_key=key,
            actual_usd=None,
        )
        self.assert_rejected("budget_exhausted", self.reserve, 201)
        self.assertEqual(paid_api_budget_status()["open_or_uncertain"], 1)

    @ENABLED
    def test_no_web_view_or_paid_client_exists_in_guard(self):
        # The budget service itself is DB/clock/env-only. No provider methods.
        with patch("urllib.request.urlopen") as fetch:
            self.reserve(10)
            paid_api_budget_status()
            fetch.assert_not_called()


@ENABLED
class BudgetConcurrentPostgresTests(BudgetFixtures, TransactionTestCase):
    """Two independent DB connections must not both spend the final dollar."""

    def test_two_workers_share_one_row_lock(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL SELECT FOR UPDATE concurrency regression")
        barrier = Barrier(2)

        def attempt(job_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                permit = reserve_paid_api_budget(
                    owner_id=self.owner.pk, job_id=job_id,
                    rate_key="fixture:text:rev1",
                    max_units=800, request_key=uuid4(),
                )
                return ("accepted", permit.charge_id)
            except PaidApiBudgetError as error:
                return ("rejected", error.code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(attempt, self.job.pk)
            b = pool.submit(attempt, self.job2.pk)
            results = [a.result(timeout=20), b.result(timeout=20)]
        self.assertEqual(sorted(x[0] for x in results), ["accepted", "rejected"])
        self.assertEqual(PaidApiCharge.objects.count(), 1)
        self.assertEqual(
            paid_api_budget_status()["committed_usd"], Decimal("8.000000"),
        )
