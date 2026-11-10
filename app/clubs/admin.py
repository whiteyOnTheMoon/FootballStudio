"""Admins can maintain countries, leagues and clubs while the public UI is built."""
from django.contrib import admin
from .models import Club, Country, League


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "tier", "provider", "is_active")
    list_filter = ("country", "tier", "is_active")
    search_fields = ("name", "country__name")
    autocomplete_fields = ("country",)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "league", "provider", "is_manual", "is_active")
    list_filter = ("league__country", "is_manual", "is_active")
    search_fields = ("name", "league__name")
    autocomplete_fields = ("league",)
