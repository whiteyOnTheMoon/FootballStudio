"""Offline-only, authenticated confederation → association → league → club API.

No external request occurs when a user opens or changes a selection.
"""
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .catalog import season_label, season_start
from .forms import ManualClubForm
from .models import Club, Confederation, Country, League


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@login_required
@require_GET
@never_cache
def confederations(request):
    values = Confederation.objects.all().order_by("name")
    return JsonResponse({
        "confederations": [
            {"code": item.code, "name": item.name} for item in values
        ]
    })


@login_required
@require_GET
@never_cache
def countries(request):
    code = request.GET.get("confederation", "").strip().upper()
    if not code or len(code) > 10:
        return _error("Choose a confederation first.")
    confed = get_object_or_404(Confederation, code=code)
    available = Country.objects.filter(
        confederation=confed, is_active=True
    ).order_by("name")
    return JsonResponse({
        "countries": [{"code": item.code, "name": item.name} for item in available],
        "notice": "Association directory is stored locally; not all clubs have been verified.",
    })


@login_required
@require_GET
@never_cache
def leagues(request):
    code = request.GET.get("country", "").strip().upper()
    if not code or len(code) > 3:
        return _error("Choose a football association.")
    country = get_object_or_404(
        Country.objects.select_related("confederation"),
        code=code, is_active=True,
    )
    results = list(country.leagues.filter(is_active=True).order_by("tier", "name"))
    return JsonResponse({
        "association": country.name,
        "leagues": [{
            "id": x.pk, "name": x.name, "tier": x.tier,
            "coverage": x.coverage_status,
            "season": x.catalog_season,
            "clubs_available": x.clubs.filter(is_active=True).count(),
        } for x in results],
        "notice": (
            "This association has no domestic league. Consult the relevant cross-border system."
            if country.code == "LI" else (
                "League data for this association has not yet verified/imported. "
                "No placeholder leagues or clubs have been invented."
                if not results else
                "Some associations have only one national league or regional parallel divisions."
            )
        ),
    })


@login_required
@require_GET
@never_cache
def clubs(request):
    code = request.GET.get("country", "").strip().upper()
    league_id = request.GET.get("league", "").strip()
    if not code or not league_id.isdecimal():
        return _error("Choose a valid association and league.")
    league = get_object_or_404(
        League.objects.select_related("country"),
        pk=int(league_id), country__code=code,
        country__is_active=True, is_active=True,
    )
    results = list(league.clubs.filter(is_active=True).order_by("name"))
    warning = None
    if league.coverage_status != "snapshot":
        warning = (
            "Only a league reference is stored. Verified club membership has "
            "not yet been imported; please do not treat this as a full roster."
        )
    elif league.catalog_season != season_label(season_start()):
        warning = (
            f"The last imported club roster is for {league.catalog_season}; "
            "it may not reflect the current season."
        )
    return JsonResponse({
        "clubs": [
            {"id": item.pk, "name": item.name, "manual": item.is_manual}
            for item in results
        ],
        "coverage": league.coverage_status,
        "season": league.catalog_season or None,
        "source": league.source_url or None,
        "warning": warning,
    })


@login_required
@require_GET
@never_cache
def selection(request):
    code = request.GET.get("country", "").strip().upper()
    league_id = request.GET.get("league", "").strip()
    club_id = request.GET.get("club", "").strip()
    if not code or not league_id.isdecimal() or not club_id.isdecimal():
        return _error("Choose an association, league and club.")
    club = get_object_or_404(
        Club.objects.select_related("league__country__confederation"),
        pk=int(club_id), is_active=True,
        league_id=int(league_id), league__is_active=True,
        league__country__code=code, league__country__is_active=True,
    )
    return JsonResponse({
        "selection": {
            "confederation": (
                club.league.country.confederation.code
                if club.league.country.confederation else None
            ),
            "country": club.league.country.name,
            "country_code": club.league.country.code,
            "league": club.league.name,
            "league_id": club.league_id,
            "club": club.name,
            "club_id": club.pk,
            "source": club.provider,
        },
        "job_enabled": True,
    })


@login_required
@require_POST
@never_cache
def create_manual_club(request):
    """Optional fallback; the user is never *required* to supply missing club data."""
    form = ManualClubForm(request.POST)
    if not form.is_valid():
        return _error("Enter a valid club name, association and league.")
    code = form.cleaned_data["country"]
    league_id = form.cleaned_data["league"]
    name = form.cleaned_data["name"]
    league = get_object_or_404(
        League.objects.select_related("country"),
        pk=league_id, country__code=code,
        country__is_active=True, is_active=True,
    )
    if Club.objects.filter(league=league, name__iexact=name).exists():
        return _error("This club already exists in the league.", 409)
    try:
        with transaction.atomic():
            club = Club.objects.create(
                league=league, name=name, provider="manual",
                provider_id="", is_manual=True, is_active=True,
            )
    except IntegrityError:
        return _error("This club already exists in the league.", 409)
    return JsonResponse({
        "club": {"id": club.pk, "name": club.name, "manual": True},
        "country": code, "league_id": league.pk,
    }, status=201)
