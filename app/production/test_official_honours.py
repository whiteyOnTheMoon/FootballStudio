"""FS-014b: official league/club honours parsing and immutable import tests."""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from app.clubs.models import Club, Country, League
from .models import (
    Fact, FactDossier, ProductionJob, SourceConfirmation, SourceReference,
)
from .official_honours import (
    _find_one_page, _gather_honours, _parse_club_profile,
    _parse_league_table, _read_official, _season_valid, _team_matches,
    import_official_honours_timeline,
)
from .safe_official_fetch import WebsiteFetchError
from .wikimedia_auto import AutoResearchError

QID = "Q124007617"
CLUB = "https://sksturm.at/"
LEAGUE = "https://www.bundesliga.at/"
LEAGUE_PAGE = "https://www.bundesliga.at/de/titel-uebersicht"
CLUB_PAGE = "https://sksturm.at/en/c/steckbrief"

# Realistic bounded official rows. More than ten seasons must be present so
# the generic parser cannot mistake a short arbitrary table for an honours list.
ROWS = (
    ("2025/26", "LASK", "LASK"),
    ("2024/25", "SK Puntigamer Sturm Graz", "RZ Pellets WAC"),
    ("2023/24", "SK Puntigamer Sturm Graz", "SK Puntigamer Sturm Graz"),
    ("2022/23", "FC Red Bull Salzburg", "SK Puntigamer Sturm Graz"),
    ("2021/22", "FC Red Bull Salzburg", "FC Red Bull Salzburg"),
    ("2019/20", "FC Red Bull Salzburg", "FC Red Bull Salzburg"),
    ("2017/18", "FC Red Bull Salzburg", "SK Puntigamer Sturm Graz"),
    ("2015/16", "FC Red Bull Salzburg", "FC Red Bull Salzburg"),
    ("2010/11", "SK Puntigamer Sturm Graz", "SV Ried"),
    ("2009/10", "FC Red Bull Salzburg", "SK Puntigamer Sturm Graz"),
    ("2004/05", "SK Rapid Wien", "FK Austria Wien"),
    ("2000/01", "FC Tirol Milch Innsbruck", "FC Kärnten"),
    ("1998/99", "SK Sturm Graz", "SK Sturm Graz"),
    ("1997/98", "SK Sturm Graz", "SV Ried"),
    ("1996/97", "SV Austria Salzburg", "SK Sturm Graz"),
    ("1995/96", "SK Rapid Wien", "SK Sturm Graz"),
)

CLUB_HTML = """
<html>
<h1>Profile of a club</h1>
<p>We won cups and titles over many seasons 2023/24.</p>
<h2>National success</h2>
<p>Austrian Champion: 5x (1997/98, 1998/99, 2010/11, 2023/24 and 2024/25)</p>
<p>Austrian Cup Winner: 6x (1995/96, 1996/97, 1998/99, 2009/10, 2017/18 and 2022/23)</p>
<h3>International success</h3><p>Champions League 2023/24</p>
<script><p>Austrian Cup Winner: 1x (2023/24)</p></script>
</html>
"""


def league_html(rows=ROWS):
    heading = "<tr><th>Saison</th><th>Meister</th><th>Cup-Sieger</th><th>Supercup</th></tr>"
    body = "".join(
        "<tr><td>" + season + "</td><td><a>" + champion + "</a></td>"
        "<td>" + cup + "</td><td></td></tr>"
        for season, champion, cup in rows
    )
    return "<html><table><thead>" + heading + "</thead><tbody>" + body + "</tbody></table></html>"


def expected_wins():
    return {
        ("2024/25", "league_champion"),
        ("2023/24", "league_champion"),
        ("2023/24", "domestic_cup"),
        ("2022/23", "domestic_cup"),
        ("2017/18", "domestic_cup"),
        ("2010/11", "league_champion"),
        ("2009/10", "domestic_cup"),
        ("1998/99", "league_champion"),
        ("1998/99", "domestic_cup"),
        ("1997/98", "league_champion"),
        ("1996/97", "domestic_cup"),
        ("1995/96", "domestic_cup"),
    }


def gathered():
    return {
        "league_url": LEAGUE_PAGE,
        "club_url": CLUB_PAGE,
        "league_wins": expected_wins(),
        "club_wins": expected_wins() - {("2023/24", "domestic_cup")},
        "retrieved_at": datetime(2026, 11, 13, tzinfo=dt_timezone.utc),
    }


