"""Guarded official club legend-list parsing and version-safe owner import.

All official-site traffic is mocked. A real list is never inferred from
Wikidata popularity, or from just knowing a homepage URL.
"""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.clubs.models import Club, Country, League
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceConfirmation,
    SourceReference,
)
from .official_legends import (
    _discover_link, _read_official_legends, crosscheck_official_club_legends,
    extract_official_legend_list,
)
from .safe_official_fetch import WebsiteFetchError
from .wikimedia_auto import AutoResearchError

CLUB_QID = "Q124007617"
HOME = "https://sksturm.at/"
LEGENDS = "https://sksturm.at/c/legendenklub"
MARKER = "auto-official-legends:" + CLUB_QID
HTML = """
<html><head><title>Legendenklub | SK Sturm</title></head>
<body>
<nav><a href="/wettbewerb">Meisterschaft</a></nav>
<h2>Der Legendenklub</h2><p>Mario Haas und Ivica Vastic – große Namen.</p>
<h2>Trainerlegenden</h2>
<p>Otto Barić, Franco Foda, Gernot Fraydl, Walter Ludescher, Ivica Osim,
Karl Schlechta, Gerdi Springer, Günther Paulitsch</p>
<h2>Spielerlegenden</h2>
<h3>Unterteilung in Epochen</h3>
<h3>1994-2006</h3>
<p>Mario Haas, György Korsós, Roman Mählich, Darko Milanič,
Günther Neukirchner, Mario Posch, Ivica Vastić, Arnold Wetl</p>
<h2>Jahrhundertelf</h2>
<p>Erwähnung in einer späteren Meldung: Marko Pantelić, Gordon Schildenfeld</p>
<script><h2>Spielerlegenden</h2><p>Injected Person, Injected Person 2</p></script>
</body></html>
"""


def discovered():
    return LEGENDS, {
        "player": {
            "mario haas": "Mario Haas",
            "ivica vastić": "Ivica Vastić",
        },
        "trainer": {
            "ivica osim": "Ivica Osim",
            "franco foda": "Franco Foda",
        },
    }


