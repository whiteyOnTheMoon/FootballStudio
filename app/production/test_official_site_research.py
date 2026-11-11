"""Offline owner/robots/limited-site research checks: never visit live websites."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.clubs.models import Club, Country, League
from .models import ProductionJob
from .official_site_research import research_official_website
from .safe_official_fetch import WebsiteFetchError


class OfficialWebsiteResearchTests(TestCase):
    HOME = "https://club.example.org/en/"
    LEAGUE = "https://league.example.org/en/"

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="research-owner@example.org", password="Long-Only-Test-Password-2026",
        )
        self.other = User.objects.create_user(
            email="other-research-owner@example.org", password="Long-Only-Test-Password-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Documentary Pilot",
            country_code="GB", league_name="Example League", club_name="Example FC",
        )

    def research(self, **kwargs):
        data = {
            "owner": self.owner, "job_id": self.job.pk,
            "homepage_url": self.HOME, "context": "club",
            "identity_confirmed": True, "terms_confirmed": True,
        }
        data.update(kwargs)
        return research_official_website(**data)

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_confirmed_club_returns_only_minimal_unverified_metadata(self, download, sleep):
        download.side_effect = [
            "User-agent: *\nDisallow: /tickets\n",
            """<title>Example Football Club</title>
            <h1>The Club</h1>
            <a href="/history">History</a>
            <a href="/honours">Honours</a>
            <a href="/stadium">Stadium</a>
            <a href="https://evil.example.org/history">History</a>
            <p>This is a long copyrighted article. No body text saved.</p>""",
            "<title>History - Example FC</title><h1>Club History</h1><p>Entire story ignored.</p>",
            "<title>Honours</title><h2>Honours</h2>",
            "<title>Stadium</title><h1>Home Ground</h1>",
        ]
        result = self.research()
        self.assertEqual(result["job_id"], self.job.pk)
        self.assertEqual(result["club_id"], self.job.club_id)
        self.assertEqual(result["context"], "club")
        self.assertEqual(result["source_status"], "unverified")
        self.assertFalse(result["stored"])
        self.assertEqual(len(result["pages"]), 4)
        self.assertEqual(
            [x["url"] for x in result["pages"]],
            [self.HOME, "https://club.example.org/history",
             "https://club.example.org/honours",
             "https://club.example.org/stadium"],
        )
        self.assertEqual(result["pages"][1]["title"], "History - Example FC")
        self.assertEqual(result["pages"][1]["headings"], ["Club History"])
        self.assertEqual(result["pages"][1]["verification_state"], "unverified")
        self.assertNotIn("Entire story ignored", str(result))
        self.assertTrue(all("retrieved_at" in x for x in result["pages"]))
        self.assertEqual(download.call_count, 5)  # robots + homepage + 3 pages
        sleep.assert_called_with(2)
        self.assertEqual(sleep.call_count, 4)
        self.assertFalse(self.job.fact_dossiers.exists())

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_league_context_recognizes_table_schedule_and_results(self, download, sleep):
        download.side_effect = [
            "User-agent: *\nDisallow:\n",
            """<h1>Example League</h1>
            <a href="/standings">Standings</a>
            <a href="/fixtures">Fixtures</a>
            <a href="/results">Results</a>""",
            "<h1>Standings 2026/27</h1>",
            "<h1>Season fixtures</h1>",
            "<h1>Results</h1>",
        ]
        result = self.research(homepage_url=self.LEAGUE, context="league")
        self.assertEqual(result["league_id"], self.job.club.league_id)
        self.assertEqual([p.get("category") for p in result["pages"][1:]],
                         ["standings", "fixtures", "results"])
        self.assertEqual(download.call_count, 5)

    @patch("app.production.official_site_research._download_public_https")
    def test_foreign_owner_unconfirmed_identity_and_terms_fail_before_network(self, download):
        cases = [
            {"owner": self.other},
            {"identity_confirmed": False},
            {"identity_confirmed": 1},
            {"terms_confirmed": False},
            {"terms_confirmed": "yes"},
            {"context": "transfermarkt"},
            {"homepage_url": "https://127.0.0.1/"}
        ]
        for options in cases:
            with self.subTest(options=options):
                with self.assertRaises((ValueError, WebsiteFetchError, ProductionJob.DoesNotExist)):
                    self.research(**options)
        download.assert_not_called()

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_robots_disallow_site_prevents_any_html_fetch(self, download, sleep):
        download.return_value = "User-agent: *\nDisallow: /\n"
        with self.assertRaises(WebsiteFetchError) as exc:
            self.research()
        self.assertEqual(exc.exception.code, "robots_disallowed")
        download.assert_called_once_with(
            "https://club.example.org/robots.txt", kind="robots",
        )
        sleep.assert_not_called()

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_robots_disallowed_subpage_is_skipped(self, download, sleep):
        download.side_effect = [
            "User-agent: *\nDisallow: /history\n",
            """<a href="/history">History</a>
            <a href="/honours">Honours</a>
            <a href="/stadium">Stadium</a>""",
            "<title>Honours</title>", "<title>Stadium</title>",
        ]
        result = self.research()
        self.assertEqual([p["url"] for p in result["pages"]], [
            self.HOME,
            "https://club.example.org/honours",
            "https://club.example.org/stadium",
        ])
        self.assertEqual(download.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    @patch("app.production.official_site_research._download_public_https")
    def test_unavailable_robots_must_fail_closed_without_html(self, download):
        for code in ("http_error", "redirect_blocked", "access_restricted"):
            with self.subTest(code=code):
                download.reset_mock()
                download.side_effect = WebsiteFetchError(code)
                with self.assertRaises(WebsiteFetchError) as ctx:
                    self.research()
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(download.call_count, 1)

    @patch("app.production.official_site_research._download_public_https")
    def test_invalid_robots_file_fails_closed(self, download):
        for bad in ("", "This is not a robots.txt file", "<html>No robots</html>"):
            with self.subTest(bad=bad):
                download.reset_mock()
                download.return_value = bad
                with self.assertRaises(WebsiteFetchError) as exc:
                    self.research()
                self.assertEqual(exc.exception.code, "robots_unusable")
                download.assert_called_once()

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_crawl_delay_is_respected_and_excessive_delay_rejected(self, download, sleep):
        download.side_effect = [
            "User-agent: *\nCrawl-delay: 4\nDisallow:\n",
            "<h1>Landing</h1>",
        ]
        result = self.research()
        self.assertEqual(len(result["pages"]), 1)
        sleep.assert_called_once_with(4)

        download.reset_mock()
        sleep.reset_mock()
        download.side_effect = None
        download.return_value = "User-agent: *\nCrawl-delay: 100\nDisallow:\n"
        with self.assertRaises(WebsiteFetchError) as exc:
            self.research()
        self.assertEqual(exc.exception.code, "crawl_delay_too_long")
        self.assertEqual(download.call_count, 1)
        sleep.assert_not_called()

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_many_candidate_pages_still_max_three(self, download, sleep):
        homepage_html = "".join(
            f'<a href="/history/{i}">History {i}</a>' for i in range(25)
        )
        download.side_effect = [
            "User-agent: *\nDisallow:\n",
            homepage_html,
            "<h1>History</h1>", "<h1>History</h1>", "<h1>History</h1>",
        ]
        result = self.research()
        self.assertEqual(len(result["pages"]), 4)
        self.assertEqual(download.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
