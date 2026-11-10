"""M1 country/league/club schema and manual management tests."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Club, Country, League


class CatalogModelsTests(TestCase):
    def setUp(self):
        self.germany = Country.objects.create(code="de", name="Germany")
        self.austria = Country.objects.create(code="AT", name="Austria")
        self.first = League.objects.create(country=self.germany, name="Bundesliga", tier=1)
        self.second = League.objects.create(country=self.germany, name="2. Bundesliga", tier=2)
        self.austrian = League.objects.create(country=self.austria, name="Bundesliga", tier=1)
        self.first_club = Club.objects.create(
            league=self.first, name="Example FC", provider="catalog",
            provider_id="example-123", is_manual=False,
        )
        self.second_club = Club.objects.create(
            league=self.second, name="Second Example", provider="catalog",
            provider_id="example-456", is_manual=False,
        )

    def test_country_codes_normalized(self):
        self.assertEqual(self.germany.code, "DE")
        invalid = Country(code="DEU", name="Invalid Country")
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_dynamic_country_league_club_relations(self):
        self.assertEqual(list(self.germany.leagues.values_list("tier", flat=True)), [1, 2])
        self.assertEqual(list(self.first.clubs.values_list("name", flat=True)), ["Example FC"])
        self.assertEqual(list(self.second.clubs.values_list("name", flat=True)), ["Second Example"])
        self.assertEqual(self.first_club.league.country.code, "DE")

    def test_same_league_name_in_different_country_allowed(self):
        self.assertEqual(self.austrian.country.code, "AT")

    def test_manual_club_creation_update_and_selection(self):
        manual = Club.objects.create(league=self.second, name="New Town FC")
        self.assertTrue(manual.is_manual)
        self.assertEqual(manual.provider, "manual")
        manual.name = "New Town United"
        manual.save(update_fields=["name", "updated_at"])
        self.assertEqual(
            Club.objects.get(league=self.second, name="New Town United").pk, manual.pk
        )

    def test_club_names_unique_case_insensitive_within_league(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Club.objects.create(league=self.first, name="EXAMPLE FC")
        # Same club name is allowed in a distinct league.
        other = Club.objects.create(league=self.second, name="EXAMPLE FC")
        self.assertIsNotNone(other.pk)

    def test_league_names_unique_case_insensitive_per_country(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                League.objects.create(country=self.germany, name="BUNDESLIGA", tier=3)
        self.assertIsNotNone(self.austrian.pk)

    def test_deleting_parent_does_not_orphan_clubs(self):
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.germany.delete()
        with self.assertRaises(ProtectedError):
            self.first.delete()
