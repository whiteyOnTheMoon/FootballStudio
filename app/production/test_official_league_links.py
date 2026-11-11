"""League-homepage candidate discovery without network access."""
from django.test import SimpleTestCase

from .official_site_links import discover_official_pages


class OfficialLeagueLinksTests(SimpleTestCase):
    HOME = "https://league.example.org/en/"

    def test_official_league_pages_are_ranked_in_multiple_languages(self):
        html = """
        <a href="/en/standings">Standings</a>
        <a href="/de/tabelle">Tabelle</a>
        <a href="/es/clasificacion">Clasificación</a>
        <a href="/fr/classement">Classement</a>
        <a href="/it/classifica">Classifica</a>
        <a href="/de/spielplan">Spielplan</a>
        <a href="/en/results">Results</a>
        <a href="/en/regulations">Competition format</a>
        <a href="/fr/equipes">Équipes</a>
        <a href="/en/statistics">Statistics</a>
        """
        found = discover_official_pages(self.HOME, html, limit=10, context="league")
        self.assertEqual([item["category"] for item in found],
                         ["standings"] * 5 + [
                             "fixtures", "results", "competition", "clubs", "statistics",
                         ])
        self.assertEqual(len(found), 10)

    def test_club_mode_stays_unchanged_and_does_not_show_standings(self):
        html = '<a href="/en/history">History</a><a href="/en/standings">Standings</a>'
        self.assertEqual(
            [p["category"] for p in discover_official_pages(self.HOME, html)],
            ["history"],
        )
        self.assertEqual(
            [p["category"] for p in discover_official_pages(self.HOME, html, context="club")],
            ["history"],
        )

    def test_reject_unsafe_and_unrelated_league_links(self):
        html = """
        <a href="http://league.example.org/standings">Table</a>
        <a href="https://fake.example.org/standings">Table</a>
        <a href="//league.example.org.evil.org/results">Results</a>
        <a href="https://league.example.org:444/standings">Standings</a>
        <a href="/results?token=private">Results</a>
        <a href="/tickets/standings">Standings</a>
        <a href="/shop/fixtures">Fixtures</a>
        <a href="/en/standings">Standings</a>
        <a href="/en/standings#today">Table</a>
        """
        found = discover_official_pages(self.HOME, html, context="league")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["url"], "https://league.example.org/en/standings")

    def test_invalid_context_and_bounded_results(self):
        html = "".join(
            f'<a href="/standings/{i}">Standings</a>' for i in range(20)
        )
        found = discover_official_pages(self.HOME, html, context="league", limit=3)
        self.assertEqual(len(found), 3)
        self.assertEqual(found[0]["url"], "https://league.example.org/standings/0")
        with self.assertRaises(ValueError):
            discover_official_pages(self.HOME, html, context="unknown")

    def test_unknown_league_homepage_has_no_guessed_url(self):
        self.assertEqual(
            discover_official_pages(self.HOME, "<a href='/news'>News</a>", context="league"),
            [],
        )
