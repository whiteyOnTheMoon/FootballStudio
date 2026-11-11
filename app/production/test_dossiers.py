"""Persistence and ownership tests for the M2 fact dossier foundation."""
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossiers import load_fact_dossier
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference


class DossierPersistenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="dossier-owner@example.com", password="long-test-password-1234",
        )
        self.other = User.objects.create_user(
            email="other-dossier-user@example.com", password="long-test-password-1234",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Research FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="A club documentary",
            country_code="GB", league_name="Example League", club_name="Research FC",
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=1)
        self.source = SourceReference.objects.create(
            dossier=self.dossier, url="https://www.wikidata.org/wiki/Q123",
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id="Q123", retrieved_at=timezone.now(),
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        self.fact = Fact.objects.create(
            dossier=self.dossier, predicate="founded_year", value=1901,
            assertion_text="The club was founded in 1901.",
        )

    def test_facts_are_unverified_by_default_and_snapshots_are_serializable(self):
        self.assertEqual(self.fact.verification_state, Fact.Verification.UNVERIFIED)
        evidence = Evidence.objects.create(
            fact=self.fact, source=self.source, locator="P571",
            summary="Wikidata date of inception property.", role=Evidence.Role.SUPPORTS,
        )
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=1,
        )
        self.assertEqual(snapshot["club_id"], self.job.club_id)
        self.assertEqual(snapshot["club_name"], "Research FC")
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["sources"][0]["external_id"], "Q123")
        self.assertEqual(snapshot["sources"][0]["access_state"], "accessible")
        self.assertEqual(snapshot["facts"][0]["value"], 1901)
        self.assertEqual(snapshot["facts"][0]["verification_state"], "unverified")
        self.assertEqual(snapshot["facts"][0]["evidence"][0]["source_id"], self.source.pk)
        self.assertEqual(snapshot["facts"][0]["evidence"][0]["id"], evidence.pk)
        self.assertEqual(snapshot["facts"][0]["evidence"][0]["locator"], "P571")
        json.dumps(snapshot)

    def test_dossier_versions_are_separate_and_unique_per_job(self):
        version_two = FactDossier.objects.create(job=self.job, version=2)
        Fact.objects.create(
            dossier=version_two, predicate="stadium", value="Unknown",
            assertion_text="Stadium unknown.",
        )
        v1 = load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=1)
        v2 = load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=2)
        self.assertEqual(len(v1["facts"]), 1)
        self.assertEqual(v1["facts"][0]["predicate"], "founded_year")
        self.assertEqual(v2["facts"][0]["predicate"], "stadium")
        self.assertEqual(v2["sources"], [])
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FactDossier.objects.create(job=self.job, version=2)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FactDossier.objects.create(job=self.job, version=0)

    def test_another_owner_cannot_read_any_version(self):
        with self.assertRaises(FactDossier.DoesNotExist):
            load_fact_dossier(owner=self.other, job_id=self.job.pk, version=1)
        with self.assertRaises(FactDossier.DoesNotExist):
            load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=77)

    def test_reject_evidence_from_another_dossier(self):
        other = FactDossier.objects.create(job=self.job, version=2)
        other_source = SourceReference.objects.create(
            dossier=other, url="https://example.org/another",
            source_kind=SourceReference.Kind.OTHER,
            retrieved_at=timezone.now(),
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        with self.assertRaises(ValidationError):
            Evidence.objects.create(
                fact=self.fact, source=other_source,
                locator="other fact", role=Evidence.Role.SUPPORTS,
            )
        self.assertEqual(Evidence.objects.count(), 0)

    def test_verified_requires_saved_accessible_supporting_evidence(self):
        self.fact.verification_state = Fact.Verification.VERIFIED
        with self.assertRaises(ValidationError):
            self.fact.save()
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.verification_state, Fact.Verification.UNVERIFIED)

        self.source.access_state = SourceReference.Access.NOT_FOUND
        self.source.save(update_fields=["access_state"])
        Evidence.objects.create(
            fact=self.fact, source=self.source, locator="P571",
            role=Evidence.Role.SUPPORTS,
        )
        self.fact.verification_state = Fact.Verification.VERIFIED
        with self.assertRaises(ValidationError):
            self.fact.save()

        self.source.access_state = SourceReference.Access.ACCESSIBLE
        self.source.save(update_fields=["access_state"])
        self.fact.save()
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.verification_state, Fact.Verification.VERIFIED)

    def test_unrelated_sources_do_not_verify_fact(self):
        Evidence.objects.create(
            fact=self.fact, source=self.source, locator="Background",
            role=Evidence.Role.CONTEXT_ONLY,
        )
        self.fact.verification_state = Fact.Verification.VERIFIED
        with self.assertRaises(ValidationError):
            self.fact.save()
