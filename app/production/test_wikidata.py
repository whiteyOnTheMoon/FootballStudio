"""Offline contract tests for the first Wikidata research adapter slice."""
from datetime import datetime
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase

from app.production.wikidata import WikidataLookupError, fetch_wikidata_profile


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


def entity_response(qid, *, label="Example FC", description="football club",
                    title="Example FC"):
    entity = {
        "id": qid,
        "labels": {"en": {"value": label}},
        "descriptions": {"en": {"value": description}},
        "sitelinks": {"enwiki": {"title": title}},
    }
    return FakeResponse(json.dumps({"entities": {qid: entity}}).encode("utf-8"))


class WikidataProfileTests(SimpleTestCase):
    @patch("app.production.wikidata.urlopen")
    def test_two_explicit_entities_have_traceable_structured_outputs(self, opener):
        for qid in ("Q123", "Q456"):
            with self.subTest(qid=qid):
                opener.return_value = entity_response(qid)
                profile = fetch_wikidata_profile(qid)
                self.assertEqual(profile["provider"], "wikidata")
                self.assertEqual(profile["entity_id"], qid)
                self.assertEqual(profile["label_en"], "Example FC")
                self.assertEqual(profile["description_en"], "football club")
                self.assertEqual(
                    profile["source_url"],
                    f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
                )
                self.assertEqual(
                    profile["wikipedia_url_en"],
                    "https://en.wikipedia.org/wiki/Example_FC",
                )
                self.assertIsNotNone(datetime.fromisoformat(profile["fetched_at"]).tzinfo)
                json.dumps(profile)
                request = opener.call_args.args[0]
                self.assertEqual(request.full_url, profile["source_url"])
                self.assertEqual(opener.call_args.kwargs["timeout"], 8)

    @patch("app.production.wikidata.urlopen")
    def test_missing_english_fields_remain_unknown(self, opener):
        opener.return_value = FakeResponse(json.dumps({
            "entities": {"Q123": {"id": "Q123", "labels": {}, "descriptions": {},
                                  "sitelinks": {}}}
        }).encode())
        profile = fetch_wikidata_profile("Q123")
        self.assertIsNone(profile["label_en"])
        self.assertIsNone(profile["description_en"])
        self.assertIsNone(profile["wikipedia_url_en"])

    @patch("app.production.wikidata.urlopen")
    def test_wikipedia_title_is_url_encoded(self, opener):
        opener.return_value = entity_response("Q123", title="A/B & C")
        self.assertEqual(fetch_wikidata_profile("Q123")["wikipedia_url_en"],
                         "https://en.wikipedia.org/wiki/A%2FB_%26_C")

    @patch("app.production.wikidata.urlopen")
    def test_invalid_ids_never_trigger_network_request(self, opener):
        for qid in ("", "q123", "Q0", "Q-1", "Q1?x=y", "https://bad.site",
                    "Q123/../../", 123, None):
            with self.subTest(qid=qid):
                with self.assertRaises(ValueError):
                    fetch_wikidata_profile(qid)
        opener.assert_not_called()

    @patch("app.production.wikidata.urlopen")
    def test_transport_http_and_size_failures_have_safe_codes(self, opener):
        cases = [
            (HTTPError("https://www.wikidata.org", 404, "missing", {}, None), "not_found"),
            (HTTPError("https://www.wikidata.org", 429, "throttled", {}, None), "http_error"),
            (URLError("hidden upstream details"), "network_error"),
        ]
        for failure, code in cases:
            with self.subTest(code=code):
                opener.side_effect = failure
                with self.assertRaises(WikidataLookupError) as ctx:
                    fetch_wikidata_profile("Q123")
                self.assertEqual(ctx.exception.code, code)
                self.assertNotIn("hidden", str(ctx.exception))
        opener.side_effect = None
        opener.return_value = FakeResponse(b"x" * 1_000_001)
        with self.assertRaises(WikidataLookupError) as ctx:
            fetch_wikidata_profile("Q123")
        self.assertEqual(ctx.exception.code, "response_too_large")

    @patch("app.production.wikidata.urlopen")
    def test_invalid_json_or_entity_is_not_treated_as_verified_data(self, opener):
        for raw, code in (
            (b"invalid", "invalid_json"),
            (b"[]", "invalid_response"),
            (json.dumps({"entities": {}}).encode(), "entity_missing"),
            (json.dumps({"entities": {"Q123": {"id": "Q456"}}}).encode(), "entity_missing"),
            (json.dumps({"entities": {"Q123": {
                "id": "Q123", "labels": ["bad"], "descriptions": {}, "sitelinks": {}
            }}}).encode(), "invalid_response"),
        ):
            with self.subTest(code=code):
                opener.return_value = FakeResponse(raw)
                with self.assertRaises(WikidataLookupError) as ctx:
                    fetch_wikidata_profile("Q123")
                self.assertEqual(ctx.exception.code, code)
