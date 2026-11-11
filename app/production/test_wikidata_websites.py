"""Offline tests: Wikidata P856 is a candidate, never verified site identity."""
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .wikidata import WikidataLookupError, fetch_wikidata_profile


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


def statement(url, *, rank="normal", qid="Q123", statement_id=None,
              snaktype="value", datatype="url"):
    snak = {"property": "P856", "snaktype": snaktype, "datatype": datatype}
    if snaktype == "value":
        snak["datavalue"] = {"type": "string", "value": url}
    return {
        "rank": rank,
        "mainsnak": snak,
        "id": statement_id or f"{qid}$sample-123",
    }


def response(qid, claims):
    entity = {"id": qid, "claims": claims, "labels": {}, "descriptions": {},
              "sitelinks": {}}
    return FakeResponse(json.dumps({"entities": {qid: entity}}).encode("utf-8"))


class WikidataOfficialWebsitesTests(SimpleTestCase):
    @patch("app.production.wikidata.urlopen")
    def test_club_candidates_preferred_before_normal_deduplicated(self, opener):
        claims = {"P856": [
            statement("https://normal.club.example.org", rank="normal"),
            statement("https://club.example.org", rank="normal"),
            statement("https://club.example.org/", rank="preferred",
                      statement_id="Q123$550e8400-e29b-41d4-a716-446655440000"),
            statement("https://other.club.example.org/", rank="preferred"),
        ]}
        opener.return_value = response("Q123", claims)
        profile = fetch_wikidata_profile("Q123")
        candidates = profile["official_website_candidates"]
        self.assertEqual(len(candidates), 3)
        self.assertEqual([c["rank"] for c in candidates],
                         ["preferred", "preferred", "normal"])
        self.assertEqual(candidates[0]["url"], "https://club.example.org/")
        self.assertEqual(
            candidates[0]["statement_id"], "Q123$550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertTrue(all(c["wikidata_property"] == "P856" for c in candidates))
        self.assertTrue(all(c["verification_state"] == "unverified" for c in candidates))
        self.assertTrue(all(c["source_url"] == profile["source_url"] for c in candidates))
        json.dumps(profile)
        opener.assert_called_once()

    @patch("app.production.wikidata.urlopen")
    def test_league_uses_same_adapter_without_fixed_club_id(self, opener):
        opener.return_value = response("Q456", {
            "P856": [statement("https://league.example.org/competition", qid="Q456")],
        })
        profile = fetch_wikidata_profile("Q456")
        self.assertEqual(profile["entity_id"], "Q456")
        self.assertEqual(profile["official_website_candidates"][0]["url"],
                         "https://league.example.org/competition")
        self.assertEqual(profile["official_website_candidates"][0]["rank"], "normal")

    @patch("app.production.wikidata.urlopen")
    def test_missing_or_empty_property_is_not_filled_in(self, opener):
        for claims in ({}, {"P856": []}):
            with self.subTest(claims=claims):
                opener.return_value = response("Q123", claims)
                self.assertEqual(fetch_wikidata_profile("Q123")[
                    "official_website_candidates"
                ], [])

    @patch("app.production.wikidata.urlopen")
    def test_disallowed_p856_urls_are_ignored(self, opener):
        invalid_urls = [
            "http://club.example.org",
            "https://127.0.0.1/history",
            "https://localhost",
            "https://club.local",
            "https://club.example.internal",
            "https://user:pass@club.example.org/",
            "https://club.example.org:444/",
            "https://club.example.org/?session=secret",
            "https://club.example.org/#anchor",
            "javascript:alert(1)",
            "ftp://club.example.org",
            "https://club.example.org\@external.example.org",
            " https://club.example.org",
            "https://club.example.org/\nmalicious",
        ]
        opener.return_value = response("Q123", {
            "P856": [statement(url) for url in invalid_urls],
        })
        self.assertEqual(
            fetch_wikidata_profile("Q123")["official_website_candidates"], [],
        )
        opener.assert_called_once()

    @patch("app.production.wikidata.urlopen")
    def test_deprecated_no_value_and_wrong_snak_are_not_candidates(self, opener):
        wrong_property = statement("https://wrong.example.org")
        wrong_property["mainsnak"]["property"] = "P999"
        wrong_type = statement("https://wrong.example.org")
        wrong_type["mainsnak"]["datavalue"]["type"] = "wikibase-entityid"
        opener.return_value = response("Q123", {"P856": [
            statement("https://old.example.org/", rank="deprecated"),
            statement(None, snaktype="novalue"),
            statement(None, snaktype="somevalue"),
            wrong_property, wrong_type,
            {"rank": "preferred", "mainsnak": None},
            123,
            statement("https://good.example.org"),
        ]})
        candidates = fetch_wikidata_profile("Q123")["official_website_candidates"]
        self.assertEqual([c["url"] for c in candidates], [
            "https://good.example.org/",
        ])

    @patch("app.production.wikidata.urlopen")
    def test_candidate_list_is_capped_even_with_many_statements(self, opener):
        opener.return_value = response("Q123", {
            "P856": [statement(f"https://site{i}.example.org") for i in range(101)],
        })
        candidates = fetch_wikidata_profile("Q123")["official_website_candidates"]
        self.assertEqual(len(candidates), 5)
        self.assertTrue(all("site100" not in c["url"] for c in candidates))

    @patch("app.production.wikidata.urlopen")
    def test_malformed_claims_fail_closed(self, opener):
        for claims in ([], {"P856": "not-a-list"}, {"P856": {}}):
            with self.subTest(claims=claims):
                opener.return_value = response("Q123", claims)
                with self.assertRaises(WikidataLookupError) as ctx:
                    fetch_wikidata_profile("Q123")
                self.assertEqual(ctx.exception.code, "invalid_response")
