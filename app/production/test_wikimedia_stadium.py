"""Free automatic P115 stadium enrichment, all HTTP mocked."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League

from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference
from .wikimedia_auto import AutoResearchError
from .wikimedia_stadium import (
    _venue_qid, discover_wikidata_stadium, enrich_wikimedia_stadium,
)


CLUB_QID = "Q124007617"
STADIUM_QID = "Q696491"
CLUB_URL = (
    "https://www.wikidata.org/wiki/Special:EntityData/Q124007617.json"
)
VENUE_URL = "https://www.wikidata.org/wiki/Special:EntityData/Q696491.json"


def venue_claim(qid=STADIUM_QID, *, rank="normal", qualifiers=None):
    return {
        "rank": rank,
        "mainsnak": {
            "property": "P115", "snaktype": "value",
            "datavalue": {"value": {"id": qid}},
        },
        "qualifiers": qualifiers or {},
    }


def qualified_year(year):
    return [{"datavalue": {"value": {
        "time": f"+{year}-01-01T00:00:00Z", "precision": 11,
    }}}]


def sample_venue():
    return {
        "club_qid": CLUB_QID,
        "venue_qid": STADIUM_QID,
        "stadium_name": "Merkur Arena",
        "club_url": CLUB_URL,
        "venue_url": VENUE_URL,
        "retrieved_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
    }


class StadiumExtractionTests(SimpleTestCase):
    def test_unique_current_home_venue_and_preferred_rank(self):
        club = {"claims": {"P115": [venue_claim()]}}
        self.assertEqual(_venue_qid(club), STADIUM_QID)
        club["claims"]["P115"] = [
            venue_claim("Q333333", rank="normal"),
            venue_claim(rank="preferred"),
        ]
        self.assertEqual(_venue_qid(club), STADIUM_QID)

    def test_multiple_current_venues_fail_closed(self):
        club = {"claims": {"P115": [
            venue_claim(), venue_claim("Q333333"),
        ]}}
        with self.assertRaisesMessage(AutoResearchError, "ambiguous_stadium"):
            _venue_qid(club)

    def test_absent_deprecated_past_or_future_home_venues_not_inferred(self):
        year = datetime.now(timezone.utc).year
        for entries in (
            [], [venue_claim(rank="deprecated")],
            [venue_claim(qualifiers={"P582": qualified_year(year - 1)})],
            [venue_claim(qualifiers={"P580": qualified_year(year + 1)})],
            [venue_claim(qualifiers={"P582": [{"datavalue": {}}]})],
            [venue_claim(qualifiers={"P580": qualified_year(year)})],
        ):
            with self.subTest(entries=entries), self.assertRaisesMessage(
                AutoResearchError, "no_stadium_candidate"
            ):
                _venue_qid({"claims": {"P115": entries}})

    @patch("app.production.wikimedia_stadium._entity")
    def test_structured_stadium_label_has_two_traceable_wikidata_item_urls(
        self, entity,
    ):
        entity.side_effect = [
            {"id": CLUB_QID, "claims": {"P115": [venue_claim()]}},
            {"id": STADIUM_QID, "labels": {
                "en": {"value": "Merkur Arena"},
            }},
        ]
        found = discover_wikidata_stadium(club_qid=CLUB_QID)
        self.assertEqual(found["club_url"], CLUB_URL)
        self.assertEqual(found["venue_url"], VENUE_URL)
        self.assertEqual(found["stadium_name"], "Merkur Arena")
        self.assertEqual(entity.call_count, 2)
        entity.assert_any_call(CLUB_QID)
        entity.assert_any_call(STADIUM_QID)

    @patch("app.production.wikimedia_stadium._entity")
    def test_untrusted_html_and_missing_english_label_are_not_facts(self, entity):
        for bad in ("", "<script>alert(1)</script>", "A" * 161, "A\nB"):
            with self.subTest(bad=bad):
                entity.side_effect = [
                    {"id": CLUB_QID, "claims": {"P115": [venue_claim()]}},
                    {"id": STADIUM_QID, "labels": {
                        "en": {"value": bad},
                    }},
                ]
                with self.assertRaisesMessage(
                    AutoResearchError, "missing_stadium_label"
                ):
                    discover_wikidata_stadium(club_qid=CLUB_QID)
        entity.assert_any_call(CLUB_QID)

    @patch("app.production.wikimedia_stadium._entity")
    def test_invalid_user_qid_never_triggers_request(self, entity):
        for bad in ("", "q123", "Q0", "https://example.org", "Q123/../", None):
            with self.subTest(bad=bad), self.assertRaisesMessage(
                AutoResearchError, "invalid_club_qid"
            ):
                discover_wikidata_stadium(club_qid=bad)
        entity.assert_not_called()


class StadiumImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="stadium-automatic-owner@example.org",
            password="Temporary-test-123456789",
        )
        self.other = User.objects.create_user(
            email="stadium-automatic-other@example.org",
            password="Temporary-test-123456789",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="A Club Story",
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=3)
        self.club_source = SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url=CLUB_URL, title="[auto] SK Sturm Graz",
            external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        self.year_fact = Fact.objects.create(
            dossier=self.dossier, predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
            verification_state="unverified",
        )
        Evidence.objects.create(
            fact=self.year_fact, source=self.club_source, role="unknown",
            locator="Wikidata inception (P571)",
            summary="Automatically imported founding year 1909.",
        )

    def enrich(self, **kwargs):
        arguments = dict(
            owner=self.owner, job_id=self.job.pk, expected_version=3,
        )
        arguments.update(kwargs)
        return enrich_wikimedia_stadium(**arguments)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_real_existing_sturm_dossier_gains_stadium_in_version_four(
        self, discover,
    ):
        discover.return_value = sample_venue()
        updated = self.enrich()
        self.assertEqual(updated.version, 4)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(updated.sources.count(), 2)
        self.assertEqual(updated.facts.count(), 2)
        self.assertEqual(self.dossier.facts.count(), 1)
        self.assertEqual(self.dossier.sources.count(), 1)
        candidate = updated.facts.get(predicate="stadium_name")
        self.assertEqual(candidate.value, "Merkur Arena")
        self.assertEqual(
            candidate.assertion_text,
            "The club's home stadium is Merkur Arena.",
        )
        self.assertEqual(candidate.verification_state, "unverified")
        self.assertEqual(
            list(candidate.evidence.order_by("source_id").values_list(
                "role", flat=True,
            )), ["unknown", "unknown"],
        )
        self.assertEqual(
            set(candidate.evidence.values_list("source__url", flat=True)),
            {CLUB_URL, VENUE_URL},
        )
        self.assertEqual(updated.facts.get(predicate="founded_year").value, 1909)
        self.assertFalse(Fact.objects.filter(
            verification_state="verified",
        ).exists())
        discover.assert_called_once_with(club_qid=CLUB_QID)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_retry_after_success_creates_no_duplication_or_network(self, discover):
        discover.return_value = sample_venue()
        first = self.enrich()
        second = self.enrich()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(first.facts.filter(predicate="stadium_name").count(), 1)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_other_user_or_stale_version_denied_before_network(self, discover):
        for args, code in (
            ({"owner": self.other}, "not_authorized"),
            ({"expected_version": 2}, "stale_dossier"),
            ({"job_id": True}, "invalid_request"),
        ):
            with self.subTest(args=args), self.assertRaisesMessage(
                AutoResearchError, code,
            ):
                self.enrich(**args)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_ambiguous_stadium_does_not_mutate_history(self, discover):
        discover.side_effect = AutoResearchError("ambiguous_stadium")
        with self.assertRaisesMessage(AutoResearchError, "ambiguous_stadium"):
            self.enrich()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(self.dossier.facts.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_manual_wikidata_source_is_not_automatic_club_identity(self, discover):
        self.club_source.title = "Manually entered Wikidata"
        self.club_source.save(update_fields=["title"])
        with self.assertRaisesMessage(AutoResearchError, "no_auto_research"):
            self.enrich()
        discover.assert_not_called()

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_tampered_club_source_is_not_used_to_fetch_arbitrary_url(self, discover):
        self.club_source.url = "https://untrusted.example.org"
        self.club_source.save(update_fields=["url"])
        with self.assertRaisesMessage(AutoResearchError, "invalid_club_source"):
            self.enrich()
        discover.assert_not_called()

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_preexisting_stadium_fact_is_not_duplicated(self, discover):
        Fact.objects.create(
            dossier=self.dossier, predicate="stadium_name",
            value="A Different Stadium", assertion_text="Unconfirmed stadium.",
        )
        self.assertEqual(self.enrich().pk, self.dossier.pk)
        discover.assert_not_called()
