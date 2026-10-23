"""
Destek talebi akışı:  talep → kabul → sözleşme (iki taraf parolayla onaylar) → teslim + teşekkür.

Güvenlik notları
- Her görünüm talebi `_get_request_for` ile alır: kullanıcı taraflardan biri değilse 404 döner
  (talebin varlığı bile sızdırılmaz — IDOR koruması). Takım tarafı = kaptan + üyeler.
- Bağlayıcı adımlar (sözleşme onayı, teslim onayı, mentörlük onayı) yalnızca takım kaptanınındır.
- Durum değiştiren tüm işlemler POST + CSRF ile yapılır.
- Mesajlar ve talepler için hız sınırı ve e-posta doğrulaması vardır.
- Engellenmiş taraflar arasında yeni talep ve mesaj yoktur.
"""
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.forms import PasswordConfirmForm
from apps.core.audit import audit
from apps.core.models import AuditLog
from apps.core.permissions import profile_required, verified_required
from apps.core.ratelimit import hit, ratelimit, too_many
from apps.core.utils import request_ip_hash
from apps.notifications.models import Notification
from apps.notifications.services import captain_users, notify, side_users, sponsor_users
from apps.projects.models import Project
from apps.rankings.services import award_completion, award_mentor_session
from apps.sponsors.models import Sponsor, SponsorCall

from .agreements import initial_for, save_agreement
from .engine import score_match
from .forms import (
    AgreementForm, CallApplyForm, CompleteForm, MentorSessionForm, MessageForm, ReportForm,
    SponsorOfferForm, TeamAskForm,
)
from .models import Agreement, Block, MentorSession, SupportRequest

S = SupportRequest.Status
OTHER = {"takim": "destekci", "destekci": "takim"}


def _get_request_for(user, pk) -> SupportRequest:
    req = get_object_or_404(
        SupportRequest.objects.select_related("project__team__owner", "sponsor__owner", "need", "call"),
        pk=pk,
    )
    if not req.is_participant(user):
        raise Http404
    return req


def _other_side(req, user):
    side = req.side_of(user)
    return side_users(req, OTHER[side]) if side else []


def _require_captain(request, req):
    if not req.is_team_captain(request.user):
        messages.warning(request, "Bu adımı takım kaptanı onaylar.")
        return redirect(req)
    return None


# --------------------------------------------------------------------------- #
# Talep oluşturma
# --------------------------------------------------------------------------- #
@verified_required
@profile_required
@ratelimit("request-create", limit=15, window=3600)
def offer_to_project(request, slug):
    """Destekçi → proje."""
    if not request.user.is_sponsor:
        raise Http404
    sponsor = request.user.sponsor
    project = get_object_or_404(Project.objects.public().select_related("team"), slug=slug)
    if Block.exists_between(project.team, sponsor):
        raise Http404
    existing = SupportRequest.objects.filter(
        project=project, sponsor=sponsor, status__in=SupportRequest.OPEN_STATUSES
    ).first()
    if existing:
        return redirect(existing)
    if sponsor.at_capacity:
        messages.warning(request, "Aynı anda çalışabileceğin takım sayısına ulaştın. Profilinden kapasiteni artırabilirsin.")
        return redirect(project)
    form = SponsorOfferForm(request.POST or None, sponsor=sponsor, project=project,
                            initial={"need": request.GET.get("ihtiyac")})
    if request.method == "POST" and form.is_valid():
        return _create(request, form, project, sponsor, SupportRequest.Initiator.SPONSOR)
    return render(request, "matching/request_form.html", {
        "form": form, "project": project, "sponsor": sponsor, "match": score_match(project, sponsor),
        "direction": "offer",
    })


