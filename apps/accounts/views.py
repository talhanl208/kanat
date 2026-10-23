import json
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.models import AuditLog
from apps.core.ratelimit import hit, is_limited, ratelimit, too_many
from apps.core.utils import client_ip, safe_next_url
from apps.core.verification import auto_verify_for_user

from . import services, totp
from .forms import (
    DeleteAccountForm, EmailChangeForm, LoginForm, MarketingConsentForm, NotificationPrefForm,
    ProfileForm, RegisterForm, TwoFactorCodeForm, TwoFactorDisableForm, TwoFactorEnableForm,
)
from .models import ConsentRecord, User

PENDING_2FA_KEYS = ("2fa_uid", "2fa_at", "2fa_next", "2fa_backend")


@ratelimit("register", limit=5, window=3600)
def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    role = request.GET.get("rol")
    initial = {"role": role} if role in (User.Role.TEAM, User.Role.SPONSOR) else {}
    form = RegisterForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if User.objects.filter(email=data["email"]).exists():
            # Hesap var mı yok mu ekranda belli etmiyoruz (hesap numaralandırmaya karşı).
            services.send_existing_account_notice(request, data["email"])
            return render(request, "accounts/verify_sent.html", {"email": data["email"]})
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=data["email"], password=data["password1"],
                    full_name=data["full_name"], role=data["role"],
                    adult_declared_at=timezone.now(),
                )
                for kind in ("aydinlatma", "kullanim", "yas"):
                    services.record_consent(request, user, kind, True)
                services.record_consent(request, user, "acik-riza", bool(data["marketing"]))
        except IntegrityError:  # eşzamanlı aynı e-posta ile kayıt
            return render(request, "accounts/verify_sent.html", {"email": data["email"]})
        audit(request, AuditLog.Action.REGISTER, user=user)
        services.send_verification_email(request, user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Hesabın oluşturuldu. E-postana gelen bağlantıyla adresini doğrula.")
        return redirect(safe_next_url(request, reverse("core:onboarding")))
    return render(request, "accounts/register.html", {"form": form, "next": request.GET.get("next", "")})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST":
        ip = client_ip(request)
        if hit("login-ip", ip, limit=20, window=600):
            return too_many(request)
        if form.is_valid():
            email = form.cleaned_data["email"]
            if is_limited("login-email", email, limit=5, window=900):
                return too_many(request)
            user = authenticate(request, email=email, password=form.cleaned_data["password"])
            if user is not None:
                target = safe_next_url(request, reverse("core:dashboard"))
                if user.totp_enabled:
                    # Parola doğru; oturumu henüz açmadan ikinci adımı iste.
                    request.session.cycle_key()
                    request.session.update({
                        "2fa_uid": user.pk, "2fa_at": int(time.time()), "2fa_next": target,
                        "2fa_backend": user.backend,
                    })
                    return redirect("accounts:login_2fa")
                login(request, user)  # oturum anahtarı yenilenir (session fixation koruması)
                audit(request, AuditLog.Action.LOGIN, user=user)
                return redirect(target)
            hit("login-email", email, limit=5, window=900)
            audit(request, AuditLog.Action.LOGIN_FAILED, user=None)
        # Hangi alanın yanlış olduğunu söylemiyoruz.
        error = "E-posta veya parola hatalı."
    return render(request, "accounts/login.html", {"form": form, "error": error,
                                                   "next": request.GET.get("next", "")})


def login_2fa(request):
    """Parola doğrulandıktan sonra TOTP ya da kurtarma kodu ister."""
    uid, started = request.session.get("2fa_uid"), request.session.get("2fa_at", 0)
    if not uid or time.time() - started > settings.TWO_FACTOR_LOGIN_TIMEOUT:
        for key in PENDING_2FA_KEYS:
            request.session.pop(key, None)
        messages.error(request, "Doğrulama süresi doldu. Lütfen yeniden giriş yap.")
        return redirect("accounts:login")
    user = User.objects.filter(pk=uid, is_active=True).first()
    if user is None or not user.totp_enabled:
        return redirect("accounts:login")
    form = TwoFactorCodeForm(request.POST or None)
    error = None
    if request.method == "POST":
        if hit("2fa-user", str(uid), limit=6, window=600):
            return too_many(request)
        if form.is_valid():
            method = services.verify_second_factor(user, form.cleaned_data["code"])
            if method:
                target = request.session.get("2fa_next") or reverse("core:dashboard")
                backend = request.session.get("2fa_backend")
                for key in PENDING_2FA_KEYS:
                    request.session.pop(key, None)
                login(request, user, backend=backend)
                request.session["otp_verified"] = True
                audit(request, AuditLog.Action.LOGIN, user=user, detail="2fa")
                if method == "recovery":
                    audit(request, AuditLog.Action.RECOVERY_CODE_USED, user=user)
                    left = user.recovery_codes.filter(used_at__isnull=True).count()
                    messages.warning(request, f"Kurtarma kodu kullandın. {left} kodun kaldı; "
                                              "gerekirse yenilerini oluştur.")
                return redirect(target)
            audit(request, AuditLog.Action.TWO_FACTOR_FAILED, user=user)
        error = "Kod hatalı ya da süresi geçmiş."
    return render(request, "accounts/login_2fa.html", {"form": form, "error": error})


@login_required
def two_factor(request):
    """İki adımlı doğrulamayı aç / kapat / kurtarma kodlarını yenile."""
    user = request.user
    context = {"next": request.GET.get("next", "")}
    if user.totp_enabled:
        disable_form = TwoFactorDisableForm(request.POST or None, user=user)
        if request.method == "POST" and "disable" in request.POST:
            if disable_form.is_valid() and services.verify_second_factor(user, disable_form.cleaned_data["code"]):
                services.disable_totp(user)
                request.session.pop("otp_verified", None)
                audit(request, AuditLog.Action.TWO_FACTOR_DISABLED)
                messages.info(request, "İki adımlı doğrulama kapatıldı.")
                return redirect("accounts:settings")
            messages.error(request, "Parola ya da kod hatalı.")
        if request.method == "POST" and "regenerate" in request.POST:
            regen_form = TwoFactorCodeForm(request.POST)
            if regen_form.is_valid() and services.verify_second_factor(user, regen_form.cleaned_data["code"]):
                context["recovery_codes"] = services.regenerate_recovery_codes(user)
            else:
                messages.error(request, "Kod hatalı.")
        context.update({
            "disable_form": disable_form,
            "regen_form": TwoFactorCodeForm(),
            "codes_left": user.recovery_codes.filter(used_at__isnull=True).count(),
        })
        return render(request, "accounts/two_factor.html", context)

    if request.method == "POST":
        form = TwoFactorEnableForm(request.POST)
        if form.is_valid() and user.totp_secret:
            codes = services.enable_totp(user, form.cleaned_data["code"])
            if codes is not None:
                request.session["otp_verified"] = True
                audit(request, AuditLog.Action.TWO_FACTOR_ENABLED)
                messages.success(request, "İki adımlı doğrulama açıldı.")
                context.update({"recovery_codes": codes, "just_enabled": True,
                                "continue_url": safe_next_url(request, reverse("accounts:settings"))})
                return render(request, "accounts/two_factor.html", context)
        messages.error(request, "Kod doğrulanamadı. Telefonunun saatinin doğru olduğundan emin ol ve yeniden dene.")
    else:
        services.start_totp_setup(user)
        form = TwoFactorEnableForm()
    issuer = settings.KANAT["SITE_NAME"]
    context.update({
        "setup_form": form,
        "secret": totp.grouped(user.totp_secret),
        "otpauth": totp.provisioning_uri(user.totp_secret, user.email, issuer),
    })
    return render(request, "accounts/two_factor.html", context)


@login_required
def two_factor_verify(request):
    """Oturum açıkken ikinci adımı yeniden doğrular (ör. yönetim paneline geçerken)."""
    if not request.user.totp_enabled:
        return redirect("accounts:two_factor")
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST":
        if hit("2fa-user", str(request.user.pk), limit=6, window=600):
            return too_many(request)
        if form.is_valid() and services.verify_second_factor(request.user, form.cleaned_data["code"]):
            request.session["otp_verified"] = True
            return redirect(safe_next_url(request, reverse("core:dashboard")))
        audit(request, AuditLog.Action.TWO_FACTOR_FAILED)
        messages.error(request, "Kod hatalı ya da süresi geçmiş.")
    return render(request, "accounts/two_factor_verify.html", {"form": form, "next": request.GET.get("next", "")})


@login_required
@ratelimit("email-change", limit=3, window=3600)
def email_change(request):
    form = EmailChangeForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        new = form.cleaned_data["new_email"]
        # Adres başka hesapta kayıtlıysa bunu ekranda belli etmiyoruz.
        if not User.objects.filter(email=new).exists():
            services.send_email_change_link(request, request.user, new)
        messages.info(request, f"{new} adresine bir onay bağlantısı gönderdik. Bağlantıya tıklayınca adresin değişecek.")
        return redirect("accounts:settings")
    return render(request, "accounts/email_change.html", {"form": form})


def email_change_confirm(request, token):
    user, error = services.apply_email_change(token)
    if user is None:
        messages.error(request, error)
    else:
        audit(request, AuditLog.Action.EMAIL_CHANGED, user=user)
        messages.success(request, "E-posta adresin güncellendi.")
    return redirect("accounts:settings" if request.user.is_authenticated else "accounts:login")


@login_required
def reconsent(request):
    """Aydınlatma metni ya da kullanım koşulları güncellenince yeniden onay."""
    from apps.core.legal import LEGAL_DOCUMENTS

    outdated = services.outdated_consents(request.user)
    if not outdated:
        return redirect("core:dashboard")
    if request.method == "POST" and all(request.POST.get(k) == "on" for k in outdated):
        for kind in outdated:
            services.record_consent(request, request.user, kind, True)
        audit(request, AuditLog.Action.CONSENT_CHANGED, detail="guncel-surum")
        messages.success(request, "Teşekkürler, güncel metinleri onayladın.")
        return redirect(safe_next_url(request, reverse("core:dashboard")))
    docs = [(k, LEGAL_DOCUMENTS[k]) for k in outdated]
    return render(request, "accounts/reconsent.html", {"docs": docs, "error": request.method == "POST"})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit(request, AuditLog.Action.LOGOUT)
    logout(request)
    messages.info(request, "Çıkış yaptın. Yine bekleriz.")
    return redirect("core:home")


def verify_email(request, token):
    user = services.read_verify_token(token)
    if user is None:
        messages.error(request, "Doğrulama bağlantısı geçersiz ya da süresi dolmuş. Yeni bağlantı iste.")
        return redirect("accounts:settings" if request.user.is_authenticated else "accounts:login")
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        audit(request, AuditLog.Action.EMAIL_VERIFIED, user=user)
        auto_verify_for_user(user)
    messages.success(request, "E-posta adresin doğrulandı.")
    return redirect("core:dashboard" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
@ratelimit("resend-verify", limit=3, window=3600)
def resend_verification(request):
    if not request.user.email_verified:
        services.send_verification_email(request, request.user)
    messages.info(request, "Doğrulama bağlantısı e-postana yeniden gönderildi.")
    return redirect("accounts:settings")


@login_required
def account_settings(request):
    user = request.user
    profile_form = ProfileForm(instance=user)
    consent_form = MarketingConsentForm(
        initial={"marketing": ConsentRecord.current(user, ConsentRecord.Kind.MARKETING)}
    )
    notif_form = NotificationPrefForm(initial={"email_notifications": user.email_notifications})
    if request.method == "POST":
        if "notifications" in request.POST:
            notif_form = NotificationPrefForm(request.POST)
            if notif_form.is_valid():
                user.email_notifications = notif_form.cleaned_data["email_notifications"]
                user.save(update_fields=["email_notifications"])
                messages.success(request, "Bildirim tercihin kaydedildi.")
                return redirect("accounts:settings")
        if "profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Bilgilerin güncellendi.")
                return redirect("accounts:settings")
        elif "consent" in request.POST:
            consent_form = MarketingConsentForm(request.POST)
            if consent_form.is_valid():
                wanted = consent_form.cleaned_data["marketing"]
                if wanted != ConsentRecord.current(user, ConsentRecord.Kind.MARKETING):
                    services.record_consent(request, user, "acik-riza", wanted)
                    audit(request, AuditLog.Action.CONSENT_CHANGED, detail=f"acik-riza={wanted}")
                messages.success(request, "Tercihin kaydedildi.")
                return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {
        "profile_form": profile_form,
        "consent_form": consent_form,
        "notif_form": notif_form,
        "consents": user.consents.all()[:20],
    })