class OfficialLegendsParserTests(SimpleTestCase):
    def test_parses_only_explicit_official_sections_not_story_or_later_content(self):
        sections = extract_official_legend_list(HTML)
        self.assertIn("mario haas", sections["player"])
        self.assertIn("ivica vastić", sections["player"])
        self.assertIn("ivica osim", sections["trainer"])
        self.assertIn("franco foda", sections["trainer"])
        self.assertNotIn("marko pantelić", sections["player"])
        self.assertNotIn("gordon schildenfeld", sections["player"])
        self.assertNotIn("injected person", sections["player"])

    def test_no_section_or_no_explicit_roster_causes_no_claims(self):
        with self.assertRaisesMessage(AutoResearchError, "no_legend_sections"):
            extract_official_legend_list(
                "<html><h2>Club History</h2><p>Mario Haas, Ivica Vastić</p></html>"
            )
        with self.assertRaisesMessage(AutoResearchError, "no_legend_names"):
            extract_official_legend_list(
                "<html><h2>Spielerlegenden</h2><p>Mario Haas</p></html>"
            )
        with self.assertRaisesMessage(AutoResearchError, "invalid_legend_page"):
            extract_official_legend_list("<html>" * 150001)

    def test_same_host_link_discovery_no_guess_on_multiple_candidates(self):
        html = '<a href="/c/legendenklub">Legendenklub</a>'
        self.assertEqual(_discover_link(HOME, html), LEGENDS)
        for html in (
            '<a href="https://evil.example.org/legends">Legends</a>',
            '<a href="/c/legendenklub">Legenden</a>'
            '<a href="/c/andere-legenden">Legenden</a>',
            '<a href="/news">News</a>',
        ):
            with self.subTest(html=html), self.assertRaisesMessage(
                AutoResearchError, "no_unique_legends_link",
            ):
                _discover_link(HOME, html)

    @patch("app.production.official_legends.time.sleep")
    @patch("app.production.official_legends._download_public_https")
    @patch("app.production.official_legends._robots_policy")
    def test_real_transport_only_reads_confirmed_sturm_path_after_robots(
        self, robots, downloader, sleep,
    ):
        gate = type("Gate", (), {"can_fetch": lambda self, agent, url: True})()
        robots.return_value = (HOME + "robots.txt", gate, 2)
        downloader.return_value = HTML
        url, found = _read_official_legends(HOME, CLUB_QID)
        self.assertEqual(url, LEGENDS)
        self.assertIn("mario haas", found["player"])
        downloader.assert_called_once_with(LEGENDS, kind="html")
        sleep.assert_called_once_with(2)
        robots.assert_called_once_with(HOME)

    @patch("app.production.official_legends.time.sleep")
    @patch("app.production.official_legends._download_public_https")
    @patch("app.production.official_legends._robots_policy")
    def test_robots_disallow_blocks_all_html_downloads(
        self, robots, downloader, sleep,
    ):
        gate = type("Gate", (), {"can_fetch": lambda self, agent, url: False})()
        robots.return_value = (HOME + "robots.txt", gate, 2)
        with self.assertRaisesMessage(WebsiteFetchError, "robots_disallowed"):
            _read_official_legends(HOME, CLUB_QID)
        downloader.assert_not_called()
        sleep.assert_not_called()

    @patch("app.production.official_legends.time.sleep")
    @patch("app.production.official_legends._download_public_https")
    @patch("app.production.official_legends._robots_policy")
    def test_generic_other_club_uses_bounded_same_host_link_discovery(
        self, robots, downloader, sleep,
    ):
        gate = type("Gate", (), {"can_fetch": lambda self, agent, url: True})()
        robots.return_value = (HOME + "robots.txt", gate, 2)
        downloader.side_effect = [
            '<a href="/c/legendenklub">Club Legends</a>', HTML,
        ]
        url, found = _read_official_legends(HOME, "Q998877")
        self.assertEqual(url, LEGENDS)
        self.assertIn("mario haas", found["player"])
        self.assertEqual(downloader.call_count, 2)
        self.assertEqual(downloader.call_args_list[0].args, (HOME,))
        self.assertEqual(downloader.call_args_list[1].args, (LEGENDS,))
        self.assertEqual(sleep.call_count, 2)


class OfficialLegendsImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="official-legend-owner@example.org",
            password="Example-test-password-2026",
        )
        self.other = User.objects.create_user(
            email="official-legend-other@example.org",
            password="Example-test-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="Sourced Club Legends",
        )
        self.before = FactDossier.objects.create(job=self.job, version=5)
        SourceReference.objects.create(
            dossier=self.before, source_kind="wikidata",
            url=(
                "https://www.wikidata.org/wiki/Special:EntityData/"
                + CLUB_QID + ".json"
            ),
            title="[auto] SK Sturm Graz", external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        official = SourceReference.objects.create(
            dossier=self.before, source_kind="club_official",
            url=HOME, title="Homepage SK Sturm",
            retrieved_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
            access_state="accessible",
        )
        SourceConfirmation.objects.create(
            source=official, reviewer=self.owner,
            checked_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
            confirmed_domain="sksturm.at",
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
            basis="Official site of SK Sturm Graz, manually confirmed.",
        )
        for name, qid in (
            ("Mario Haas", "Q471837"),
            ("Ivica Vastić", "Q295065"),
            ("Marko Pantelić", "Q207399"),
        ):
            Fact.objects.create(
                dossier=self.before,
                predicate="club_player_candidate",
                value={"name": name, "person_qid": qid, "sitelinks": 20},
                assertion_text=f"Wikidata records a team association for {name}.",
                verification_state="unverified",
            )
        self.expected = {
            "owner": self.owner, "job_id": self.job.pk, "expected_version": 5,
        }

    def run_check(self, **kwargs):
        return crosscheck_official_club_legends(**(self.expected | kwargs))

    @patch("app.production.official_legends._read_official_legends")
    def test_real_dossier_creates_official_player_matches_and_coaches(self, read):
        read.return_value = discovered()
        after = self.run_check()
        self.assertEqual(after.version, 6)
        self.assertEqual(self.before.facts.count(), 3)
        self.assertEqual(after.facts.count(), 7)
        self.assertEqual(after.facts.filter(
            predicate="official_player_legend_candidate",
        ).count(), 2)
        self.assertEqual(after.facts.filter(
            predicate="official_coach_legend_candidate",
        ).count(), 2)
        self.assertFalse(after.facts.filter(
            verification_state="verified",
        ).exists())
        self.assertEqual(
            set(after.facts.filter(
                predicate="official_player_legend_candidate",
            ).values_list("value__name", flat=True)),
            {"Mario Haas", "Ivica Vastić"},
        )
        for fact in after.facts.exclude(predicate="club_player_candidate"):
            self.assertEqual(fact.evidence.count(), 1)
            evidence = fact.evidence.get()
            self.assertEqual(evidence.role, "unknown")
            self.assertEqual(evidence.source.url, LEGENDS)
            self.assertEqual(evidence.source.external_id, MARKER)
        self.assertFalse(self.before.sources.filter(external_id=MARKER).exists())
        read.assert_called_once_with(HOME, CLUB_QID)

    @patch("app.production.official_legends._read_official_legends")
    def test_retry_does_not_fetch_or_write_again(self, read):
        read.return_value = discovered()
        first = self.run_check()
        second = self.run_check()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.official_legends._read_official_legends")
    def test_wrong_owner_and_stale_version_rejected_without_network(self, read):
        for change, code in (
            ({"owner": self.other}, "not_authorized"),
            ({"expected_version": 4}, "stale_dossier"),
            ({"job_id": True}, "invalid_request"),
        ):
            with self.subTest(change=change), self.assertRaisesMessage(
                AutoResearchError, code,
            ):
                self.run_check(**change)
        read.assert_not_called()

    @patch("app.production.official_legends._read_official_legends")
    def test_manual_source_confirmation_is_required(self, read):
        SourceConfirmation.objects.all().delete()
        with self.assertRaisesMessage(AutoResearchError, "no_confirmed_club_source"):
            self.run_check()
        read.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_legends._read_official_legends")
    def test_no_player_candidates_causes_no_network(self, read):
        self.before.facts.all().delete()
        with self.assertRaisesMessage(AutoResearchError, "no_player_candidates"):
            self.run_check()
        read.assert_not_called()

    @patch("app.production.official_legends._read_official_legends")
    def test_robots_failure_does_not_create_new_dossier(self, read):
        read.side_effect = WebsiteFetchError("robots_disallowed")
        with self.assertRaisesMessage(
            AutoResearchError, "official_site_robots_disallowed",
        ):
            self.run_check()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_legends._read_official_legends")
    def test_only_coach_list_can_still_import_coach_candidates(self, read):
        read.return_value = (LEGENDS, {
            "player": {}, "trainer": {"ivica osim": "Ivica Osim"},
        })
        after = self.run_check()
        self.assertEqual(after.facts.filter(
            predicate="official_coach_legend_candidate",
        ).count(), 1)
        self.assertEqual(after.facts.filter(
            predicate="official_player_legend_candidate",
        ).count(), 0)

    @patch("app.production.official_legends._read_official_legends")
    def test_no_matching_list_does_not_fake_confirmations(self, read):
        read.return_value = (LEGENDS, {
            "player": {"unrelated person": "Unrelated Person"},
            "trainer": {},
        })
        with self.assertRaisesMessage(AutoResearchError, "no_legend_matches"):
            self.run_check()
        self.assertEqual(FactDossier.objects.count(), 1)
