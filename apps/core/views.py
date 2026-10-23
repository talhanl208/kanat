from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.matching.models import SupportRequest
from apps.projects.models import Project, Team
from apps.sponsors.models import Sponsor

from .audit import audit
from .forms import StyledFormMixin, validate_https
from .legal import LEGAL_DOCUMENTS
from .models import AuditLog, DataRequest, VerificationRequest
from .quotes import QUOTES
from .ratelimit import ratelimit
from .verification import (
    auto_verify_for_user, domains_match, email_domain, is_edu_domain, website_host,
)


def home(request):
    from apps.rankings.services import leaderboard, resolve_period

    from apps.sponsors.models import SponsorCall

    period = resolve_period("ay")
    context = {
        "calls": [c for c in SponsorCall.objects.open().select_related("sponsor")[:12] if c.slots_left][:3],
        "projects": Project.objects.public().select_related("team").prefetch_related("needs")[:6],
        "stats": {
            "teams": Team.objects.filter(owner__is_active=True).count(),
            "sponsors": Sponsor.objects.filter(owner__is_active=True).count(),
            "completed": SupportRequest.objects.filter(status=SupportRequest.Status.COMPLETED).count(),
        },
        "top_sponsors": leaderboard(period, limit=3),
        "period": period,
        "quotes": QUOTES,
        "thanks": SupportRequest.objects.filter(
            status=SupportRequest.Status.COMPLETED, thanks_public=True
        ).exclude(thanks_note="").select_related("project__team", "sponsor")[:3],
    }
    return render(request, "core/home.html", context)


def about(request):
    return render(request, "core/about.html")


def legal(request, slug):
    doc = LEGAL_DOCUMENTS.get(slug)
    if doc is None:
        raise Http404
    return render(request, doc["template"], {"doc": doc, "slug": slug, "documents": LEGAL_DOCUMENTS})


class DataRequestForm(forms.ModelForm):
    identity_ack = forms.BooleanField(
        label="Başvurunun bana ait olduğunu ve kimliğimi doğrulamak için benimle iletişime "
        "geçilebileceğini biliyorum.",
        required=True,
    )

    class Meta:
        model = DataRequest
        fields = ["full_name", "email", "kind", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


@ratelimit("kvkk", limit=5, window=3600)
def data_request(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"full_name": request.user.full_name, "email": request.user.email}
    form = DataRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if request.user.is_authenticated:
            obj.user = request.user
        obj.save()
        messages.success(
            request,
            "Başvurun alındı. KVKK gereği en geç 30 gün içinde e-posta ile yanıtlanacak.",
        )
        return redirect("core:home")
    return render(request, "core/data_request.html", {"form": form})


class VerificationRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = VerificationRequest
        fields = ["evidence_url", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 5})}

    def clean_evidence_url(self):
        return validate_https(self.cleaned_data.get("evidence_url", ""))


@login_required
def verification(request):
    from apps.notifications.models import Notification
    from apps.notifications.services import notify, staff_users

    user = request.user
    if user.is_team and user.owned_team is None:
        if user.team_or_none is not None:
            messages.info(request, "Takımın doğrulamasını takım kaptanı yapar.")
            return redirect("core:dashboard")
        return redirect("core:onboarding")
    team, sponsor = user.owned_team, user.sponsor_or_none
    subject = team or sponsor
    if subject is None:
        return redirect("core:onboarding")
    auto_verify_for_user(user)
    subject.refresh_from_db()
    history = VerificationRequest.objects.filter(team=team, sponsor=sponsor)
    pending = history.filter(status=VerificationRequest.Status.PENDING).first()
    form = VerificationRequestForm(request.POST or None)
    if request.method == "POST" and not subject.verified and pending is None and form.is_valid():
        obj = form.save(commit=False)
        obj.user, obj.team, obj.sponsor = user, team, sponsor
        obj.save()
        audit(request, AuditLog.Action.VERIFICATION, detail=f"basvuru={obj.pk}")
        notify(staff_users(), Notification.Kind.VERIFY, f"Doğrulama başvurusu: {subject}",
               url=reverse("admin:core_verificationrequest_changelist"), email=False)
        messages.success(request, "Başvurun alındı. Yönetim inceleyince bildirim alacaksın.")
        return redirect("core:verification")
    domain = email_domain(user.email)
    return render(request, "core/verification.html", {
        "subject": subject, "is_team": team is not None, "form": form, "pending": pending,
        "history": history, "domain": domain, "email_verified": user.email_verified,
        "edu_ok": is_edu_domain(domain),
        "site_host": website_host(sponsor.website) if sponsor else "",
        "domain_ok": bool(sponsor and domains_match(domain, website_host(sponsor.website))),
    })


@require_GET
def health(request):
    """Yük dengeleyici / izleme için. Ayrıntı ya da sürüm bilgisi vermez."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status, code = "ok", 200
    except Exception:  # noqa: BLE001
        status, code = "veritabani-erisilemiyor", 503
    response = JsonResponse({"durum": status}, status=code)
    response["Cache-Control"] = "no-store"
    return response


@login_required
def dashboard(request):
    user = request.user
    if user.is_staff and not (user.is_team or user.is_sponsor):
        return redirect("admin:index")
    if user.is_team:
        from apps.projects.views import team_dashboard

        return team_dashboard(request)
    if user.is_sponsor:
        from apps.sponsors.views import sponsor_dashboard

        return sponsor_dashboard(request)
    raise Http404


@login_required
def onboarding(request):
    if request.user.is_team:
        return redirect("projects:team_edit")
    if request.user.is_sponsor:
        return redirect("sponsors:edit")
    return redirect("core:home")


@require_GET
@cache_control(max_age=86400, public=True)
def robots_txt(request):
    lines = [
        "User-agent: *",
        f"Disallow: /{settings.ADMIN_URL}",
        "Disallow: /hesap/",
        "Disallow: /eslesmeler/",
        "Allow: /",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


@require_GET
def security_txt(request):
    """RFC 9116 — güvenlik araştırmacıları için iletişim bilgisi."""
    expires = (timezone.now() + timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
    body = (
        f"Contact: mailto:{settings.KANAT['SECURITY_CONTACT']}\n"
        f"Expires: {expires}\n"
        "Preferred-Languages: tr, en\n"
        f"Policy: {settings.KANAT['SITE_URL'].rstrip('/')}/hakkinda/#guvenlik\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


# ---- Hata sayfaları -------------------------------------------------------- #
def bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    # Bağlam işlemcileri (veritabanı) çalıştırılmadan, en sade hâliyle.
    from django.template import loader

    return HttpResponse(loader.get_template("errors/500.html").render(), status=500)


def csrf_failure(request, reason=""):
    return render(request, "errors/403_csrf.html", status=403)
