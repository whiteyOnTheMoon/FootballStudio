"""No-network regression tests for official club research link planning."""
from django.test import SimpleTestCase

from .official_site_links import discover_official_pages


class OfficialSiteDiscoveryTests(SimpleTestCase):
    HOME = "https://club.example.org/en/"

    def test_multilingual_research_sections_are_prioritized(self):
        markup = """
        <a href="/en/history">Our history</a>
        <a href="/de/geschichte">Geschichte</a>
        <a href="/es/historia">Historia</a>
        <a href="/fr/histoire">Histoire</a>
        <a href="/it/storia">Storia</a>
        <a href="/en/honours">Trophies and honours</a>
        <a href="/en/stadium">Stadium</a>
        <a href="/en/club">About our club</a>
        <a href="/en/first-team">Team</a>
        """
        items = discover_official_pages(self.HOME, markup)
        self.assertEqual(len(items), 8)
        self.assertEqual([x["category"] for x in items[:5]], ["history"] * 5)
        self.assertEqual([x["category"] for x in items[5:]],
                         ["honours", "stadium", "about"])
        self.assertTrue(all(item["url"].startswith("https://club.example.org/")
                            for item in items))

    def test_relative_links_canonical_and_deduplicated(self):
        items = discover_official_pages(
            self.HOME,
            '<a href="../history#intro">History</a>'
            '<a href="/history#team">The club history</a>'
            '<a href="/stadium">Stadium</a>',
        )
        self.assertEqual([item["url"] for item in items], [
            "https://club.example.org/history",
            "https://club.example.org/stadium",
        ])

    def test_external_http_private_port_and_session_urls_rejected(self):
        markup = """
        <a href="//evil.example.org/history">History</a>
        <a href="https://club.example.org.evil.org/history">History</a>
        <a href="http://club.example.org/history">History</a>
        <a href="https://club.example.org:8443/history">History</a>
        <a href="https://user:pass@club.example.org/history">History</a>
        <a href="mailto:history@club.example.org">History</a>
        <a href="javascript:alert(1)">History</a>
        <a href="/history?session=abc">History</a>
        <a href="/history">History</a>
        """
        items = discover_official_pages(self.HOME, markup)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://club.example.org/history")

    def test_commercial_access_and_media_links_are_excluded(self):
        items = discover_official_pages(
            self.HOME,
            '<a href="/en/shop/history">Club history</a>'
            '<a href="/en/tickets/club">Club tickets</a>'
            '<a href="/en/login">Club login</a>'
            '<a href="/en/history.pdf">History PDF</a>'
            '<a href="/en/history.jpg">History image</a>'
            '<a href="/en/honours">Honours</a>',
        )
        self.assertEqual([v["category"] for v in items], ["honours"])

    def test_nofollow_and_download_anchors_are_ignored(self):
        items = discover_official_pages(
            self.HOME,
            '<a rel="nofollow" href="/history">History</a>'
            '<a download href="/stadium">Stadium</a>'
            '<a href="#history">History</a>'
            '<a href="/club" title="Our club"><span>Read more</span></a>',
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "about")

    def test_shortlist_is_limited_sorted_and_repeatable(self):
        markup = "".join(f'<a href="/history/{i}">History</a>' for i in range(20))
        first = discover_official_pages(self.HOME, markup, limit=3)
        self.assertEqual(first, discover_official_pages(self.HOME, markup, limit=3))
        self.assertEqual(len(first), 3)
        self.assertEqual(first[0]["url"], "https://club.example.org/history/0")

    def test_generic_homepage_navigation_is_not_included(self):
        markup = '<a href="/en/">Home</a><a href="/news">News</a><a href="/contact">Contact</a>'
        self.assertEqual(discover_official_pages(self.HOME, markup), [])

    def test_invalid_homepage_or_html_fails_closed(self):
        for homepage in (
            "http://club.example.org/", "https://127.0.0.1/",
            "https://localhost/", "https://club.local/",
            "https://user:password@club.example.org/",
            "https://club.example.org:444/", "https://club.example.org/?sid=1",
            "https://club.example.org/#intro", "ftp://club.example.org/",
            "https://club.example.org.evil.local/", None,
        ):
            with self.subTest(homepage=homepage):
                with self.assertRaises(ValueError):
                    discover_official_pages(homepage, "")
        for payload in (None, b"<a>abc</a>", "x" * 300_001):
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(ValueError):
                    discover_official_pages(self.HOME, payload)

    def test_invalid_result_limits_are_rejected(self):
        for limit in (0, 11, -1, 2.5, True):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    discover_official_pages(self.HOME, "<a href='/club'>Club</a>",
                                            limit=limit)
