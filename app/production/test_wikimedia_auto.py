"""Offline tests for real free Wikimedia discovery and owner-scoped fact import."""
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.clubs.models import Club, Country, League
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference
from .wikimedia_auto import (
    AutoResearchError, _read_json, discover_free_club_research,
    import_free_club_research,
)


def claim(prop, value, *, kind="wikibase-entityid", rank="normal"):
    return {
        "rank": rank,
        "mainsnak": {
            "property": prop, "snaktype": "value",
            "datatype": kind, "datavalue": {"type": kind, "value": value},
        },
    }


def club_entity(qid="Q124007617", *, country="Q40", founding_year=1909):
    claims = {
        "P31": [claim("P31", {"id": "Q476028"})],
        "P17": [claim("P17", {"id": country})],
    }
    if founding_year is not None:
        claims["P571"] = [claim("P571", {
            "time": f"+{founding_year}-05-01T00:00:00Z",
            "precision": 11, "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
        }, kind="time")]
    return {
        "id": qid,
        "labels": {"en": {"value": "SK Sturm Graz"}},
        "claims": claims,
        "sitelinks": {"enwiki": {"title": "SK Sturm Graz"}},
    }


def fake_fetch(url, *, limit=256_000, duplicate=False, mismatch=False,
               no_wikipedia=False):
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    action = query.get("action", [None])[0]
    if action == "wbsearchentities":
        rows = [
            {"id": "Q124007617", "label": "SK Sturm Graz",
             "description": "association football club in Austria"},
            {"id": "Q123456", "label": "Some Other Club"},
        ]
        if duplicate:
            rows.append({"id": "Q987654", "label": "Sturm Graz"})
        return {"search": rows}
    if "Special:EntityData/" in parsed.path:
        qid = parsed.path.split("/")[-1].replace(".json", "")
        return {"entities": {qid: club_entity(qid=qid)}}
    if action == "wbgetclaims":
        country = "DE" if mismatch else "AT"
        return {"claims": {"P297": [claim("P297", country, kind="string")]}}
    if action == "query" and parsed.hostname == "en.wikipedia.org":
        if no_wikipedia:
            raise AutoResearchError("network_error")
        return {"query": {"pages": {"12345": {
            "pageid": 12345, "ns": 0, "title": "SK Sturm Graz",
            "extract": "SK Sturm Graz is a football club founded in 1909.",
        }}}}
    raise AssertionError("Unexpected request: " + url)


