"""Operator reset must preserve real jobs, catalog, users and paid ledger."""
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from app.clubs.models import Club, Country, League
from .models import (
    Evidence, Fact, FactDossier, FactReview, PaidApiCharge,
    ProductionJob, ScenePlanSnapshot, SourceConfirmation, SourceReference,
)

CONFIRM = "DELETE_PROTOTYPE_TEST_JOBS"


class ResetPrototypeJobsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="cleanup-primary@example.org",
            password="Local-fixture-password-12345",
        )
        self.other = User.objects.create_user(
            email="cleanup-secondary@example.org",
            password="Local-fixture-password-12345",
        )
        self.country = Country.objects.create(code="AT", name="Austria")
        self.league = League.objects.create(
            country=self.country, name="Austrian Bundesliga",
        )
        self.club = Club.objects.create(
            league=self.league, name="Sturm Graz",
        )
        self.proto = self.job(self.owner, "First test")
        self.another_proto = self.job(self.other, "Second test")
        self.film = self.job(
            self.owner, "Real film job", kind=ProductionJob.Kind.FILM,
        )
        self.proto_dossier = self.sourced_dossier(self.proto)
        self.film_dossier = self.sourced_dossier(self.film)
        ScenePlanSnapshot.objects.create(
            job=self.proto,
            dossier_version=1,
            words_per_minute=145,
            source_script_fingerprint_sha256="1" * 64,
            plan_fingerprint_sha256="2" * 64,
            plan_payload={"research_stage": "fixture"},
        )

    def job(self, owner, title, *, kind=ProductionJob.Kind.PROTOTYPE):
        return ProductionJob.objects.create(
            owner=owner, club=self.club, title=title, kind=kind,
            club_name="Sturm Graz", country_code="AT",
            league_name="Austrian Bundesliga",
        )

    def sourced_dossier(self, job):
        dossier = FactDossier.objects.create(job=job, version=1)
        source = SourceReference.objects.create(
            dossier=dossier, source_kind="club_official",
            url="https://sksturm.at/", title="Official club",
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        SourceConfirmation.objects.create(
            source=source, reviewer=job.owner,
            checked_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            confirmed_domain="sksturm.at", terms_confirmed=True,
            access_confirmed=True, identity_confirmed=True,
            basis="User personally confirmed the official club home site.",
        )
        fact = Fact.objects.create(
            dossier=dossier, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )
        Evidence.objects.create(
            source=source, fact=fact, locator="club history",
            summary="Documented club founding year", role="unknown",
        )
        return dossier

    def reset(self, *, execute=False, backup=False, confirm="", owner_id=None):
        out = StringIO()
        args = {}
        if execute:
            args["execute"] = True
        if backup:
            args["backup_verified"] = True
        if confirm:
            args["confirm"] = confirm
        if owner_id is not None:
            args["owner_id"] = owner_id
        call_command("reset_prototype_jobs", stdout=out, **args)
        return out.getvalue()

    def test_default_lists_targets_but_does_not_delete(self):
        report = self.reset()
        self.assertIn("matching test jobs: 2", report)
        self.assertIn("DRY RUN ONLY", report)
        self.assertIn("First test", report)
        self.assertIn("Second test", report)
        self.assertNotIn("Real film job", report)
        self.assertEqual(ProductionJob.objects.count(), 3)
        self.assertEqual(Evidence.objects.count(), 2)

    def test_requires_both_explicit_confirmation_and_backup_attestation(self):
        for kwargs in (
            {"execute": True},
            {"execute": True, "backup": True},
            {"execute": True, "confirm": CONFIRM},
            {"execute": True, "backup": True, "confirm": "DELETE_ALL"},
            {"backup": True},
            {"confirm": CONFIRM},
        ):
            with self.subTest(args=kwargs), self.assertRaises(CommandError):
                self.reset(**kwargs)
        self.assertEqual(ProductionJob.objects.count(), 3)
        self.assertEqual(FactDossier.objects.count(), 2)

    def test_deletes_only_prototypes_and_all_related_research_data(self):
        summary = self.reset(
            execute=True, backup=True, confirm=CONFIRM,
        )
        self.assertIn("Deleted 2 prototype test job(s)", summary)
        self.assertEqual(
            list(ProductionJob.objects.values_list("pk", flat=True)),
            [self.film.pk],
        )
        self.assertEqual(
            list(FactDossier.objects.values_list("job_id", flat=True)),
            [self.film.pk],
        )
        self.assertEqual(
            list(Evidence.objects.values_list("fact__dossier__job_id", flat=True)),
            [self.film.pk],
        )
        self.assertEqual(
            list(SourceConfirmation.objects.values_list(
                "source__dossier__job_id", flat=True,
            )),
            [self.film.pk],
        )
        self.assertFalse(ScenePlanSnapshot.objects.exists())
        self.assertEqual(get_user_model().objects.count(), 2)
        self.assertEqual(Country.objects.count(), 1)
        self.assertEqual(League.objects.count(), 1)
        self.assertEqual(Club.objects.count(), 1)

    def test_repeated_execution_is_idempotent_with_no_prototype_left(self):
        self.reset(execute=True, backup=True, confirm=CONFIRM)
        again = self.reset(execute=True, backup=True, confirm=CONFIRM)
        self.assertIn("matching test jobs: 0", again)
        self.assertIn("Deleted 0 prototype test job(s)", again)
        self.assertEqual(ProductionJob.objects.count(), 1)

    def test_owner_scope_never_targets_other_owners_test_jobs(self):
        out = self.reset(owner_id=self.owner.pk)
        self.assertIn("matching test jobs: 1", out)
        self.reset(
            execute=True, backup=True, confirm=CONFIRM,
            owner_id=self.owner.pk,
        )
        self.assertTrue(ProductionJob.objects.filter(pk=self.another_proto.pk).exists())
        self.assertTrue(ProductionJob.objects.filter(pk=self.film.pk).exists())
        self.assertFalse(ProductionJob.objects.filter(pk=self.proto.pk).exists())
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_invalid_owner_scope_does_not_delete_anything(self):
        with self.assertRaises(CommandError):
            self.reset(
                execute=True, backup=True, confirm=CONFIRM, owner_id=0,
            )
        self.assertEqual(ProductionJob.objects.count(), 3)

    def test_cost_ledger_blocks_even_deletion_with_explicit_flags(self):
        charge = PaidApiCharge.objects.create(
            request_key=uuid4(), job=self.proto,
            purpose=PaidApiCharge.Purpose.RESEARCH,
            provider="unit-test-provider", rate_key="unit-test-rate",
            model_id="offline", price_version="test",
            unit_name="unit", unit_count=1,
            quoted_unit_usd=Decimal("0.050000"),
            reserved_usd=Decimal("0.050000"),
            period_start=date(2026, 11, 1),
            state=PaidApiCharge.State.RESERVED,
        )
        with self.assertRaisesMessage(CommandError, "Blocked"):
            self.reset(execute=True, backup=True, confirm=CONFIRM)
        self.assertTrue(PaidApiCharge.objects.filter(pk=charge.pk).exists())
        self.assertEqual(ProductionJob.objects.count(), 3)
        self.assertEqual(Evidence.objects.count(), 2)

    def test_a_verification_record_is_cascaded_only_for_test_job(self):
        fact = self.proto_dossier.facts.get()
        link = fact.evidence.get()
        link.role = Evidence.Role.SUPPORTS
        link.save(update_fields=["role"])
        fact.verification_state = Fact.Verification.VERIFIED
        fact.save(update_fields=["verification_state"])
        FactReview.objects.create(
            fact=fact, reviewer=self.owner,
            decision=Fact.Verification.VERIFIED,
            note=(
                "The named official club source was reviewed against "
                "the historical foundation year."
            ),
            checked_source=True, checked_season=False,
        )
        self.reset(execute=True, backup=True, confirm=CONFIRM)
        self.assertFalse(FactReview.objects.exists())
        self.assertTrue(ProductionJob.objects.filter(pk=self.film.pk).exists())
