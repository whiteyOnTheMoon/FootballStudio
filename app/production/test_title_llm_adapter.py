"""Offline FS-015a provider seam tests: only fake adapters, no network."""
import os
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from app.clubs.models import Club, Country, League
from .models import FactDossier, PaidApiCharge, ProductionJob
from .title_llm_adapter import (
    GeneratedTitles, TitleBackendResult, TitleGenerationError,
    generate_title_candidates,
)


CARDS = {"fixture:title:v1": {
    "provider": "fixture", "purpose": "llm", "model": "fake-only",
    "price_version": "v1", "unit_name": "fake_units",
    "usd_per_unit_upper_bound": "0.01",
    "credential_env": "FS_FAKE_TITLE_TEST_KEY",
}}
ENABLED = override_settings(
    TITLE_LLM_ENABLED=True, PAID_API_CALLS_ENABLED=True,
    API_MONTHLY_BUDGET_USD="10.00", PAID_API_RATE_CARDS=CARDS,
)
BRIEF = {
    "contract": "fs-015a-title-brief-v1",
    "job_id": 1, "dossier_version": 1, "club_name": "Example FC",
    "language": "en", "requested_titles": 3,
    "reviewed_facts": [{"fact_id": 1, "sentence": "The club was founded in 1902.",
                        "supporting_sources": [{"source_id": 1, "url": "https://example.org"}]}],
    "editorial_review_required": True,
}
TITLES = [
    "Example FC: The Club Story",
    "The Football History of Example FC",
    "Example FC: From Its Beginnings",
]


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.result = result or TitleBackendResult(
            candidates={"titles": TITLES}, actual_usd="0.01",
            billing_confirmed=True,
        )
        self.error = error
        self.calls = []

    def generate(self, *, brief, max_units):
        self.calls.append((brief, max_units))
        if self.error:
            raise RuntimeError("fake secret must never escape")
        return self.result


class TitleLlmAdapterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="llm-owner@example.org", password="Fake-Passphrase-2026"
        )
        self.other = User.objects.create_user(
            email="llm-other@example.org", password="Fake-Passphrase-2026"
        )
        country = Country.objects.create(code="GB", name="United Kingdom")
        league = League.objects.create(
            country=country, name="Fake League", tier=1,
            provider="manual", provider_id="",
        )
        club = Club.objects.create(
            league=league, name="Example FC", provider="manual",
            provider_id="", is_manual=True,
        )
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="A Manual Title",
            country_code="GB", league_name="Fake League", club_name="Example FC",
        )
        FactDossier.objects.create(job=self.job, version=1)
        self.vars = patch.dict(
            os.environ, {"FS_FAKE_TITLE_TEST_KEY": "FAKE-DO-NOT-USE"}
        )
        self.vars.start()
        self.addCleanup(self.vars.stop)

    def invoke(self, backend, **overrides):
        args = dict(
            owner=self.owner, job_id=self.job.pk, version=1,
            rate_key="fixture:title:v1", max_units=2,
            request_key=uuid4(), backend=backend,
        )
        args.update(overrides)
        return generate_title_candidates(**args)

    def test_both_switches_fail_closed_before_backend_or_charge(self):
        provider = FakeProvider()
        with patch("app.production.title_llm_adapter.build_title_brief") as brief:
            with self.assertRaisesMessage(TitleGenerationError, "title_llm_disabled"):
                self.invoke(provider)
            brief.assert_not_called()
        with override_settings(TITLE_LLM_ENABLED=True):
            with self.assertRaisesMessage(TitleGenerationError, "paid_calls_disabled"):
                self.invoke(provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_fake_provider_settles_once_and_only_returns_editorial_candidates(self):
        provider = FakeProvider()
        with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
            result = self.invoke(provider)
        self.assertIsInstance(result, GeneratedTitles)
        self.assertEqual(result.titles, tuple(TITLES))
        self.assertTrue(result.requires_editorial_review)
        self.assertEqual(len(provider.calls), 1)
        charge = PaidApiCharge.objects.get(pk=result.charge_id)
        self.assertEqual(charge.state, PaidApiCharge.State.SETTLED)
        self.assertEqual(str(charge.actual_usd), "0.010000")
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "A Manual Title")

    @ENABLED
    def test_other_owner_and_missing_version_are_blocked_pre_dispatch(self):
        provider = FakeProvider()
        for fields, code in [
            ({"owner": self.other}, "not_authorized"),
            ({"version": 99}, "dossier_not_found"),
        ]:
            with self.subTest(code=code), self.assertRaisesMessage(
                TitleGenerationError, code
            ):
                self.invoke(provider, **fields)
        self.assertEqual(provider.calls, [])
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_no_reviewed_facts_blocks_before_reservation(self):
        provider = FakeProvider()
        with self.assertRaisesMessage(ValueError, "no_reviewed_facts"):
            self.invoke(provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_backend_error_is_safe_and_keeps_uncertain_cost(self):
        provider = FakeProvider(error=True)
        with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
            with self.assertRaisesMessage(TitleGenerationError, "backend_failed") as ctx:
                self.invoke(provider)
        self.assertNotIn("fake secret", str(ctx.exception))
        charge = PaidApiCharge.objects.get()
        self.assertEqual(charge.state, PaidApiCharge.State.UNCERTAIN)
        self.assertIsNone(charge.actual_usd)

    @ENABLED
    def test_unknown_billing_holds_budget(self):
        provider = FakeProvider(TitleBackendResult(
            candidates={"titles": TITLES}, actual_usd=None, billing_confirmed=False,
        ))
        with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
            with self.assertRaisesMessage(TitleGenerationError, "billing_uncertain"):
                self.invoke(provider)
        self.assertEqual(PaidApiCharge.objects.get().state, PaidApiCharge.State.UNCERTAIN)

    @ENABLED
    def test_invalid_titles_still_settle_known_provider_cost(self):
        provider = FakeProvider(TitleBackendResult(
            candidates={"titles": ["Not our club"]}, actual_usd="0.02",
            billing_confirmed=True,
        ))
        with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
            with self.assertRaisesMessage(TitleGenerationError, "invalid_title_candidates"):
                self.invoke(provider)
        self.assertEqual(PaidApiCharge.objects.get().state, PaidApiCharge.State.SETTLED)

    @ENABLED
    def test_wrong_rate_purpose_cannot_run(self):
        provider = FakeProvider()
        wrong = dict(CARDS["fixture:title:v1"], purpose="tts")
        with override_settings(PAID_API_RATE_CARDS={"fixture:title:v1": wrong}):
            with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
                with self.assertRaisesMessage(TitleGenerationError, "wrong_rate_purpose"):
                    self.invoke(provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_budget_exhaustion_never_calls_provider(self):
        provider = FakeProvider()
        with override_settings(API_MONTHLY_BUDGET_USD="0"):
            with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
                with self.assertRaisesMessage(ValueError, "budget_exhausted"):
                    self.invoke(provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse(PaidApiCharge.objects.exists())

    @ENABLED
    def test_replay_does_not_repeat_provider_call(self):
        provider = FakeProvider()
        request_key = uuid4()
        with patch("app.production.title_llm_adapter.build_title_brief", return_value=BRIEF):
            self.invoke(provider, request_key=request_key)
            with self.assertRaisesMessage(ValueError, "already_reserved"):
                self.invoke(provider, request_key=request_key)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(PaidApiCharge.objects.count(), 1)
