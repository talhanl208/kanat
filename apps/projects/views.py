from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.constants import CITIES
from apps.core.models import AuditLog
from apps.core.permissions import captain_required, profile_required, role_required
from apps.core.ratelimit import hit, too_many
from apps.core.strength import team_strength
from apps.core.utils import apply_search
from apps.core.verification import auto_verify_team
from apps.matching.engine import recommend_sponsors, score_match
from apps.matching.models import Block, SupportRequest
from apps.notifications.models import Notification
from apps.notifications.services import captain_users, notify, team_users

from .forms import (
    DossierForm, InviteForm, NeedFormSet, ProgressUpdateForm, ProjectFilterForm, ProjectForm, TeamForm,
    TransferCaptainForm,
)
from .models import MAX_TEAM_MEMBERS, Project, Team, TeamInvite, TeamMembership


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


# --------------------------------------------------------------------------- #
# Herkese açık
# --------------------------------------------------------------------------- #
def project_list(request):
    form = ProjectFilterForm(request.GET or None)
    qs = Project.objects.public().select_related("team").prefetch_related("needs__contributions")
    if form.is_valid():
        data = form.cleaned_data
        qs = apply_search(qs, data["q"])
        if data["alan"]:
            qs = qs.filter(category=data["alan"])
        if data["yarisma"]:
            qs = qs.filter(competition=data["yarisma"])
        if data["ihtiyac"]:
            qs = qs.filter(needs__kind=data["ihtiyac"], needs__fulfilled=False).distinct()
        if data["sehir"] in CITIES:
            qs = qs.filter(team__city=data["sehir"])
    sponsor = request.user.sponsor_or_none if request.user.is_authenticated else None
    if sponsor:
        qs = qs.exclude(team__blocks__sponsor=sponsor)
    page = Paginator(qs, 12).get_page(request.GET.get("sayfa"))
    if sponsor:
        for project in page.object_list:
            project.match = score_match(project, sponsor)

    params = request.GET.copy()
    params.pop("sayfa", None)
    return render(request, "projects/list.html", {
        "form": form, "page": page, "cities": CITIES, "querystring": params.urlencode(),
    })


def project_detail(request, slug):
    project = get_object_or_404(
        Project.objects.select_related("team__owner").prefetch_related("needs__contributions", "updates"),
        slug=slug,
    )
    user = request.user
    is_member = project.team.is_member(user)
    if project.status == Project.Status.ARCHIVED and not is_member:
        return render(request, "errors/404.html", status=404)

    context = {
        "project": project, "is_member": is_member, "is_owner": is_member,
        "is_captain": project.team.is_captain(user),
    }
    sponsor = user.sponsor_or_none if user.is_authenticated else None
    if sponsor:
        context["blocked"] = Block.exists_between(project.team, sponsor)
        context["match"] = score_match(project, sponsor)
        context["open_request"] = SupportRequest.objects.filter(
            project=project, sponsor=sponsor, status__in=SupportRequest.OPEN_STATUSES
        ).first()
    if is_member:
        context["recommendations"] = recommend_sponsors(project, limit=4)
        context["update_form"] = ProgressUpdateForm()
        context["dossier_form"] = DossierForm()
    context["can_download"] = bool(project.dossier) and (
        is_member or (user.is_authenticated and (user.is_sponsor or user.is_staff)
                      and not context.get("blocked"))
    )
    context["supporters"] = (
        SupportRequest.objects.filter(project=project, status__in=["anlasma", "tamamlandi"])
        .select_related("sponsor")
    )
    return render(request, "projects/detail.html", context)


def team_detail(request, slug):
    team = get_object_or_404(Team.objects.filter(owner__is_active=True), slug=slug)
    projects = team.projects.exclude(status=Project.Status.ARCHIVED).prefetch_related("needs__contributions")
    return render(request, "projects/team_detail.html", {"team": team, "projects": projects})


# --------------------------------------------------------------------------- #
# Takım profili
# --------------------------------------------------------------------------- #
@role_required("takim")
def team_edit(request):
    user = request.user
    team = user.team_or_none
    if team is not None and not team.is_captain(user):
        messages.info(request, "Takım profilini kaptan düzenler.")
        return redirect("projects:members")
    form = TeamForm(request.POST or None, request.FILES or None, instance=team)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.owner = user
        obj.save()
        auto_verify_team(obj)
        messages.success(request, "Takım profilin kaydedildi.")
        if not obj.projects.exists():
            return redirect("projects:create")
        return redirect("core:dashboard")
    return render(request, "projects/team_form.html", {"form": form, "creating": team is None})