@verified_required
@profile_required
@ratelimit("request-create", limit=15, window=3600)
def ask_sponsor(request, slug):
    """Takım → destekçi."""
    if not request.user.is_team:
        raise Http404
    team = request.user.team_or_none
    sponsor = get_object_or_404(Sponsor.objects.active().select_related("owner"), slug=slug)
    if Block.exists_between(team, sponsor):
        raise Http404
    if sponsor.at_capacity:
        messages.info(request, f"{sponsor.name} şu an kapasitesi dolu olduğu için yeni talep almıyor.")
        return redirect(sponsor)
    form = TeamAskForm(request.POST or None, team=team, sponsor=sponsor)
    if not form.fields["project"].queryset.exists():
        messages.info(request, "Destek istemek için önce destek arayan bir proje oluştur.")
        return redirect("projects:create")
    if request.method == "POST" and form.is_valid():
        project = form.cleaned_data["project"]
        existing = SupportRequest.objects.filter(
            project=project, sponsor=sponsor, status__in=SupportRequest.OPEN_STATUSES
        ).first()
        if existing:
            return redirect(existing)
        return _create(request, form, project, sponsor, SupportRequest.Initiator.TEAM)
    return render(request, "matching/request_form.html", {
        "form": form, "sponsor": sponsor, "direction": "ask",
    })


@verified_required
@profile_required
@require_POST
@ratelimit("request-create", limit=15, window=3600)
def call_apply(request, pk):
    """Takım → destek çağrısı."""
    if not request.user.is_team:
        raise Http404
    team = request.user.team_or_none
    call = get_object_or_404(SponsorCall.objects.open().select_related("sponsor__owner"), pk=pk)
    sponsor = call.sponsor
    if Block.exists_between(team, sponsor):
        raise Http404
    if not call.is_open:
        messages.info(request, "Bu çağrının kontenjanı doldu ya da süresi bitti.")
        return redirect(call)
    if call.applications.filter(project__team=team).exclude(status__in=[S.DECLINED, S.WITHDRAWN]).exists():
        messages.info(request, "Bu çağrıya zaten başvurdun.")
        return redirect(call)
    form = CallApplyForm(request.POST, team=team, call=call)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(call)
    project = form.cleaned_data["project"]
    if SupportRequest.objects.filter(project=project, sponsor=sponsor,
                                     status__in=SupportRequest.OPEN_STATUSES).exists():
        messages.info(request, "Bu proje ile bu destekçi arasında zaten açık bir süreç var.")
        return redirect(call)
    obj = form.save(commit=False)
    obj.kind, obj.call = call.kind, call
    obj.amount, obj.mentor_hours = call.amount_per_team, call.mentor_hours
    return _create(request, None, project, sponsor, SupportRequest.Initiator.TEAM, obj=obj)


def _create(request, form, project, sponsor, initiator, obj=None):
    obj = obj or form.save(commit=False)
    obj.project, obj.sponsor, obj.initiated_by = project, sponsor, initiator
    obj.match_score = score_match(project, sponsor).score
    try:
        with transaction.atomic():
            obj.save()
            receiver = "takim" if initiator == SupportRequest.Initiator.SPONSOR else "destekci"
            who = sponsor.name if receiver == "takim" else project.team.name
            title = (f"{who} projene destek teklif etti" if receiver == "takim"
                     else f"{who} senden destek istiyor")
            if obj.call_id:
                title = f"{who}, “{obj.call.title}” çağrına başvurdu"
            notify(side_users(obj, receiver), Notification.Kind.REQUEST, title,
                   f"{project.title}: {obj.get_kind_display().lower()}", url=obj.get_absolute_url())
    except IntegrityError:
        messages.info(request, "Bu proje ile bu destekçi arasında zaten açık bir talep var.")
        return redirect("matching:inbox")
    messages.success(request, "Talebin iletildi. Yanıt geldiğinde bildirim alacaksın.")
    return redirect(obj)