class HonoursParsingTests(SimpleTestCase):
    def test_table_requires_explicit_season_champion_and_cup_columns(self):
        self.assertEqual(
            _parse_league_table(league_html(), "Sturm Graz"),
            expected_wins(),
        )
        self.assertEqual(len(expected_wins()), 12)
        with self.assertRaisesMessage(AutoResearchError, "invalid_honours_table"):
            _parse_league_table(
                league_html().replace("Cup-Sieger", "Cup-Finalist"),
                "Sturm Graz",
            )

    def test_sponsors_can_prefix_names_but_youth_teams_cannot_match(self):
        self.assertTrue(_team_matches(
            "SK Puntigamer Sturm Graz", "Sturm Graz",
        ))
        self.assertTrue(_team_matches("Sturm Graz", "Sturm Graz"))
        for misleading in (
            "Sturm Graz II", "Sturm Graz Frauen",
            "Grazer AK", "Sturm Graz Junioren", "SK Sturm Graz U21",
        ):
            with self.subTest(name=misleading):
                self.assertFalse(_team_matches(misleading, "Sturm Graz"))

    def test_duplicate_conflicting_seasons_are_rejected(self):
        rows = list(ROWS)
        rows.append(("2023/24", "Grazer AK", "Grazer AK"))
        with self.assertRaisesMessage(
            AutoResearchError, "ambiguous_honours_table",
        ):
            _parse_league_table(league_html(rows), "Sturm Graz")

    def test_future_seasons_and_bad_season_not_imported(self):
        self.assertFalse(_season_valid("2024/26"))
        self.assertFalse(_season_valid("2028/29"))
        self.assertFalse(_season_valid("2024-25"))
        self.assertFalse(_season_valid("1900/20"))
        self.assertTrue(_season_valid("1997/98"))

    def test_club_profile_requires_exact_section_and_count(self):
        self.assertEqual(
            _parse_club_profile(CLUB_HTML),
            expected_wins() - {("2023/24", "domestic_cup")},
        )
        with self.assertRaisesMessage(
            AutoResearchError, "invalid_club_profile",
        ):
            _parse_club_profile(CLUB_HTML.replace(
                "Austrian Cup Winner: 6x", "Austrian Cup Winner: 7x",
            ))
        with self.assertRaisesMessage(
            AutoResearchError, "invalid_club_profile",
        ):
            _parse_club_profile(CLUB_HTML.replace(
                "<h2>National success</h2>", "<h2>News</h2>",
            ))

    def test_link_discovery_never_crosses_confirmed_domain(self):
        self.assertEqual(
            _find_one_page(
                LEAGUE,
                '<a href="/de/titel-uebersicht">Champions</a>',
                role="league",
            ),
            LEAGUE_PAGE,
        )
        for bad in (
            '<a href="https://evil.example/awards">Champions</a>',
            '<a href="/a">Champions</a><a href="/b">Champions</a>',
        ):
            with self.subTest(html=bad), self.assertRaisesMessage(
                AutoResearchError, "no_unique_honours_link",
            ):
                _find_one_page(LEAGUE, bad, role="league")

    @patch("app.production.official_honours.time.sleep")
    @patch("app.production.official_honours._download_public_https")
    @patch("app.production.official_honours._robots_policy")
    def test_pilot_fetches_exact_sources_after_robots(
        self, robots, fetch, sleep,
    ):
        gate = type("Gate", (), {
            "can_fetch": lambda self, agent, url: True,
        })()
        robots.return_value = (LEAGUE + "robots.txt", gate, 2)
        fetch.return_value = league_html()
        import time
        url, html = _read_official(
            LEAGUE, role="league", hint="/de/titel-uebersicht",
            deadline=time.monotonic() + 30,
        )
        self.assertEqual(url, LEAGUE_PAGE)
        self.assertEqual(html, league_html())
        fetch.assert_called_once_with(LEAGUE_PAGE, kind="html")
        sleep.assert_called_once_with(2)
        robots.assert_called_once_with(LEAGUE)

    @patch("app.production.official_honours.time.sleep")
    @patch("app.production.official_honours._download_public_https")
    @patch("app.production.official_honours._robots_policy")
    def test_robots_disallow_makes_no_html_request(
        self, robots, fetch, sleep,
    ):
        gate = type("Gate", (), {
            "can_fetch": lambda self, agent, url: False,
        })()
        robots.return_value = (LEAGUE + "robots.txt", gate, 2)
        import time
        with self.assertRaisesMessage(WebsiteFetchError, "robots_disallowed"):
            _read_official(
                LEAGUE, role="league", hint="/de/titel-uebersicht",
                deadline=time.monotonic() + 30,
            )
        fetch.assert_not_called()
        sleep.assert_not_called()


class OfficialHonoursImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="honours-owner@example.org",
            password="Local-test-only-password-12345",
        )
        self.other = User.objects.create_user(
            email="honours-other@example.org",
            password="Local-test-only-password-12345",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
            title="A History with Titles",
        )
        self.before = FactDossier.objects.create(
            job=self.job, version=6,
        )
        SourceReference.objects.create(
            dossier=self.before,
            source_kind="wikidata",
            url=(
                "https://www.wikidata.org/wiki/Special:EntityData/"
                + QID + ".json"
            ),
            title="[auto] SK Sturm Graz", external_id=QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=dt_timezone.utc),
            access_state="accessible",
        )
        for url, kind, host, title in (
            (CLUB, "club_official", "sksturm.at", "Official Sturm homepage"),
            (LEAGUE, "league_official", "www.bundesliga.at", "Official Bundesliga"),
        ):
            source = SourceReference.objects.create(
                dossier=self.before, url=url, source_kind=kind,
                title=title,
                retrieved_at=datetime(2026, 11, 11, tzinfo=dt_timezone.utc),
                access_state="accessible",
            )
            SourceConfirmation.objects.create(
                source=source, reviewer=self.owner,
                confirmed_domain=host,
                checked_at=datetime(2026, 11, 11, tzinfo=dt_timezone.utc),
                identity_confirmed=True, terms_confirmed=True,
                access_confirmed=True,
                basis="Confirmed official club or league website for research.",
            )
        Fact.objects.create(
            dossier=self.before,
            predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
        )

    def import_it(self, **changes):
        data = {
            "owner": self.owner, "job_id": self.job.pk, "expected_version": 6,
        }
        data.update(changes)
        return import_official_honours_timeline(**data)

    @patch("app.production.official_honours._gather_honours")
    def test_sturm_title_timeline_detects_both_and_uncorroborated_2023_cup(
        self, gather,
    ):
        gather.return_value = gathered()
        dossier = self.import_it()
        self.assertEqual(dossier.version, 7)
        self.assertEqual(self.before.facts.count(), 1)
        self.assertEqual(dossier.facts.count(), 13)
        self.assertEqual(dossier.sources.count(), 5)
        entries = list(dossier.facts.filter(
            predicate="club_honour_candidate",
        ))
        self.assertEqual(len(entries), 12)
        matches = [f for f in entries if f.value["corroboration"] == "both"]
        not_listed = [
            f for f in entries if f.value["corroboration"] == "league_only"
        ]
        self.assertEqual(len(matches), 11)
        self.assertEqual(len(not_listed), 1)
        self.assertEqual(not_listed[0].value, {
            "season": "2023/24", "category": "domestic_cup",
            "corroboration": "league_only",
        })
        self.assertEqual(not_listed[0].evidence.count(), 1)
        self.assertEqual(matches[0].evidence.count(), 2)
        self.assertFalse(dossier.facts.filter(
            verification_state="verified",
        ).exists())
        self.assertFalse(self.before.sources.filter(
            external_id="auto-honours:" + QID,
        ).exists())
        gather.assert_called_once()
        self.assertEqual(gather.call_args.kwargs["club_name"], "Sturm Graz")
        self.assertEqual(gather.call_args.kwargs["country_code"], "AT")

    @patch("app.production.official_honours._gather_honours")
    def test_no_available_club_profile_is_not_reported_as_disagreement(self, gather):
        data = gathered()
        data["club_wins"] = None
        data["club_url"] = None
        gather.return_value = data
        dossier = self.import_it()
        statuses = set(dossier.facts.filter(
            predicate="club_honour_candidate",
        ).values_list("value__corroboration", flat=True))
        self.assertEqual(statuses, {"club_not_checked"})
        self.assertEqual(dossier.sources.count(), 4)

    @patch("app.production.official_honours._gather_honours")
    def test_retry_is_idempotent_and_does_not_refetch(self, gather):
        gather.return_value = gathered()
        first = self.import_it()
        second = self.import_it()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(gather.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.official_honours._gather_honours")
    def test_owner_and_stale_version_checked_before_requests(self, gather):
        for kwargs, code in (
            ({"owner": self.other}, "not_authorized"),
            ({"expected_version": 5}, "stale_dossier"),
            ({"job_id": True}, "invalid_request"),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesMessage(
                AutoResearchError, code,
            ):
                self.import_it(**kwargs)
        gather.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_no_confirmed_league_domain_stops_before_network(self, gather):
        source = self.before.sources.get(source_kind="league_official")
        source.manual_confirmation.delete()
        with self.assertRaisesMessage(
            AutoResearchError, "no_confirmed_league_source",
        ):
            self.import_it()
        gather.assert_not_called()
        self.assertEqual(self.before.facts.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_unavailable_league_page_does_not_fork(self, gather):
        gather.side_effect = AutoResearchError("league_site_robots_disallowed")
        with self.assertRaisesMessage(
            AutoResearchError, "league_site_robots_disallowed",
        ):
            self.import_it()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_club_only_season_is_clearly_marked_unverified(self, gather):
        data = gathered()
        data["club_wins"] = set(data["club_wins"]) | {
            ("2019/20", "domestic_cup")
        }
        gather.return_value = data
        dossier = self.import_it()
        item = next(
            f for f in dossier.facts.filter(
                predicate="club_honour_candidate",
            ) if f.value["corroboration"] == "club_only"
        )
        self.assertIn("not corroborated", item.assertion_text)
        self.assertEqual(item.evidence.count(), 1)
        self.assertEqual(item.evidence.get().source.source_kind, "club_official")
        self.assertEqual(item.verification_state, "unverified")