def _team_project(request, slug):
    # Nesne düzeyinde yetki: proje yalnızca kullanıcının takımında aranır (IDOR koruması).
    team = request.user.team_or_none
    if team is None:
        raise Http404
    return get_object_or_404(Project, slug=slug, team=team)


@role_required("takim")
@profile_required
def project_create(request):
    return _project_form(request, Project(team=request.user.team_or_none), creating=True)


@role_required("takim")
@profile_required
def project_edit(request, slug):
    return _project_form(request, _team_project(request, slug), creating=False)


def _project_form(request, project, creating):
    form = ProjectForm(request.POST or None, instance=project)
    formset = NeedFormSet(request.POST or None, instance=project, prefix="ihtiyac")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            project = form.save()
            formset.instance = project
            formset.save()
            project.refresh_search_index()
        messages.success(request, "Proje kaydedildi." if not creating else "Projen yayında!")
        return redirect(project.get_absolute_url())
    return render(request, "projects/project_form.html", {
        "form": form, "formset": formset, "creating": creating, "project": project,
    })


@captain_required
@require_POST
def project_status(request, slug):
    project = _team_project(request, slug)
    new_status = request.POST.get("status")
    if new_status in Project.Status.values:
        project.status = new_status
        project.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Proje durumu: {project.get_status_display()}.")
    return redirect(project.get_absolute_url())


@role_required("takim")
@require_POST
def update_create(request, slug):
    project = _team_project(request, slug)
    form = ProgressUpdateForm(request.POST)
    if form.is_valid():
        update = form.save(commit=False)
        update.project = project
        update.save()
        supporters = {r.sponsor for r in project.requests.filter(status__in=["anlasma", "tamamlandi"])
                      .select_related("sponsor__owner")}
        notify([s.owner for s in supporters], Notification.Kind.TEAM,
               f"{project.title}: proje günlüğünde yeni bir girdi", update.title,
               url=project.get_absolute_url() + "#gunluk", email=False)
        messages.success(request, "Günlüğe eklendi. Destekçilerin bunu görecek.")
    else:
        messages.error(request, "Başlık ve metin gerekli.")
    return redirect(project.get_absolute_url() + "#gunluk")


# --------------------------------------------------------------------------- #
# Sponsorluk dosyası (PDF)
# --------------------------------------------------------------------------- #
@role_required("takim")
@require_POST
def dossier_upload(request, slug):
    project = _team_project(request, slug)
    if hit("dossier-up", str(request.user.pk), limit=10, window=3600):
        return too_many(request)
    form = DossierForm(request.POST, request.FILES)
    if form.is_valid():
        old = project.dossier.name if project.dossier else None
        project.dossier.save(form.cleaned_data["dossier"].name, form.cleaned_data["dossier"], save=False)
        project.dossier_uploaded_at = timezone.now()
        project.save(update_fields=["dossier", "dossier_uploaded_at", "updated_at"])
        if old:
            project.dossier.storage.delete(old)
        messages.success(request, "Sponsorluk dosyan yüklendi. Yalnızca giriş yapmış destekçiler indirebilir.")
    else:
        for error in form.errors.get("dossier", []):
            messages.error(request, error)
    return redirect(project.get_absolute_url() + "#dosya")


@role_required("takim")
@require_POST
def dossier_delete(request, slug):
    project = _team_project(request, slug)
    if project.dossier:
        project.dossier.delete(save=False)
        project.dossier_uploaded_at = None
        project.save(update_fields=["dossier", "dossier_uploaded_at", "updated_at"])
        messages.info(request, "Sponsorluk dosyası kaldırıldı.")
    return redirect(project.get_absolute_url() + "#dosya")