# --------------------------------------------------------------------------- #
# Gelen kutusu ve talep sayfası
# --------------------------------------------------------------------------- #
@profile_required
def inbox(request):
    reqs = (
        SupportRequest.for_user(request.user)
        .select_related("project__team", "sponsor").order_by("-created_at")
    )
    tab = request.GET.get("sekme", "acik")
    if tab == "acik":
        reqs = reqs.filter(status__in=SupportRequest.OPEN_STATUSES)
    elif tab == "kapali":
        reqs = reqs.exclude(status__in=SupportRequest.OPEN_STATUSES)
    return render(request, "matching/inbox.html", {"requests": reqs, "tab": tab})


@profile_required
def detail(request, pk):
    req = _get_request_for(request.user, pk)
    side = req.side_of(request.user)
    now = timezone.now()
    req.messages.filter(read_at__isnull=True).exclude(sender=request.user).update(read_at=now)
    request.user.notifications.filter(read_at__isnull=True, url=req.get_absolute_url()).update(read_at=now)
    agreement = Agreement.objects.filter(request=req).first()
    block = Block.objects.filter(team=req.project.team, sponsor=req.sponsor).first()
    team = req.project.team
    return render(request, "matching/detail.html", {
        "req": req,
        "side": side,
        "is_captain": req.is_team_captain(request.user),
        "thread": req.messages.select_related("sender"),
        "message_form": MessageForm(),
        "agreement": agreement,
        "sessions": req.sessions.all(),
        "session_form": MentorSessionForm(),
        "report_form": ReportForm(),
        "can_respond": req.status == S.PENDING and side == req.awaiting_response_from() and not block,
        "can_withdraw": req.status == S.PENDING and side == req.initiated_by,
        "can_message": req.status not in (S.DECLINED, S.WITHDRAWN) and not block,
        "block": block,
        "can_unblock": block is not None and block.blocked_by == side,
        "match": score_match(req.project, req.sponsor),
        "team_member_ids": {u.pk for u in team.all_users},
    })


@verified_required
@require_POST
def post_message(request, pk):
    req = _get_request_for(request.user, pk)
    if req.status in (S.DECLINED, S.WITHDRAWN) or req.is_blocked:
        raise Http404
    if hit("message-user", str(request.user.pk), limit=30, window=600):
        return too_many(request)
    form = MessageForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            msg = form.save(commit=False)
            msg.request, msg.sender = req, request.user
            msg.save()
            side = req.side_of(request.user)
            sender_name = req.sponsor.name if side == "destekci" else req.project.team.name
            recipients = _other_side(req, request.user)
            if side == "takim":  # takım arkadaşları da görsün (e-postasız)
                notify([u for u in req.project.team.all_users if u.pk != request.user.pk and u.is_active],
                       Notification.Kind.MESSAGE, f"{request.user.get_short_name()} {req.sponsor.name} ile yazıştı",
                       msg.body[:120], url=req.get_absolute_url(), email=False)
            notify(recipients, Notification.Kind.MESSAGE, f"{sender_name} sana yazdı",
                   msg.body[:120], url=req.get_absolute_url())
    else:
        messages.error(request, "Mesaj gönderilemedi: " + " ".join(form.errors.get("body", [])))
    return redirect(req.get_absolute_url() + "#mesajlar")


@verified_required
@require_POST
def respond(request, pk):
    req = _get_request_for(request.user, pk)
    if req.status != S.PENDING or req.side_of(request.user) != req.awaiting_response_from() or req.is_blocked:
        raise Http404
    decision = request.POST.get("karar")
    if decision == "kabul":
        if req.call_id and req.call.slots_left <= 0:
            messages.warning(request, "Bu çağrının kontenjanı dolu; önce başka bir başvuruyu kapat ya da kontenjanı artır.")
            return redirect(req)
        if req.side_of(request.user) == "destekci" and req.sponsor.at_capacity:
            messages.warning(request, "Kapasiten dolu. Profilinden 'aynı anda en fazla' sınırını artırabilirsin.")
            return redirect(req)
        req.status = S.ACCEPTED
        messages.success(request, "Talebi kabul ettin. Sıradaki adım: sözleşmeyi hazırlamak.")
        title = "Talebin kabul edildi"
    elif decision == "red":
        req.status = S.DECLINED
        messages.info(request, "Talebi kibarca reddettin.")
        title = "Talebin bu kez olumlu sonuçlanmadı"
    else:
        raise Http404
    req.responded_at = timezone.now()
    req.save(update_fields=["status", "responded_at"])
    notify(_other_side(req, request.user), Notification.Kind.RESPONSE, title,
           f"{req.project.title} ↔ {req.sponsor.name}", url=req.get_absolute_url())
    return redirect(req)


