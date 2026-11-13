"""Authenticated and owner-scoped M1 selection test jobs.

No worker is triggered and no external API is called. This deliberately
tests database persistence and the selected club's parent relationships.
"""
from decimal import Decimal
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app.clubs.models import Club

from .dossiers import load_fact_dossier
from .forms import TestJobForm
from .models import FactDossier, ProductionJob
from .safe_official_fetch import WebsiteFetchError, _checked_url


def as_public_data(job):
    return {
        "id": job.pk,
        "title": job.title,
        "language": job.language,
        "kind": job.kind,
        "status": job.status,
        "country_code": job.country_code,
        "league": job.league_name,
        "club": job.club_name,
        "club_id": job.club_id,
        "manual_market_value": (
            {
                "metric": "squad_total",
                "amount": format(job.manual_market_value_amount, ".2f"),
                "millions": format(job.manual_market_value_amount / Decimal("1000000"), ".2f"),
                "currency": job.manual_market_value_currency,
                "as_of": (
                    job.manual_market_value_as_of.isoformat()
                    if job.manual_market_value_as_of else None
                ),
                "source_url": job.manual_market_value_source_url or None,
                "provenance": "user_entered",
                "verification_state": "unverified",
            }
            if job.manual_market_value_amount is not None else None
        ),
        "error": job.error_message,
        "has_video": bool(job.output_path),
        "created_at": job.created_at.isoformat(),
    }


@login_required
@require_GET
@never_cache
def test_job_list(request):
    jobs = ProductionJob.objects.filter(owner=request.user)[:20]
    return JsonResponse({"jobs": [as_public_data(job) for job in jobs]})


@login_required
@require_POST
@never_cache
def create_test_job(request):
    form = TestJobForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            "error": "Check the club, title and optional market value (millions, date and HTTPS source)."
        }, status=400)
    payload = form.cleaned_data
    club = get_object_or_404(
        Club.objects.select_related("league__country"),
        pk=payload["club"], is_active=True,
        league_id=payload["league"], league__is_active=True,
        league__country__code=payload["country"],
        league__country__is_active=True,
    )
    job = ProductionJob(
        owner=request.user,
        club=club,
        title=payload["title"],
        language="en",
        kind=ProductionJob.Kind.PROTOTYPE,
        status=ProductionJob.Status.QUEUED,
        country_code=club.league.country.code,
        league_name=club.league.name,
        club_name=club.name,
        manual_market_value_amount=(
            payload["market_value_millions"] * Decimal("1000000")
            if payload["market_value_millions"] is not None else None
        ),
        manual_market_value_currency=payload["market_value_currency"] or "EUR",
        manual_market_value_as_of=payload["market_value_as_of"],
        manual_market_value_source_url=payload["market_value_source_url"],
    )
    job.full_clean()
    job.save()
    return JsonResponse({
        "job": as_public_data(job),
        "notice": "M1 selection test saved. Video generation is not active yet.",
    }, status=201)



def _safe_source_link(url):
    """Only show clickable, public-looking HTTPS references.

    The stored source URL is never fetched here. Everything else is displayed
    as escaped text, not a potentially unsafe hyperlink.
    """
    try:
        canonical, _host = _checked_url(url)
        return canonical if canonical == url else None
    except WebsiteFetchError:
        return None