@login_required
def dossier_download(request, slug):
    project = get_object_or_404(Project.objects.select_related("team"), slug=slug)
    if not project.dossier:
        raise Http404
    user = request.user
    if not project.team.is_member(user):
        if project.status == Project.Status.ARCHIVED:
            raise Http404
        if not (user.is_sponsor or user.is_staff):
            raise PermissionDenied
        if not user.email_verified:
            messages.warning(request, "Dosyayı indirmek için önce e-posta adresini doğrula.")
            return redirect("accounts:settings")
        sponsor = user.sponsor_or_none
        if sponsor is not None and Block.exists_between(project.team, sponsor):
            raise Http404
    if hit("dossier-dl", str(user.pk), limit=60, window=3600):
        return too_many(request)
    response = FileResponse(
        project.dossier.open("rb"), as_attachment=True, content_type="application/pdf",
        filename=f"{project.slug}-sponsorluk-dosyasi.pdf",
    )
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cache-Control"] = "private, no-store"
    return response


# --------------------------------------------------------------------------- #
# Takım üyeleri
# --------------------------------------------------------------------------- #
@role_required("takim")
@profile_required
def members(request):
    user = request.user
    team = user.team_or_none
    is_captain = team.is_captain(user)
    invite_form = InviteForm()
    transfer_form = TransferCaptainForm(team=team, user=user)

    if request.method == "POST":
        if not is_captain:
            raise PermissionDenied
        if "invite" in request.POST:
            if hit("team-invite", str(team.pk), limit=20, window=3600):
                return too_many(request)
            invite_form = InviteForm(request.POST)
            if invite_form.is_valid():
                email = invite_form.cleaned_data["email"]
                pending = team.invites.filter(accepted_at__isnull=True, expires_at__gt=timezone.now())
                existing_member = (email == team.owner.email
                                   or team.memberships.filter(user__email=email).exists())
                if existing_member:
                    invite_form.add_error("email", "Bu kişi zaten takımda.")
                elif team.memberships.count() + pending.count() >= MAX_TEAM_MEMBERS:
                    invite_form.add_error("email", f"Bir takımda en fazla {MAX_TEAM_MEMBERS} üye olabilir.")
                else:
                    pending.filter(email=email).delete()
                    invite, token = TeamInvite.create_for(team, email, user)
                    link = request.build_absolute_uri(reverse("projects:invite_accept", args=[token]))
                    body = render_to_string("accounts/email/invite.txt", {
                        "team": team, "inviter": user.full_name, "link": link,
                    })
                    send_mail(f"{settings.KANAT['SITE_NAME']} — {team.name} takımına davet", body, None,
                              [email], fail_silently=True)
                    audit(request, AuditLog.Action.TEAM_MEMBER, detail=f"davet takim={team.pk}")
                    messages.success(request, f"Davet {email} adresine gönderildi. 7 gün geçerli.")
                    return redirect("projects:members")
        elif "transfer" in request.POST:
            transfer_form = TransferCaptainForm(request.POST, team=team, user=user)
            if transfer_form.is_valid():
                membership = transfer_form.cleaned_data["member"]
                new_captain = membership.user
                with transaction.atomic():
                    membership.delete()
                    team.owner = new_captain
                    team.save(update_fields=["owner"])
                    TeamMembership.objects.create(team=team, user=user)
                auto_verify_team(team)
                audit(request, AuditLog.Action.TEAM_MEMBER, detail=f"kaptan_devri takim={team.pk}")
                notify(team_users(team), Notification.Kind.TEAM, f"{team.name}: yeni kaptan",
                       f"Takım kaptanlığı {new_captain.full_name} adlı üyeye devredildi.",
                       url=reverse("projects:members"), exclude=user)
                messages.success(request, f"Kaptanlık {new_captain.full_name} adlı üyeye devredildi.")
                return redirect("projects:members")

    return render(request, "projects/members.html", {
        "team": team, "is_captain": is_captain,
        "memberships": team.memberships.select_related("user"),
        "invites": team.invites.filter(accepted_at__isnull=True, expires_at__gt=timezone.now()),
        "invite_form": invite_form, "transfer_form": transfer_form, "max_members": MAX_TEAM_MEMBERS,
    })


@captain_required
@require_POST
def invite_cancel(request, pk):
    team = request.user.team_or_none
    get_object_or_404(TeamInvite, pk=pk, team=team, accepted_at__isnull=True).delete()
    messages.info(request, "Davet iptal edildi.")
    return redirect("projects:members")


