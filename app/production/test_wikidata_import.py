"""No-network DB tests for the explicitly confirmed Wikidata source importer."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.clubs.models import Club, Country, League

from .dossiers import load_fact_dossier
from .models import Fact, FactDossier, ProductionJob, SourceReference
from .wikidata import WikidataLookupError
from .wikidata_import import import_wikidata_source


def profile(qid="Q123", *, title="Example FC"):
    return {
        "provider": "wikidata",
        "entity_id": qid,
        "label_en": title,
        "description_en": "association football club",
        "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
        "wikipedia_url_en": (f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else None),
        "fetched_at": "2026-11-11T02:00:00+00:00",
    }


class WikidataSourceImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="research-owner@example.com", password="test-passphrase-2026",
        )
        self.other = User.objects.create_user(
            email="research-other@example.com", password="other-passphrase-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Premier League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Example Club Story",
            country_code="GB", league_name="Premier League", club_name="Example FC",
        )

    def import_entity(self, **kwargs):
        args = {
            "owner": self.owner, "job_id": self.job.pk,
            "qid": "Q123", "identity_confirmed": True,
        }
        args.update(kwargs)
        return import_wikidata_source(**args)

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_explicit_import_saves_only_source_in_dossier(self, fetch):
        fetch.return_value = profile()
        dossier = self.import_entity()
        fetch.assert_called_once_with("Q123")
        self.assertEqual(dossier.version, 1)
        self.assertEqual(dossier.job.club, self.job.club)
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=1,
        )
        self.assertEqual(snapshot["facts"], [])
        self.assertEqual(Fact.objects.count(), 0)
        self.assertEqual(snapshot["sources"][0]["title"], "Example FC")
        self.assertEqual(snapshot["sources"][0]["source_kind"], "wikidata")
        self.assertEqual(snapshot["sources"][0]["external_id"], "Q123")
        self.assertEqual(snapshot["sources"][0]["access_state"], "accessible")
        self.assertEqual(
            snapshot["sources"][0]["url"],
            "https://www.wikidata.org/wiki/Special:EntityData/Q123.json",
        )
        self.assertIn("2026-11-11T02:00:00", snapshot["sources"][0]["retrieved_at"])

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_same_entity_reuses_latest_version_without_network(self, fetch):
        fetch.return_value = profile()
        first = self.import_entity()
        second = self.import_entity()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)
        fetch.assert_called_once_with("Q123")

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_new_confirmed_qid_creates_new_version_and_keeps_old(self, fetch):
        fetch.side_effect = [profile(), profile("Q456", title="Other FC")]
        first = self.import_entity()
        second = self.import_entity(qid="Q456")
        self.assertEqual((first.version, second.version), (1, 2))
        self.assertEqual(
            list(first.sources.values_list("external_id", flat=True)), ["Q123"],
        )
        self.assertEqual(
            list(second.sources.values_list("external_id", flat=True)), ["Q123", "Q456"],
        )
        self.assertEqual(SourceReference.objects.count(), 2)

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_permission_confirmation_and_bad_id_fail_before_network(self, fetch):
        cases = [
            {"owner": self.other},
            {"identity_confirmed": False},
            {"identity_confirmed": 1},
            {"qid": "Q0"},
            {"qid": "https://example.org"},
        ]
        for options in cases:
            with self.subTest(options=options):
                with self.assertRaises((ValueError, ProductionJob.DoesNotExist)):
                    self.import_entity(**options)
        fetch.assert_not_called()
        self.assertFalse(FactDossier.objects.exists())

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_network_errors_leave_no_partial_version(self, fetch):
        fetch.side_effect = WikidataLookupError("network_error")
        with self.assertRaises(WikidataLookupError) as raised:
            self.import_entity()
        self.assertEqual(raised.exception.code, "network_error")
        self.assertFalse(FactDossier.objects.exists())
        self.assertFalse(SourceReference.objects.exists())

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_untrusted_or_malformed_profile_is_rejected_atomically(self, fetch):
        for replacement in (
            {"entity_id": "Q456"},
            {"source_url": "https://example.org/redirect"},
            {"provider": "other"},
            {"fetched_at": "not-a-date"},
            {"fetched_at": "2026-11-11T02:00:00"},
            {"label_en": "A" * 251},
        ):
            with self.subTest(replacement=replacement):
                fetch.return_value = {**profile(), **replacement}
                with self.assertRaises(WikidataLookupError) as raised:
                    self.import_entity()
                self.assertEqual(raised.exception.code, "invalid_response")
                self.assertFalse(FactDossier.objects.exists())

    @patch("app.production.wikidata_import.fetch_wikidata_profile")
    def test_missing_english_label_does_not_invent_club_name(self, fetch):
        fetch.return_value = profile(title=None)
        dossier = self.import_entity()
        self.assertEqual(dossier.sources.get().title, "Wikidata entity Q123")
        self.assertFalse(Fact.objects.exists())
