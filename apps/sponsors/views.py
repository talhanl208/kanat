from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.constants import CATEGORY_LABELS
from apps.core.permissions import profile_required, role_required, verified_required
from apps.core.ratelimit import ratelimit
from apps.core.strength import sponsor_strength
from apps.core.utils import apply_search
from apps.core.verification import auto_verify_sponsor
from apps.matching.engine import recommend_projects
from apps.matching.models import Block, MentorSession, SupportRequest
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.models import Project
from apps.rankings.models import PointEntry
from apps.rankings.services import (
    VALID, badges_for, held_points, leaderboard, resolve_period, title_for, total_points,
)

from .forms import CallFilterForm, SponsorCallForm, SponsorFilterForm, SponsorForm
from .models import Sponsor, SponsorCall


def sponsor_list(request):
    form = SponsorFilterForm(request.GET or None)
    qs = Sponsor.objects.filter(owner__is_active=True).with_load()
    if form.is_valid():
        data = form.cleaned_data
        qs = apply_search(qs, data["q"])
        if data["lig"]:
            qs = qs.filter(league=data["lig"])
        sponsors = list(qs)
        # JSON alanlarında veritabanından bağımsız filtreleme (SQLite/PostgreSQL uyumlu)
        if data["destek"]:
            sponsors = [s for s in sponsors if data["destek"] in (s.support_types or [])]
        if data["alan"]:
            sponsors = [
                s for s in sponsors
                if not s.interest_categories or data["alan"] in s.interest_categories
            ]
    else:
        sponsors = list(qs)
    sponsors.sort(key=lambda s: (not s.can_receive_requests, not s.verified, s.name))
    page = Paginator(sponsors, 18).get_page(request.GET.get("sayfa"))
    params = request.GET.copy()
    params.pop("sayfa", None)
    return render(request, "sponsors/list.html", {
        "form": form, "page": page, "querystring": params.urlencode(),
    })


def sponsor_detail(request, slug):
    sponsor = get_object_or_404(Sponsor.objects.filter(owner__is_active=True), slug=slug)
    points = total_points(sponsor)
    supported = (
        SupportRequest.objects.filter(sponsor=sponsor, status__in=["anlasma", "tamamlandi"])
        .select_related("project__team")
    )
    thanks = [r for r in supported if r.thanks_public and r.thanks_note]
    team = request.user.team_or_none if request.user.is_authenticated else None
    return render(request, "sponsors/detail.html", {
        "sponsor": sponsor,
        "points": points,
        "title": title_for(points),
        "badges": badges_for(sponsor),
        "supported": supported,
        "thanks": thanks,
        "awards": sponsor.awards.all()[:6],
        "calls": sponsor.calls.open(),
        "blocked": bool(team and Block.exists_between(team, sponsor)),
    })


@role_required("destekci")
def sponsor_edit(request):
    sponsor = getattr(request.user, "sponsor", None)
    form = SponsorForm(request.POST or None, request.FILES or None, instance=sponsor)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.owner = request.user
        obj.save()
        was_verified = obj.verified
        if auto_verify_sponsor(obj) and not was_verified:
            messages.success(request, "E-posta alan adın web sitenle eşleşti; profilin doğrulandı.")
        messages.success(request, "Destekçi profilin kaydedildi. Sana uygun projeleri listeledik.")
        return redirect("core:dashboard")
    return render(request, "sponsors/form.html", {"form": form, "creating": sponsor is None})


@profile_required
def sponsor_dashboard(request):
    sponsor = request.user.sponsor
    month = resolve_period("ay")
    board = leaderboard(month, limit=200)
    my_rank = next((row.rank for row in board if row.pk == sponsor.pk), None)
    month_points = sponsor.points.filter(
        VALID, created_at__date__gte=month.start, created_at__date__lt=month.end
    ).aggregate(t=Sum("points"))["t"] or 0
    points = total_points(sponsor)
    requests_qs = (
        SupportRequest.objects.filter(sponsor=sponsor)
        .select_related("project__team").order_by("-created_at")
    )
    calls = list(sponsor.calls.order_by("-created_at")[:5])
    return render(request, "sponsors/dashboard.html", {
        "sponsor": sponsor,
        "recommendations": recommend_projects(sponsor, limit=6),
        "incoming": [r for r in requests_qs if r.status == "beklemede" and r.initiated_by == "takim"],
        "requests": requests_qs[:8],
        "points": points,
        "held": held_points(sponsor),
        "month_points": month_points,
        "my_rank": my_rank,
        "period": month,
        "title": title_for(points),
        "badges": badges_for(sponsor),
        "strength": sponsor_strength(sponsor),
        "calls": calls,
        "active_load": sponsor.active_project_count,
    })