@captain_required
@require_POST
def member_remove(request, pk):
    team = request.user.team_or_none
    membership = get_object_or_404(TeamMembership.objects.select_related("user"), pk=pk, team=team)
    removed = membership.user
    membership.delete()
    audit(request, AuditLog.Action.TEAM_MEMBER, detail=f"cikarildi takim={team.pk}")
    notify([removed], Notification.Kind.TEAM, f"{team.name} takımından çıkarıldın",
           "Yeni bir takım kurabilir ya da başka bir davete katılabilirsin.", url=reverse("core:dashboard"))
    messages.info(request, f"{removed.full_name} takımdan çıkarıldı.")
    return redirect("projects:members")


@role_required("takim")
@require_POST
def leave_team(request):
    membership = getattr(request.user, "team_membership", None)
    if membership is None:
        raise Http404
    team = membership.team
    membership.delete()
    audit(request, AuditLog.Action.TEAM_MEMBER, detail=f"ayrildi takim={team.pk}")
    notify(captain_users(team), Notification.Kind.TEAM, f"{request.user.full_name} takımdan ayrıldı",
           url=reverse("projects:members"))
    messages.info(request, f"{team.name} takımından ayrıldın.")
    return redirect("core:dashboard")


def invite_accept(request, token):
    invite = TeamInvite.find(token)
    context = {"invite": invite, "token": token}
    if invite is None:
        context["problem"] = "Bu davet bağlantısı geçersiz, kullanılmış ya da süresi dolmuş."
        return render(request, "projects/invite.html", context, status=404)
    team = invite.team
    if not request.user.is_authenticated:
        context["login_url"] = f"{reverse('accounts:login')}?next={request.path}"
        context["register_url"] = f"{reverse('accounts:register')}?rol=takim&next={request.path}"
        return render(request, "projects/invite.html", context)

    user = request.user
    problem = None
    if not user.is_team:
        problem = "Bu davet takım hesapları içindir; destekçi hesabıyla bir takıma katılamazsın."
    elif user.team_or_none is not None:
        problem = ("Zaten bu takımdasın." if user.team_or_none == team
                   else "Zaten bir takımdasın. Yeni takıma katılmak için önce mevcut takımından ayrıl.")
    elif user.email.lower() != invite.email:
        problem = (f"Bu davet {_mask_email(invite.email)} adresine gönderildi. "
                   "Daveti kabul etmek için o adresle giriş yap.")
    elif team.memberships.count() >= MAX_TEAM_MEMBERS:
        problem = "Takım üye sınırına ulaşmış."
    context["problem"] = problem

    if request.method == "POST" and problem is None:
        try:
            with transaction.atomic():
                TeamMembership.objects.create(team=team, user=user)
                invite.accepted_at = timezone.now()
                invite.save(update_fields=["accepted_at"])
        except IntegrityError:
            messages.error(request, "Zaten bir takımdasın.")
            return redirect("core:dashboard")
        audit(request, AuditLog.Action.TEAM_MEMBER, detail=f"katildi takim={team.pk}")
        notify(captain_users(team), Notification.Kind.TEAM, f"{user.full_name} takıma katıldı",
               url=reverse("projects:members"))
        messages.success(request, f"Hoş geldin! Artık {team.name} takımındasın.")
        return redirect("core:dashboard")
    return render(request, "projects/invite.html", context)


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
@profile_required
def team_dashboard(request):
    from apps.sponsors.models import SponsorCall

    team = request.user.team_or_none
    projects = list(team.projects.prefetch_related("needs__contributions").order_by("status", "-created_at"))
    active = [p for p in projects if p.status == Project.Status.ACTIVE and not p.is_expired]
    expired = [p for p in projects if p.status == Project.Status.ACTIVE and p.is_expired]
    focus = active[0] if active else None
    requests_qs = (
        SupportRequest.objects.filter(project__team=team)
        .select_related("project", "sponsor").order_by("-created_at")
    )
    calls = []
    if focus:
        calls = [c for c in SponsorCall.objects.open().select_related("sponsor")
                 .exclude(sponsor__blocks__team=team)[:30]
                 if c.accepts_category(focus.category) and c.kind in focus.need_kinds and c.slots_left][:3]
    return render(request, "projects/dashboard.html", {
        "team": team,
        "is_captain": team.is_captain(request.user),
        "projects": projects,
        "expired": expired,
        "focus_project": focus,
        "recommendations": recommend_sponsors(focus, limit=4) if focus else [],
        "incoming": [r for r in requests_qs if r.status == "beklemede" and r.initiated_by == "destekci"],
        "requests": requests_qs[:8],
        "strength": team_strength(team),
        "calls": calls,
    })