@login_required
@require_GET
@never_cache
def research_dossier(request, job_id):
    """Read-only HTML overview of owner-scoped research and historical versions.

    Sources and reviews are *not* created by loading this page. It never
    fetches remote pages, starts workers, or promotes facts to verified.
    """
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    versions = list(
        FactDossier.objects.filter(job=job)
        .order_by("-version").values_list("version", flat=True)[:100]
    )
    raw_version = request.GET.get("version")
    if raw_version is None:
        selected_version = versions[0] if versions else None
    elif isinstance(raw_version, str) and re.fullmatch(r"[1-9][0-9]{0,8}", raw_version):
        selected_version = int(raw_version)
    else:
        raise Http404("No such dossier version.")

    if selected_version is not None and selected_version not in versions:
        versions.append(selected_version)
        versions.sort(reverse=True)

    snapshot = None
    if selected_version is not None:
        try:
            snapshot = load_fact_dossier(
                owner=request.user, job_id=job.pk, version=selected_version,
            )
        except FactDossier.DoesNotExist:
            raise Http404("No such dossier version.") from None

        references = {}
        for source in snapshot["sources"]:
            source["safe_link"] = _safe_source_link(source["url"])
            references[source["id"]] = source

        for fact in snapshot["facts"]:
            if isinstance(fact["value"], dict):
                fact["value_display"] = " · ".join(
                    f"{key}: {value}" for key, value in fact["value"].items()
                )
            elif fact["value"] is None:
                fact["value_display"] = "Keine strukturierte Angabe"
            else:
                fact["value_display"] = str(fact["value"])

            for evidence in fact["evidence"]:
                evidence["source"] = references.get(evidence["source_id"])

    can_propose_facts = (
        snapshot is not None
        and selected_version == (versions[0] if versions else None)
        and any(
            source["source_kind"] in ("club_official", "league_official")
            and source["access_state"] == "accessible"
            for source in snapshot["sources"]
        )
    )
    auto_research_imported = (
        snapshot is not None
        and selected_version == (versions[0] if versions else None)
        and any(
            source["source_kind"] == "wikidata"
            and source["title"].startswith("[auto] ")
            and source["external_id"].startswith("Q")
            for source in snapshot["sources"]
        )
    )
    has_stadium_fact = (
        snapshot is not None
        and any(fact["predicate"] == "stadium_name" for fact in snapshot["facts"])
    )
    player_candidates = []
    if snapshot is not None:
        for fact in snapshot["facts"]:
            if (
                fact["predicate"] != "club_player_candidate"
                or not isinstance(fact["value"], dict)
                or not isinstance(fact["value"].get("name"), str)
            ):
                continue
            evidence = fact["evidence"]
            linked = evidence[0].get("source") if evidence else None
            player_candidates.append({
                "name": fact["value"]["name"],
                "person_qid": fact["value"].get("person_qid", ""),
                "source_url": linked.get("safe_link") if isinstance(linked, dict) else None,
            })
    has_player_scan = (
        snapshot is not None
        and any(
            source["source_kind"] == "wikidata"
            and source["external_id"].startswith("auto-p54:Q")
            for source in snapshot["sources"]
        )
    )
    official_legends_compared = (
        snapshot is not None
        and any(
            source["source_kind"] == "club_official"
            and source["external_id"].startswith("auto-official-legends:Q")
            for source in snapshot["sources"]
        )
    )
    official_player_legends = []
    official_trainer_legends = []
    if snapshot is not None:
        for fact in snapshot["facts"]:
            value = fact.get("value")
            if (
                fact["predicate"] not in (
                    "official_player_legend_candidate",
                    "official_coach_legend_candidate",
                )
                or not isinstance(value, dict)
                or not isinstance(value.get("name"), str)
                or fact.get("verification_state") != "unverified"
            ):
                continue
            entry = {
                "name": value["name"],
                "source_url": (
                    fact["evidence"][0]["source"].get("safe_link")
                    if fact["evidence"] and isinstance(
                        fact["evidence"][0].get("source"), dict
                    ) else None
                ),
            }
            if fact["predicate"] == "official_player_legend_candidate":
                official_player_legends.append(entry)
            else:
                official_trainer_legends.append(entry)
    return render(request, "studio/research.html", {
        "official_legends_compared": official_legends_compared,
        "official_player_legends": official_player_legends,
        "official_trainer_legends": official_trainer_legends,
        "player_candidates": player_candidates,
        "has_player_scan": has_player_scan,
        "auto_research_imported": auto_research_imported,
        "has_stadium_fact": has_stadium_fact,
        "job": job,
        "versions": versions,
        "selected_version": selected_version,
        "latest_version": versions[0] if versions else None,
        "snapshot": snapshot,
        "can_propose_facts": can_propose_facts,
    })
