"""P856 source suggestions: no automatic approval, network access or fiction."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.clubs.models import Club, Country, League
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceConfirmation,
    SourceReference,
)
from .official_source_candidates import (
    _league_matches, _one_p856, discover_official_site_candidates,
    import_official_site_candidates, proposed_site_for_context,
)
from .wikimedia_auto import AutoResearchError

CLUB_QID = "Q124007617"
LEAGUE_QID = "Q123789"
CLUB_URL = "https://www.wikidata.org/wiki/Special:EntityData/" + CLUB_QID + ".json"
CLUB_SITE = "https://sksturm.at/"
LEAGUE_SITE = "https://www.bundesliga.at/"


def claim(prop, value, kind="wikibase-entityid"):
    return {
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value", "property": prop,
            "datavalue": {"type": "string" if kind == "url" else kind,
                          "value": value},
        },
    }


def club_entity(*, site=CLUB_SITE, leagues=(LEAGUE_QID,)):
    claims = {"P118": [
        claim("P118", {"id": qid}) for qid in leagues
    ]}
    if site is not None:
        claims["P856"] = [claim("P856", site, kind="url")]
    return {"id": CLUB_QID, "claims": claims}


def league_entity(*, title="Austrian Football Bundesliga", site=LEAGUE_SITE,
                  country="Q40"):
    claims = {"P17": [claim("P17", {"id": country})]}
    if site is not None:
        claims["P856"] = [claim("P856", site, kind="url")]
    return {
        "id": LEAGUE_QID,
        "labels": {"en": {"value": title}},
        "claims": claims,
    }


class SourceCandidateSelectionTests(SimpleTestCase):
    def test_p856_accepts_one_https_url_no_conflicting_domains(self):
        self.assertEqual(_one_p856(club_entity()), CLUB_SITE)
        self.assertEqual(_one_p856(club_entity(site="https://sksturm.at")), CLUB_SITE)
        for website in (
            "http://sksturm.at/", "https://127.0.0.1/",
            "https://evil.example/", "https://user:secret@sksturm.at/",
            "https://sksturm.at:8443/",
            "https://sksturm.at/?token=abc",
            "https://sksturm.at/#hidden",
        ):
            with self.subTest(website=website):
                self.assertIsNone(_one_p856(club_entity(site=website)))
        entity = club_entity()
        entity["claims"]["P856"].append(claim(
            "P856", "https://anotherclub.org/", kind="url",
        ))
        self.assertIsNone(_one_p856(entity))

    def test_league_matching_conservative_and_no_generic_bundesliga(self):
        self.assertTrue(_league_matches(
            league_entity(), "Austrian Bundesliga",
        ))
        self.assertFalse(_league_matches(
            league_entity(title="German Bundesliga"), "Austrian Bundesliga",
        ))
        self.assertFalse(_league_matches(
            league_entity(title="Austrian 2. Bundesliga"), "Austrian Bundesliga",
        ))
        self.assertFalse(_league_matches(
            league_entity(), "Bundesliga",
        ))

    @patch("app.production.official_source_candidates._iso_country")
    @patch("app.production.official_source_candidates._entity")
    def test_only_p118_matching_league_and_country_yields_suggestions(
        self, get_entity, countries,
    ):
        get_entity.side_effect = lambda qid: (
            club_entity() if qid == CLUB_QID else league_entity()
        )
        countries.return_value = {"AT"}
        result = discover_official_site_candidates(
            club_qid=CLUB_QID, league_name="Austrian Bundesliga",
            country_code="AT",
        )
        self.assertEqual(result["club_url"], CLUB_SITE)
        self.assertEqual(result["league_url"], LEAGUE_SITE)
        self.assertEqual(result["league_qid"], LEAGUE_QID)
        self.assertEqual(get_entity.call_count, 2)
        countries.assert_called_once_with("Q40")

    @patch("app.production.official_source_candidates._iso_country")
    @patch("app.production.official_source_candidates._entity")
    def test_wrong_country_never_yields_league_site(self, get_entity, countries):
        get_entity.side_effect = lambda qid: (
            club_entity() if qid == CLUB_QID else league_entity()
        )
        countries.return_value = {"DE"}
        result = discover_official_site_candidates(
            club_qid=CLUB_QID, league_name="Austrian Bundesliga",
            country_code="AT",
        )
        self.assertEqual(result["club_url"], CLUB_SITE)
        self.assertIsNone(result["league_url"])

    @patch("app.production.official_source_candidates._iso_country")
    @patch("app.production.official_source_candidates._entity")
    def test_missing_p856_does_not_fabricate_url(self, get_entity, countries):
        get_entity.side_effect = lambda qid: (
            club_entity(site=None) if qid == CLUB_QID
            else league_entity(site=None)
        )
        countries.return_value = {"AT"}
        result = discover_official_site_candidates(
            club_qid=CLUB_QID, league_name="Austrian Bundesliga",
            country_code="AT",
        )
        self.assertIsNone(result["club_url"])
        self.assertIsNone(result["league_url"])

    @patch("app.production.official_source_candidates._iso_country")
    @patch("app.production.official_source_candidates._entity")
    def test_conflicting_p118_league_candidates_cannot_be_selected(
        self, get_entity, countries,
    ):
        new_qid = "Q99910"
        def data(qid):
            if qid == CLUB_QID:
                return club_entity(leagues=(LEAGUE_QID, new_qid))
            result = league_entity()
            result["id"] = qid
            return result
        get_entity.side_effect = data
        countries.return_value = {"AT"}
        result = discover_official_site_candidates(
            club_qid=CLUB_QID, league_name="Austrian Bundesliga",
            country_code="AT",
        )
        self.assertIsNone(result["league_url"])
        self.assertEqual(result["club_url"], CLUB_SITE)

    def test_reject_bad_qids_and_country_before_network(self):
        for kwargs in (
            {"club_qid": "Q1; DROP TABLE"},
            {"club_qid": "q1"},
            {"country_code": "at"},
            {"country_code": "GER"},
            {"league_name": ""},
        ):
            data = {
                "club_qid": CLUB_QID,
                "league_name": "Austrian Bundesliga",
                "country_code": "AT",
            }
            data.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaisesMessage(
                AutoResearchError, "invalid_request",
            ):
                discover_official_site_candidates(**data)


class SourceCandidateImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="p856-owner@example.org", password="Only-test-password-2026",
        )
        self.other = User.objects.create_user(
            email="p856-other@example.org", password="Only-test-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            club_name="Sturm Graz", country_code="AT",
            league_name="Austrian Bundesliga", title="Full Research Test",
        )
        self.before = FactDossier.objects.create(job=self.job, version=4)
        SourceReference.objects.create(
            dossier=self.before, source_kind="wikidata",
            external_id=CLUB_QID, url=CLUB_URL,
            title="[auto] SK Sturm Graz",
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        Fact.objects.create(
            dossier=self.before, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )

    def found(self):
        return {
            "club_qid": CLUB_QID, "club_url": CLUB_SITE,
            "league_qid": LEAGUE_QID, "league_url": LEAGUE_SITE,
        }

    def scan(self, **kwargs):
        args = {
            "owner": self.owner, "job_id": self.job.pk,
            "expected_version": 4,
        }
        args.update(kwargs)
        return import_official_site_candidates(**args)

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_persists_only_unreviewed_candidate_urls_with_wikidata_evidence(
        self, discover,
    ):
        discover.return_value = self.found()
        latest = self.scan()
        self.assertEqual(latest.version, 5)
        self.assertEqual(latest.facts.count(), 3)
        self.assertEqual(latest.sources.count(), 3)
        self.assertEqual(self.before.sources.count(), 1)
        self.assertEqual(self.before.facts.count(), 1)
        self.assertFalse(SourceConfirmation.objects.exists())
        proposals = latest.facts.exclude(predicate="founded_year")
        self.assertEqual(set(proposals.values_list("predicate", flat=True)), {
            "official_club_site_candidate", "official_league_site_candidate",
        })
        self.assertTrue(all(
            fact.verification_state == "unverified" for fact in proposals
        ))
        self.assertTrue(all(fact.evidence.count() == 1 for fact in proposals))
        self.assertTrue(all(
            fact.evidence.get().role == Evidence.Role.UNKNOWN
            for fact in proposals
        ))
        self.assertEqual(
            proposed_site_for_context(latest, "club")["url"], CLUB_SITE,
        )
        self.assertEqual(
            proposed_site_for_context(latest, "league")["url"], LEAGUE_SITE,
        )
        self.assertFalse(
            latest.sources.filter(source_kind="club_official").exists()
        )
        discover.assert_called_once_with(
            club_qid=CLUB_QID, league_name="Austrian Bundesliga",
            country_code="AT",
        )

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_empty_proposal_is_recorded_once_without_fabricating_domains(self, discover):
        discover.return_value = {
            "club_qid": CLUB_QID, "club_url": None,
            "league_qid": None, "league_url": None,
        }
        latest = self.scan()
        self.assertEqual(latest.facts.count(), 1)
        self.assertIsNone(proposed_site_for_context(latest, "club"))
        self.assertIsNone(proposed_site_for_context(latest, "league"))
        self.assertEqual(latest.sources.count(), 2)
        self.assertEqual(self.scan().pk, latest.pk)
        discover.assert_called_once()

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_idempotent_retry_never_queries_wikidata_again(self, discover):
        discover.return_value = self.found()
        first = self.scan()
        again = self.scan(expected_version=4)
        self.assertEqual(first.pk, again.pk)
        discover.assert_called_once()
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_foreign_user_and_stale_form_blocked_before_external_call(self, discover):
        for change, code in (
            ({"owner": self.other}, "not_authorized"),
            ({"expected_version": 3}, "stale_dossier"),
            ({"job_id": True}, "invalid_request"),
        ):
            with self.subTest(change=change), self.assertRaisesMessage(
                AutoResearchError, code,
            ):
                self.scan(**change)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_failure_keeps_original_dossier_intact(self, discover):
        discover.side_effect = AutoResearchError("network_error")
        with self.assertRaisesMessage(AutoResearchError, "network_error"):
            self.scan()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertFalse(SourceConfirmation.objects.exists())

    @patch("app.production.official_source_candidates.discover_official_site_candidates")
    def test_malformed_stored_proposal_never_prefills_form(self, discover):
        discover.return_value = self.found()
        dossier = self.scan()
        proposal = dossier.facts.get(predicate="official_club_site_candidate")
        proposal.value = {
            "context": "club", "url": "https://127.0.0.1/",
            "wikidata_qid": CLUB_QID,
        }
        proposal.save(update_fields=["value"])
        self.assertIsNone(proposed_site_for_context(dossier, "club"))