@require_POST
@profile_required
def withdraw(request, pk):
    req = _get_request_for(request.user, pk)
    if req.status != S.PENDING or req.side_of(request.user) != req.initiated_by:
        raise Http404
    req.status = S.WITHDRAWN
    req.save(update_fields=["status"])
    notify(_other_side(req, request.user), Notification.Kind.RESPONSE, "Bir talep geri çekildi",
           f"{req.project.title} ↔ {req.sponsor.name}", url=req.get_absolute_url(), email=False)
    messages.info(request, "Talebini geri çektin.")
    return redirect("matching:inbox")


# --------------------------------------------------------------------------- #
# Sözleşme
# --------------------------------------------------------------------------- #
@verified_required
@profile_required
def agreement_edit(request, pk):
    req = _get_request_for(request.user, pk)
    if req.status != S.ACCEPTED:
        messages.info(request, "Sözleşme yalnızca kabul edilmiş ve henüz onaylanmamış taleplerde düzenlenir.")
        return redirect(req)
    if req.side_of(request.user) == "takim" and (resp := _require_captain(request, req)):
        return resp
    agreement = Agreement.objects.filter(request=req).first()
    form = AgreementForm(
        request.POST or None, instance=agreement, initial=None if agreement else initial_for(req)
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            save_agreement(form, req)
            recipients = (captain_users(req.project.team) if req.side_of(request.user) == "destekci"
                          else sponsor_users(req.sponsor))
            notify(recipients, Notification.Kind.AGREEMENT, "Sözleşme onayını bekliyor",
                   f"{req.project.title} ↔ {req.sponsor.name}", url=reverse("matching:agreement", args=[req.pk]))
        messages.success(request, "Sözleşme kaydedildi. Şimdi iki tarafın da onaylaması gerekiyor.")
        return redirect("matching:agreement", pk=req.pk)
    return render(request, "matching/agreement_form.html", {"form": form, "req": req})


@profile_required
def agreement_view(request, pk):
    req = _get_request_for(request.user, pk)
    agreement = get_object_or_404(Agreement, request=req)
    side = req.side_of(request.user)
    my_approval = agreement.team_approved_at if side == "takim" else agreement.sponsor_approved_at
    return render(request, "matching/agreement.html", {
        "req": req, "agreement": agreement, "side": side, "my_approval": my_approval,
        "can_approve": side == "destekci" or req.is_team_captain(request.user),
        "confirm_form": PasswordConfirmForm(user=request.user),
    })


@verified_required
@require_POST
@ratelimit("agreement-approve", limit=10, window=900)
def agreement_approve(request, pk):
    req = _get_request_for(request.user, pk)
    agreement = get_object_or_404(Agreement, request=req)
    if req.status != S.ACCEPTED:
        raise Http404
    side = req.side_of(request.user)
    if side == "takim" and (resp := _require_captain(request, req)):
        return resp
    form = PasswordConfirmForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Onay için parolanı doğru gir.")
        return redirect("matching:agreement", pk=req.pk)
    # Kullanıcının gördüğü metin ile kayıttaki metin aynı mı? (araya değişiklik girmesine karşı)
    if request.POST.get("body_hash") != agreement.body_hash:
        messages.error(request, "Sözleşme sen okurken değişti. Lütfen güncel metni yeniden oku.")
        return redirect("matching:agreement", pk=req.pk)

    now, ip = timezone.now(), request_ip_hash(request)
    if side == "takim":
        agreement.team_approved_at, agreement.team_ip_hash = now, ip
    else:
        agreement.sponsor_approved_at, agreement.sponsor_ip_hash = now, ip
    with transaction.atomic():
        agreement.save()
        if agreement.fully_approved:
            req.status = S.AGREED
            req.save(update_fields=["status"])
            notify(side_users(req, "takim") + side_users(req, "destekci"), Notification.Kind.AGREEMENT,
                   "Sözleşme iki tarafça onaylandı", f"{req.project.title} ↔ {req.sponsor.name}",
                   url=req.get_absolute_url(), exclude=request.user)
        else:
            notify(_other_side(req, request.user), Notification.Kind.AGREEMENT,
                   "Karşı taraf sözleşmeyi onayladı, sıra sende",
                   f"{req.project.title} ↔ {req.sponsor.name}", url=reverse("matching:agreement", args=[req.pk]))
    audit(request, AuditLog.Action.AGREEMENT_APPROVED, detail=f"talep={req.pk}")
    messages.success(
        request,
        "Sözleşme iki tarafça onaylandı." if agreement.fully_approved else "Onayın kaydedildi. Karşı tarafın onayı bekleniyor.",
    )
    return redirect("matching:agreement", pk=req.pk)


# --------------------------------------------------------------------------- #
# Teslim, teşekkür ve mentörlük
# --------------------------------------------------------------------------- #
@verified_required
@profile_required
def complete(request, pk):
    req = _get_request_for(request.user, pk)
    if req.side_of(request.user) != "takim" or req.status != S.AGREED:
        raise Http404
    if resp := _require_captain(request, req):
        return resp
    # Parasal ihtiyaçlar, katkılar tutarı karşılayınca kendiliğinden kapanır; diğerlerini takım işaretler.
    preselect = [req.need_id] if req.need_id and not req.need.estimated_cost else []
    form = CompleteForm(request.POST or None, instance=req, initial={
        "delivered_value": req.amount, "fulfilled_needs": preselect,
    })
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.status = S.COMPLETED
            obj.completed_at = timezone.now()
            obj.save()
            form.cleaned_data["fulfilled_needs"].update(fulfilled=True)
            if obj.need_id:  # ortak kanat: katkılar tutarı karşıladıysa ihtiyaç kendiliğinden kapanır
                need = type(obj.need).objects.prefetch_related("contributions").get(pk=obj.need_id)
                if need.estimated_cost and need.delivered_amount >= need.estimated_cost:
                    type(need).objects.filter(pk=need.pk).update(fulfilled=True)
            entries = award_completion(obj)
            total = sum(e.points for e in entries if e.sponsor_id == obj.sponsor_id and not e.held)
            body = f"{req.project.team.name} desteğini teslim aldı"
            body += f" ve {total} Kanat puanı kazandın." if total else "."
            notify(sponsor_users(req.sponsor), Notification.Kind.COMPLETED, "Teşekkürler! Desteğin ulaştı",
                   body, url=req.get_absolute_url())
        messages.success(request, "Teşekkürün iletildi. Destekçin Kanat puanı kazandı.")
        return redirect(req)
    return render(request, "matching/complete.html", {"form": form, "req": req})


@verified_required
@require_POST
def session_add(request, pk):
    req = _get_request_for(request.user, pk)
    if req.side_of(request.user) != "destekci" or req.status not in (S.AGREED, S.COMPLETED):
        raise Http404
    form = MentorSessionForm(request.POST)
    if form.is_valid():
        session = form.save(commit=False)
        session.request = req
        session.save()
        notify(captain_users(req.project.team), Notification.Kind.MENTOR,
               "Mentörlük oturumu onayını bekliyor", f"{session.topic} ({session.hours} saat)",
               url=req.get_absolute_url() + "#mentorluk")
        messages.success(request, "Oturum kaydedildi; takım kaptanı onaylayınca puanı yansır.")
    else:
        messages.error(request, "Oturum kaydedilemedi: tarih, 0,5–8 saat arası süre ve konu gerekli.")
    return redirect(req.get_absolute_url() + "#mentorluk")


@verified_required
@require_POST
def session_confirm(request, pk, session_id):
    req = _get_request_for(request.user, pk)
    if req.side_of(request.user) != "takim":
        raise Http404
    if resp := _require_captain(request, req):
        return resp
    session = get_object_or_404(MentorSession, pk=session_id, request=req, confirmed_at__isnull=True)
    with transaction.atomic():
        session.confirmed_at = timezone.now()
        session.save(update_fields=["confirmed_at"])
        award_mentor_session(session)
    messages.success(request, "Mentörlük oturumunu onayladın.")
    return redirect(req.get_absolute_url() + "#mentorluk")


# --------------------------------------------------------------------------- #
# Şikâyet ve engelleme
# --------------------------------------------------------------------------- #
@require_POST
@profile_required
@ratelimit("report", limit=10, window=3600)
def report(request, pk):
    from apps.notifications.services import staff_users

    req = _get_request_for(request.user, pk)
    form = ReportForm(request.POST)
    if form.is_valid():
        rep = form.save(commit=False)
        rep.request, rep.reporter = req, request.user
        rep.save()
        audit(request, AuditLog.Action.REPORT, detail=f"talep={req.pk} neden={rep.reason}")
        urgent = rep.reason in ("cocuk", "taciz")
        notify(staff_users(), Notification.Kind.SYSTEM,
               ("ACİL şikâyet: " if urgent else "Yeni şikâyet: ") + rep.get_reason_display(),
               f"Talep #{req.pk}", url=reverse("admin:matching_report_changelist"), email=urgent)
        messages.success(request, "Şikâyetin yönetime iletildi. Gerekirse seninle iletişime geçeceğiz.")
    return redirect(req)


@require_POST
@profile_required
def block(request, pk):
    req = _get_request_for(request.user, pk)
    side = req.side_of(request.user)
    if side == "takim" and not req.is_team_captain(request.user):
        messages.warning(request, "Engelleme kararını takım kaptanı verir.")
        return redirect(req)
    with transaction.atomic():
        _, created = Block.objects.get_or_create(team=req.project.team, sponsor=req.sponsor,
                                                 defaults={"blocked_by": side})
        if created:
            # Açık ve henüz bağlayıcı olmayan süreçler kapanır; onaylı sözleşmeler etkilenmez.
            SupportRequest.objects.filter(project__team=req.project.team, sponsor=req.sponsor,
                                          status=S.PENDING).update(status=S.WITHDRAWN)
            SupportRequest.objects.filter(project__team=req.project.team, sponsor=req.sponsor,
                                          status=S.ACCEPTED).update(status=S.DECLINED)
    audit(request, AuditLog.Action.BLOCK, detail=f"talep={req.pk} taraf={side}")
    messages.info(request, "Engellendi. Artık birbirinize talep ya da mesaj gönderemezsiniz. "
                           "Ciddi bir sorun varsa şikâyet de bırakmanı öneririz.")
    return redirect(req)


@require_POST
@profile_required
def unblock(request, pk):
    req = _get_request_for(request.user, pk)
    side = req.side_of(request.user)
    if side == "takim" and not req.is_team_captain(request.user):
        raise Http404
    deleted, _ = Block.objects.filter(team=req.project.team, sponsor=req.sponsor, blocked_by=side).delete()
    if deleted:
        audit(request, AuditLog.Action.BLOCK, detail=f"kaldirildi talep={req.pk}")
        messages.info(request, "Engel kaldırıldı.")
    return redirect(req)