# --------------------------------------------------------------------------- #
# Etki raporu (kurumsal sosyal sorumluluk raporlarına hazır özet)
# --------------------------------------------------------------------------- #
@role_required("destekci")
@profile_required
def impact_report(request):
    sponsor = request.user.sponsor
    today = timezone.localdate()
    first = sponsor.requests.filter(status="tamamlandi").order_by("completed_at").first()
    first_year = first.completed_at.year if first and first.completed_at else today.year
    try:
        year = int(request.GET.get("yil", today.year))
    except ValueError:
        year = today.year
    year = min(max(year, first_year), today.year)

    completed = list(
        sponsor.requests.filter(status="tamamlandi", completed_at__year=year)
        .select_related("project__team").order_by("completed_at")
    )
    teams = {r.project.team_id: r.project.team for r in completed}
    cities = Counter(t.city for t in teams.values())
    categories = Counter(CATEGORY_LABELS.get(r.project.category, r.project.category) for r in completed)
    total_value = sum((r.delivered_value or r.amount or Decimal(0)) for r in completed)
    mentor_hours = MentorSession.objects.filter(
        request__sponsor=sponsor, confirmed_at__isnull=False, date__year=year
    ).aggregate(h=Sum("hours"))["h"] or 0
    year_points = sponsor.points.filter(VALID, created_at__year=year)
    first_time = year_points.filter(kind=PointEntry.Kind.FIRST_TEAM).count()
    co_funded = year_points.filter(kind=PointEntry.Kind.CO_FUND).count()
    ratings = [r.rating for r in completed if r.rating]

    def rows(counter):
        top = max(counter.values()) if counter else 1
        return [(label, n, round(100 * n / top)) for label, n in counter.most_common()]

    return render(request, "sponsors/impact.html", {
        "sponsor": sponsor, "year": year, "years": list(range(today.year, first_year - 1, -1)),
        "completed": completed, "team_count": len(teams), "cities": rows(cities),
        "categories": rows(categories), "total_value": total_value,
        "mentor_hours": mentor_hours, "first_time": first_time, "co_funded": co_funded,
        "points": year_points.aggregate(t=Sum("points"))["t"] or 0,
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "thanks": [r for r in completed if r.thanks_note],
        "awards": sponsor.awards.filter(period__startswith=str(year)),
        "generated": timezone.now(),
    })


# --------------------------------------------------------------------------- #
# Destek çağrıları
# --------------------------------------------------------------------------- #
def call_list(request):
    form = CallFilterForm(request.GET or None)
    calls = list(SponsorCall.objects.open().select_related("sponsor").order_by("deadline"))
    if form.is_valid():
        if form.cleaned_data["destek"]:
            calls = [c for c in calls if c.kind == form.cleaned_data["destek"]]
        if form.cleaned_data["alan"]:
            calls = [c for c in calls if c.accepts_category(form.cleaned_data["alan"])]
    calls = [c for c in calls if c.slots_left > 0]
    return render(request, "sponsors/call_list.html", {"form": form, "calls": calls})


def call_detail(request, pk):
    call = get_object_or_404(SponsorCall.objects.select_related("sponsor__owner"), pk=pk)
    is_owner = request.user.is_authenticated and call.sponsor.owner_id == request.user.pk
    if not call.sponsor.owner.is_active:
        raise Http404
    context = {"call": call, "is_owner": is_owner}
    team = request.user.team_or_none if request.user.is_authenticated else None
    if team is not None:
        from apps.matching.forms import CallApplyForm

        context["blocked"] = Block.exists_between(team, call.sponsor)
        context["my_application"] = call.applications.filter(project__team=team).first()
        context["apply_form"] = CallApplyForm(team=team, call=call)
    if is_owner:
        context["applications"] = call.applications.select_related("project__team").order_by("-match_score")
    return render(request, "sponsors/call_detail.html", context)


def _notify_matching_teams(call) -> int:
    from apps.notifications.services import captain_users

    projects = (Project.objects.public().select_related("team__owner").prefetch_related("needs")
                .exclude(team__blocks__sponsor=call.sponsor))
    if call.categories:
        projects = projects.filter(category__in=call.categories)
    sent, seen = 0, set()
    for project in projects[:300]:
        if call.kind not in project.need_kinds or project.team_id in seen:
            continue
        seen.add(project.team_id)
        notify(captain_users(project.team), Notification.Kind.CALL,
               f"Projene uygun bir destek çağrısı: {call.title}",
               f"{call.sponsor.name}, son başvuru {call.deadline:%d.%m.%Y}.",
               url=call.get_absolute_url(), email=False)
        sent += 1
        if sent >= 100:
            break
    return sent


@role_required("destekci")
@verified_required
@profile_required
@ratelimit("call-create", limit=5, window=86400)
def call_create(request):
    sponsor = request.user.sponsor
    form = SponsorCallForm(request.POST or None, sponsor=sponsor)
    if request.method == "POST" and form.is_valid():
        call = form.save(commit=False)
        call.sponsor = sponsor
        call.save()
        reached = _notify_matching_teams(call)
        messages.success(request, f"Çağrın yayında. Uygun {reached} takıma haber verdik.")
        return redirect(call)
    return render(request, "sponsors/call_form.html", {"form": form, "creating": True})


@role_required("destekci")
@profile_required
def call_edit(request, pk):
    call = get_object_or_404(SponsorCall, pk=pk, sponsor=request.user.sponsor)
    form = SponsorCallForm(request.POST or None, instance=call, sponsor=call.sponsor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Çağrı güncellendi.")
        return redirect(call)
    return render(request, "sponsors/call_form.html", {"form": form, "creating": False, "call": call})


@role_required("destekci")
@require_POST
def call_close(request, pk):
    call = get_object_or_404(SponsorCall, pk=pk, sponsor=request.user.sponsor_or_none)
    call.status = SponsorCall.Status.CLOSED
    call.save(update_fields=["status"])
    messages.info(request, "Çağrı başvurulara kapatıldı.")
    return redirect(call)
