from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.cache import cache_control

from apps.core.constants import LEAGUES
from apps.matching.models import SupportRequest
from apps.sponsors.models import Sponsor

from . import services
from .models import Award


def leaderboard(request):
    period_key = request.GET.get("donem", "ay")
    if period_key not in {"ay", "yil", "tum"}:
        period_key = "ay"
    league = request.GET.get("lig") or None
    if league not in dict(LEAGUES):
        league = None
    period = services.resolve_period(period_key)
    rows = services.leaderboard(period, league=league, limit=50)
    top = rows[0].total if rows else 0
    for row in rows:
        row.share = round(100 * row.total / top) if top else 0
        row.title = services.title_for(services.total_points(row))
    return render(request, "rankings/leaderboard.html", {
        "rows": rows, "period": period, "league": league, "leagues": LEAGUES,
        "rules": {
            "base": services.COMPLETION_BASE, "value_cap": services.VALUE_CAP,
            "first": services.FIRST_TEAM_BONUS, "fast": services.FAST_RESPONSE_BONUS,
            "fast_hours": services.FAST_RESPONSE_HOURS, "mentor": services.MENTOR_POINTS_PER_HOUR,
            "mentor_cap": services.MENTOR_MONTHLY_HOURS_CAP, "co_fund": services.CO_FUND_BONUS,
            "examples": [(v, services.value_points(v)) for v in (1000, 10000, 50000, 100000)],
        },
        "titles": list(reversed(services.TITLES)),
    })


def awards(request):
    latest = Award.objects.aggregate(m=Max("issued_at"))["m"]
    items = Award.objects.select_related("sponsor").filter(sponsor__owner__is_active=True)[:60]
    return render(request, "rankings/awards.html", {
        "awards": items, "latest": latest, "badges": services.BADGES,
    })


def certificate(request, code):
    award = get_object_or_404(Award.objects.select_related("sponsor"), code=code.upper()[:12])
    return render(request, "rankings/certificate.html", {"award": award})


def thanks_wall(request):
    items = (
        SupportRequest.objects.filter(status="tamamlandi", thanks_public=True)
        .exclude(thanks_note="").select_related("project__team", "sponsor")
        .order_by("-completed_at")[:60]
    )
    return render(request, "rankings/thanks.html", {"items": items})


@cache_control(max_age=3600, public=True)
def badge_svg(request, slug):
    """Destekçinin kendi sitesine koyabileceği unvan rozeti. Metinler şablonda kaçışlanır."""
    sponsor = get_object_or_404(Sponsor.objects.filter(owner__is_active=True), slug=slug)
    points = services.total_points(sponsor)
    svg = render_to_string("rankings/badge.svg", {
        "sponsor": sponsor, "title": services.title_for(points), "points": points,
    })
    response = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"  # başka sitelerde gösterilebilsin
    return response
