"""Wikidata P54 candidate selection, persistence and safe ownership tests."""
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.clubs.models import Club, Country, League
from .models import Fact, FactDossier, ProductionJob, SourceReference
from .script_draft import ScriptDraftError, build_script_draft
from .wikimedia_auto import AutoResearchError
from .wikimedia_players import (
    _parse, _query, discover_wikidata_players, import_wikidata_player_candidates,
)

CLUB_QID = "Q124007617"
CLUB_URL = (
    "https://www.wikidata.org/wiki/Special:EntityData/"
    + CLUB_QID + ".json"
)


def row(qid="Q45678", label="Mario Haas", links=36):
    return {
        "person": {
            "type": "uri", "value": "http://www.wikidata.org/entity/" + qid,
        },
        "name": {
            "type": "literal", "xml:lang": "en", "value": label,
        },
        "sitelinks": {
            "type": "literal", "value": str(links),
            "datatype": "http://www.w3.org/2001/XMLSchema#integer",
        },
    }


def sample_people():
    return [
        {"person_qid": "Q45678", "name": "Mario Haas", "sitelinks": 36},
        {"person_qid": "Q98765", "name": "Ivica Vastić", "sitelinks": 28},
    ]


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


class WikimediaPlayersQueryTests(SimpleTestCase):
    def test_queries_only_one_specific_club_with_strict_bound(self):
        query = _query(CLUB_QID)
        self.assertIn("wdt:P54 wd:" + CLUB_QID, query)
        self.assertIn("wdt:P31 wd:Q5", query)
        self.assertIn("wdt:P106 wd:Q937857", query)
        self.assertIn("LIMIT 12", query)
        self.assertNotIn("SERVICE wikibase:label", query)
        for bad in ("", "q1", "Q0", "Q4; DROP ALL", 123, None):
            with self.subTest(bad=bad), self.assertRaisesMessage(
                AutoResearchError, "invalid_club_qid"
            ):
                _query(bad)

    def test_results_are_bounded_deduplicated_and_sorted(self):
        answer = {"results": {"bindings": [
            row("Q98765", "Ivica Vastić", 28),
            row(), row(), row("Q12345", "Another Player", 12),
        ]}}
        self.assertEqual(_parse(answer), sample_people() + [
            {"person_qid": "Q12345", "name": "Another Player", "sitelinks": 12},
        ])

    def test_bad_names_ids_or_sitelinks_are_ignored(self):
        bad_script = row(label="<script>alert(1)</script>")
        bad_qid = row(qid="Q0")
        low_coverage = row(links=1)
        bad_url = row()
        bad_url["person"]["value"] = "https://evil.example.org/entity/Q123"
        wrong_language = row()
        wrong_language["name"]["xml:lang"] = "de"
        result = _parse({"results": {"bindings": [
            bad_script, bad_qid, low_coverage, bad_url, wrong_language,
        ]}})
        self.assertEqual(result, [])

    def test_malformed_or_conflicting_responses_fail_closed(self):
        for value in (None, [], {}, {"results": {}},
                      {"results": {"bindings": "oops"}},
                      {"results": {"bindings": [{}] * 13}}):
            with self.subTest(value=value), self.assertRaisesMessage(
                AutoResearchError, "invalid_response"
            ):
                _parse(value)
        with self.assertRaisesMessage(AutoResearchError, "conflicting_candidate"):
            _parse({"results": {"bindings": [
                row("Q12345", "One Person"),
                row("Q12345", "Two People"),
            ]}})

    @patch("app.production.wikimedia_players.build_opener")
    def test_one_fixed_query_uses_get_timeout_and_no_redirects(self, opener):
        import json
        opener.return_value.open.return_value = FakeResponse(
            json.dumps({"results": {"bindings": [
                row(), row("Q98765", "Ivica Vastić", 28),
            ]}}).encode("utf-8")
        )
        found = discover_wikidata_players(club_qid=CLUB_QID)
        self.assertEqual(found, sample_people())
        opener.assert_called_once()
        sent = opener.return_value.open.call_args
        request = sent.args[0]
        self.assertEqual(urlsplit(request.full_url).netloc, "query.wikidata.org")
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(params["format"], ["json"])
        self.assertIn("wdt:P54 wd:" + CLUB_QID, params["query"][0])
        self.assertEqual(sent.kwargs["timeout"], 8)
        self.assertIsNone(opener.call_args.args[0].redirect_request(
            None, None, 302, None, {}, "https://untrusted.example/",
        ))

    @patch("app.production.wikimedia_players.build_opener")
    def test_network_errors_and_large_responses_do_not_yield_candidates(self, opener):
        opener.return_value.open.side_effect = URLError("do not disclose upstream")
        with self.assertRaisesMessage(AutoResearchError, "network_error"):
            discover_wikidata_players(club_qid=CLUB_QID)
        opener.return_value.open.side_effect = HTTPError(
            "https://query.wikidata.org/sparql", 429, "slow", {}, None,
        )
        with self.assertRaisesMessage(AutoResearchError, "service_busy"):
            discover_wikidata_players(club_qid=CLUB_QID)
        opener.return_value.open.side_effect = None
        opener.return_value.open.return_value = FakeResponse(b"x" * 128001)
        with self.assertRaisesMessage(AutoResearchError, "response_too_large"):
            discover_wikidata_players(club_qid=CLUB_QID)

    @patch("app.production.wikimedia_players.build_opener")
    def test_empty_query_result_creates_no_names(self, opener):
        import json
        opener.return_value.open.return_value = FakeResponse(
            json.dumps({"results": {"bindings": []}}).encode("utf-8")
        )
        with self.assertRaisesMessage(AutoResearchError, "no_people_candidates"):
            discover_wikidata_players(club_qid=CLUB_QID)


class WikidataPlayerImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="player-candidate-owner@example.org",
            password="Local-fixture-password-2026",
        )
        self.other = User.objects.create_user(
            email="player-candidate-other@example.org",
            password="Local-fixture-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Bundesliga", club_name="Sturm Graz",
            title="The Story of Sturm Graz",
        )
        self.initial = FactDossier.objects.create(job=self.job, version=4)
        SourceReference.objects.create(
            dossier=self.initial, source_kind="wikidata",
            url=CLUB_URL, title="[auto] SK Sturm Graz",
            external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        Fact.objects.create(
            dossier=self.initial, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )

    def run_import(self, **kwargs):
        args = {
            "owner": self.owner, "job_id": self.job.pk, "expected_version": 4,
        }
        args.update(kwargs)
        return import_wikidata_player_candidates(**args)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_persists_two_people_with_source_evidence_but_not_legend_status(self, fetch):
        fetch.return_value = sample_people()
        latest = self.run_import()
        self.assertEqual(latest.version, 5)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(self.initial.facts.count(), 1)
        self.assertEqual(latest.facts.count(), 3)
        self.assertEqual(latest.sources.count(), 4)
        facts = list(latest.facts.filter(
            predicate="club_player_candidate",
        ).order_by("pk"))
        self.assertEqual([f.value["name"] for f in facts], [
            "Mario Haas", "Ivica Vastić",
        ])
        self.assertTrue(all(f.verification_state == "unverified" for f in facts))
        self.assertTrue(all(f.evidence.count() == 1 for f in facts))
        self.assertTrue(all(
            f.evidence.first().role == "unknown"
            for f in facts
        ))
        self.assertTrue(all(
            f.evidence.first().source.url.startswith(
                "https://www.wikidata.org/wiki/Special:EntityData/"
            ) for f in facts
        ))
        self.assertEqual(
            latest.sources.filter(external_id="auto-p54:" + CLUB_QID).count(),
            1,
        )
        self.assertFalse(latest.facts.filter(
            verification_state="verified",
        ).exists())
        fetch.assert_called_once_with(club_qid=CLUB_QID)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_retry_does_not_repeat_network_or_fork(self, fetch):
        fetch.return_value = sample_people()
        first = self.run_import()
        second = self.run_import(expected_version=4)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_stale_and_foreign_owner_denied_before_network(self, fetch):
        for change, code in (
            ({"owner": self.other}, "not_authorized"),
            ({"expected_version": 3}, "stale_dossier"),
            ({"job_id": True}, "invalid_request"),
        ):
            with self.subTest(change=change), self.assertRaisesMessage(
                AutoResearchError, code,
            ):
                self.run_import(**change)
        fetch.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_no_auto_club_qid_or_untrusted_source_does_not_call_network(self, fetch):
        src = self.initial.sources.get()
        src.title = "Manual source"
        src.save(update_fields=["title"])
        with self.assertRaisesMessage(AutoResearchError, "no_auto_research"):
            self.run_import()
        src.title = "[auto] SK Sturm Graz"
        src.url = "https://example.org/club"
        src.save(update_fields=["title", "url"])
        with self.assertRaisesMessage(AutoResearchError, "invalid_club_source"):
            self.run_import()
        fetch.assert_not_called()

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_wikimedia_failure_is_atomic(self, fetch):
        fetch.side_effect = AutoResearchError("service_busy")
        with self.assertRaisesMessage(AutoResearchError, "service_busy"):
            self.run_import()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(self.initial.facts.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_person_is_unreviewed_and_cannot_enter_factual_script(self, fetch):
        fetch.return_value = sample_people()
        latest = self.run_import()
        from .dossiers import load_fact_dossier
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=latest.version,
        )
        with self.assertRaisesMessage(ScriptDraftError, "no_reviewed_facts"):
            build_script_draft(
                snapshot, club_name=self.job.club_name,
                selected_title=self.job.title,
            )