@login_required
@ratelimit("export", limit=5, window=3600, methods=("GET", "POST"))
def export_data(request):
    payload = services.export_user_data(request.user)
    audit(request, AuditLog.Action.DATA_EXPORTED)
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8"
    )
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="kanat-verilerim-{stamp}.json"'
    return response


@login_required
def delete_account(request):
    allowed, reason = services.can_delete_account(request.user)
    form = DeleteAccountForm(request.POST or None, user=request.user)
    if not allowed:
        return render(request, "accounts/delete.html", {"form": form, "blocked_reason": reason})
    if request.method == "POST" and form.is_valid():
        user = request.user
        audit(request, AuditLog.Action.ACCOUNT_DELETED, user=user)
        services.delete_account(user)
        logout(request)
        messages.info(request, "Hesabın kapatıldı ve kişisel verilerin silindi.")
        return redirect("core:home")
    return render(request, "accounts/delete.html", {"form": form})


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/email/password_reset.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def post(self, request, *args, **kwargs):
        if hit("pw-reset", client_ip(request), limit=5, window=3600):
            return too_many(request)
        return super().post(request, *args, **kwargs)

    def get_extra_email_context(self):
        return {"site_name": settings.KANAT["SITE_NAME"]}


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:settings")

    def form_valid(self, form):
        response = super().form_valid(form)
        audit(self.request, AuditLog.Action.PASSWORD_CHANGED)
        messages.success(self.request, "Parolan değiştirildi.")
        return response
