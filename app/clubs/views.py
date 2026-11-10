"""Authenticated JSON endpoints for the first dynamic club picker."""
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .catalog import CatalogUnavailable, discover_countries, season_label, season_start, sync_league_teams
from .forms import ManualClubForm
from .models import Club, Country, League


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@login_required
@require_GET
@never_cache
def countries(request):
    available, errors = discover_countries()
    if not available:
        return _error(
            "No two-tier country catalog is currently available. "
            "Please try again later; manual club entry follows in M1.",
            status=503,
        )
    return JsonResponse({
        "season": season_label(season_start()),
        "countries": [{"code": x.code, "name": x.name} for x in available],
        "warnings": errors,
    })


@login_required
@require_GET
@never_cache
def leagues(request):
    code = request.GET.get("country", "").strip().upper()
    if code not in ("GB", "DE"):
        return _error("Choose a supported country.")
    country = get_object_or_404(Country, code=code, is_active=True)
    items = list(country.leagues.filter(
        is_active=True, catalog_season=season_label(season_start())
    ).order_by("tier", "name"))
    if not {1, 2}.issubset({item.tier for item in items}):
        return _error("The current season has fewer than two supported leagues.", 503)
    return JsonResponse({
        "leagues": [{
            "id": x.id, "name": x.name, "tier": x.tier,
            "provider": x.provider,
        } for x in items],
    })


@login_required
@require_GET
@never_cache
def clubs(request):
    code = request.GET.get("country", "").strip().upper()
    league_id = request.GET.get("league", "")
    if code not in ("GB", "DE") or not league_id.isdecimal():
        return _error("Choose a valid country and league.")
    league = get_object_or_404(
        League.objects.select_related("country"),
        pk=int(league_id), country__code=code, country__is_active=True,
        is_active=True, catalog_season=season_label(season_start()),
    )
    warning = None
    try:
        sync_league_teams(league)
    except CatalogUnavailable:
        if not league.clubs.filter(is_active=True).exists():
            return _error(
                "The current club list could not be loaded from its public source. "
                "Please try again later.",
                status=503,
            )
        warning = (
            "The live source is unavailable. This saved club list may be outdated."
        )
    results = league.clubs.filter(is_active=True).order_by("name")
    return JsonResponse({
        "clubs": [
            {"id": item.pk, "name": item.name, "manual": item.is_manual}
            for item in results
        ],
        "warning": warning,
    })


@login_required
@require_GET
@never_cache
def selection(request):
    code = request.GET.get("country", "").strip().upper()
    league_id = request.GET.get("league", "")
    club_id = request.GET.get("club", "")
    if code not in ("GB", "DE") or not league_id.isdecimal() or not club_id.isdecimal():
        return _error("Choose a country, league and club.")
    club = get_object_or_404(
        Club.objects.select_related("league__country"),
        pk=int(club_id), is_active=True,
        league_id=int(league_id), league__is_active=True,
        league__catalog_season=season_label(season_start()),
        league__country__code=code, league__country__is_active=True,
    )
    return JsonResponse({
        "selection": {
            "country": club.league.country.name,
            "country_code": club.league.country.code,
            "league": club.league.name,
            "league_id": club.league_id,
            "club": club.name,
            "club_id": club.id,
            "source": club.provider,
        },
        "job_enabled": False,  # FS-011c #26 creates persistent jobs later.
    })


@login_required
@require_POST
@never_cache
def create_manual_club(request):
    """Create a club in the chosen league; no API data may be overwritten.

    CSRF is enforced by Django middleware. The selected country is verified
    against the league even if a caller forges or edits the HTML form.
    """
    form = ManualClubForm(request.POST)
    if not form.is_valid():
        return _error("Enter a valid club name, country and league.")
    code = form.cleaned_data["country"]
    league_id = form.cleaned_data["league"]
    name = form.cleaned_data["name"]
    league = get_object_or_404(
        League.objects.select_related("country"),
        pk=league_id,
        country__code=code, country__is_active=True, is_active=True,
        catalog_season=season_label(season_start()),
    )
    if Club.objects.filter(league=league, name__iexact=name).exists():
        return _error(
            "This club already exists in the selected league. Choose it from the list.",
            409,
        )
    try:
        with transaction.atomic():
            club = Club.objects.create(
                league=league, name=name, provider="manual",
                provider_id="", is_manual=True, is_active=True,
            )
    except IntegrityError:
        # Case-insensitive database constraint prevents concurrent duplicates.
        return _error(
            "This club already exists in the selected league. Choose it from the list.",
            409,
        )
    return JsonResponse({
        "club": {"id": club.pk, "name": club.name, "manual": True},
        "country": code,
        "league_id": league.pk,
    }, status=201)