class WikimediaDiscoveryTests(SimpleTestCase):
    @patch("app.production.wikimedia_auto._read_json", side_effect=fake_fetch)
    def test_sturm_graz_selected_from_search_without_hardcoded_club_id(self, fetch):
        data = discover_free_club_research(
            club_name="Sturm Graz", country_code="AT",
        )
        self.assertEqual(data["qid"], "Q124007617")
        self.assertEqual(data["founded_year_candidate"], 1909)
        self.assertEqual(data["label"], "SK Sturm Graz")
        self.assertEqual(
            data["wikipedia_url"], "https://en.wikipedia.org/wiki/SK_Sturm_Graz",
        )
        self.assertTrue(data["wikipedia_intro_mentions_year"])
        self.assertEqual(fetch.call_count, 4)
        self.assertTrue(all(
            "https://" in call.args[0] for call in fetch.call_args_list
        ))

    @patch("app.production.wikimedia_auto._read_json")
    def test_wrong_country_cannot_be_attached_to_football_job(self, fetch):
        fetch.side_effect = lambda u, **kw: fake_fetch(u, mismatch=True, **kw)
        with self.assertRaisesMessage(AutoResearchError, "no_confident_match"):
            discover_free_club_research(
                club_name="Sturm Graz", country_code="AT",
            )

    @patch("app.production.wikimedia_auto._read_json")
    def test_multiple_matching_clubs_are_ambiguous_not_auto_chosen(self, fetch):
        fetch.side_effect = lambda u, **kw: fake_fetch(u, duplicate=True, **kw)
        with self.assertRaisesMessage(AutoResearchError, "ambiguous_entity"):
            discover_free_club_research(
                club_name="Sturm Graz", country_code="AT",
            )

    @patch("app.production.wikimedia_auto._read_json")
    def test_article_unavailable_still_keeps_only_unverified_wikidata(self, fetch):
        fetch.side_effect = lambda u, **kw: fake_fetch(u, no_wikipedia=True, **kw)
        result = discover_free_club_research(
            club_name="Sturm Graz", country_code="AT",
        )
        self.assertEqual(result["founded_year_candidate"], 1909)
        self.assertIsNone(result["wikipedia_url"])
        self.assertFalse(result["wikipedia_intro_mentions_year"])

    @patch("app.production.wikimedia_auto._read_json")
    def test_no_unambiguous_founding_year_means_no_year_claim(self, fetch):
        def runner(url, **kwargs):
            result = fake_fetch(url, **kwargs)
            if "Special:EntityData/" in url:
                qid = next(iter(result["entities"]))
                result["entities"][qid]["claims"]["P571"].append(
                    claim("P571", {
                        "time": "+1912-03-31T00:00:00Z",
                        "precision": 11,
                    }, kind="time"),
                )
            return result
        fetch.side_effect = runner
        result = discover_free_club_research(
            club_name="Sturm Graz", country_code="AT",
        )
        self.assertIsNone(result["founded_year_candidate"])

    @patch("app.production.wikimedia_auto._read_json")
    def test_fake_club_class_and_invalid_search_result_rejected(self, fetch):
        def runner(url, **kwargs):
            result = fake_fetch(url, **kwargs)
            if "Special:EntityData/" in url:
                qid = next(iter(result["entities"]))
                result["entities"][qid]["claims"]["P31"] = [
                    claim("P31", {"id": "Q5"}),
                ]
            return result
        fetch.side_effect = runner
        with self.assertRaisesMessage(AutoResearchError, "no_confident_match"):
            discover_free_club_research(
                club_name="Sturm Graz", country_code="AT",
            )

    @patch("app.production.wikimedia_auto.build_opener")
    def test_client_does_not_follow_redirects_or_accept_non_wiki_hosts(self, opener):
        for url in (
            "http://www.wikidata.org/w/api.php",
            "https://127.0.0.1/w/api.php",
            "https://localhost/w/api.php",
            "https://example.org/w/api.php",
            "https://user:pass@www.wikidata.org/w/api.php",
        ):
            with self.subTest(url=url), self.assertRaisesMessage(
                AutoResearchError, "invalid_endpoint"
            ):
                _read_json(url)
        opener.assert_not_called()
        self.assertEqual(
            _read_json.__module__, "app.production.wikimedia_auto",
        )

    @patch("app.production.wikimedia_auto.build_opener")
    def test_upstream_redirect_error_is_not_followed(self, opener):
        opener.return_value.open.side_effect = HTTPError(
            "https://www.wikidata.org/w/api.php", 302, "redirect", {}, None,
        )
        with self.assertRaisesMessage(AutoResearchError, "upstream_error"):
            _read_json("https://www.wikidata.org/w/api.php")
        redirect_handler = opener.call_args.args[0]
        self.assertIsNone(redirect_handler.redirect_request(
            None, None, 302, None, {}, "https://evil.example.org/",
        ))

    def test_bad_club_name_or_country_rejected_before_search(self):
        for club in ("", "<script>", "A" * 200):
            with self.subTest(club=club), self.assertRaises(AutoResearchError):
                discover_free_club_research(club_name=club, country_code="AT")
        for country in ("", "AAA", "at", "AT\n", None):
            with self.subTest(country=country), self.assertRaisesMessage(
                AutoResearchError, "invalid_country"
            ):
                discover_free_club_research(
                    club_name="Sturm Graz", country_code=country,
                )


class WikimediaResearchImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="wikimedia-auto-owner@example.org",
            password="Offline-test-password-123456",
        )
        self.other = User.objects.create_user(
            email="wikimedia-auto-other@example.org",
            password="Offline-test-password-123456",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
            title="An Austrian Football Story",
        )
        self.snapshot = FactDossier.objects.create(job=self.job, version=2)

    def imported(self, **kwargs):
        args = {"owner": self.owner, "job_id": self.job.pk, "expected_version": 2}
        args.update(kwargs)
        return import_free_club_research(**args)

    def discovery(self):
        return {
            "qid": "Q124007617", "label": "SK Sturm Graz",
            "wikidata_url":
                "https://www.wikidata.org/wiki/Special:EntityData/Q124007617.json",
            "founded_year_candidate": 1909,
            "wikipedia_url": "https://en.wikipedia.org/wiki/SK_Sturm_Graz",
            "wikipedia_intro_mentions_year": True,
            "retrieved_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
        }

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_empty_version2_imports_into_version3_with_unverified_fact(self, discover):
        discover.return_value = self.discovery()
        dossier = self.imported()
        self.assertEqual(dossier.version, 3)
        self.assertEqual(FactDossier.objects.count(), 2)
        source_kinds = set(dossier.sources.values_list("source_kind", flat=True))
        self.assertEqual(source_kinds, {"wikidata", "wikipedia"})
        fact = dossier.facts.get()
        self.assertEqual(fact.predicate, "founded_year")
        self.assertEqual(fact.value, 1909)
        self.assertEqual(fact.verification_state, "unverified")
        self.assertFalse(hasattr(fact, "human_checked"))
        self.assertEqual(fact.evidence.count(), 2)
        self.assertEqual(set(fact.evidence.values_list("role", flat=True)), {"unknown"})
        self.assertFalse(Fact.objects.filter(
            verification_state="verified",
        ).exists())
        self.assertFalse(self.snapshot.facts.exists())
        discover.assert_called_once_with(club_name="Sturm Graz", country_code="AT")

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_retry_reuses_snapshot_without_external_network(self, discover):
        discover.return_value = self.discovery()
        first = self.imported()
        second = self.imported(expected_version=2)
        self.assertEqual(first.pk, second.pk)
        discover.assert_called_once()
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_owner_and_version_checked_before_any_external_call(self, discover):
        with self.assertRaisesMessage(AutoResearchError, "not_authorized"):
            self.imported(owner=self.other)
        with self.assertRaisesMessage(AutoResearchError, "stale_dossier"):
            self.imported(expected_version=1)
        with self.assertRaisesMessage(AutoResearchError, "invalid_request"):
            self.imported(job_id=True)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_network_failure_does_not_fork_or_mutate_dossier(self, discover):
        discover.side_effect = AutoResearchError("network_error")
        with self.assertRaisesMessage(AutoResearchError, "network_error"):
            self.imported()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 0)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_wikipedia_missing_creates_only_wikidata_source(self, discover):
        data = self.discovery()
        data.update(
            wikipedia_url=None, wikipedia_intro_mentions_year=False,
        )
        discover.return_value = data
        dossier = self.imported()
        self.assertEqual(dossier.sources.count(), 1)
        self.assertEqual(dossier.facts.count(), 1)
        self.assertEqual(dossier.facts.get().evidence.count(), 1)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_missing_founded_year_does_not_invent_fact(self, discover):
        data = self.discovery()
        data["founded_year_candidate"] = None
        discover.return_value = data
        dossier = self.imported()
        self.assertEqual(dossier.facts.count(), 0)
        self.assertEqual(dossier.sources.count(), 2)
        self.assertEqual(self.imported().pk, dossier.pk)
        discover.assert_called_once()

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_existing_manual_qid_reference_does_not_block_automatic_fact_import(self, discover):
        SourceReference.objects.create(
            dossier=self.snapshot, source_kind="wikidata",
            external_id="Q124007617",
            url="https://www.wikidata.org/wiki/Special:EntityData/Q124007617.json",
            title="SK Sturm Graz", retrieved_at=datetime.now(timezone.utc),
            access_state="accessible",
        )
        discover.return_value = self.discovery()
        dossier = self.imported()
        self.assertEqual(dossier.version, 3)
        self.assertEqual(dossier.sources.filter(source_kind="wikidata").count(), 1)
        self.assertEqual(dossier.facts.count(), 1)
        self.assertEqual(
            self.snapshot.sources.get().title, "SK Sturm Graz",
        )
        self.assertTrue(dossier.sources.get(source_kind="wikidata").title.startswith("[auto] "))

    @patch("socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_db_persistence_does_not_dispatch_other_network_services(
        self, discover, http, dns,
    ):
        discover.return_value = self.discovery()
        self.imported()
        http.assert_not_called()
        dns.assert_not_called()
