"""Hesap yaşam döngüsü: kayıt, e-posta doğrulama, rıza kayıtları, veri dışa aktarma, silme."""
from __future__ import annotations

import hashlib
import secrets
import uuid

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.core.legal import version_of
from apps.core.utils import request_ip_hash

from . import totp
from .models import ConsentRecord, RecoveryCode, User

VERIFY_SALT = "kanat.email-verify.v1"
EMAIL_CHANGE_MAX_AGE = 60 * 60 * 24


# --------------------------------------------------------------------------- #
# Rıza
# --------------------------------------------------------------------------- #
def record_consent(request, user, kind: str, granted: bool) -> ConsentRecord:
    doc_slug = {"yas": "kullanim"}.get(kind, kind)
    return ConsentRecord.objects.create(
        user=user, kind=kind, version=version_of(doc_slug), granted=granted,
        ip_hash=request_ip_hash(request),
    )


REQUIRED_DOCUMENTS = ("aydinlatma", "kullanim")


def outdated_consents(user) -> list[str]:
    """Kullanıcının en son onayladığı sürümü güncel olmayan zorunlu metinler."""
    if user.is_staff and not (user.is_team or user.is_sponsor):
        return []
    outdated = []
    for kind in REQUIRED_DOCUMENTS:
        last = ConsentRecord.objects.filter(user=user, kind=kind, granted=True).order_by("-created_at", "-id").first()
        if last is None or last.version != version_of(kind):
            outdated.append(kind)
    return outdated


# --------------------------------------------------------------------------- #
# E-posta doğrulama
# --------------------------------------------------------------------------- #
def _email_fingerprint(email: str) -> str:
    # Bağlantıda (ve sunucu günlüklerinde) e-posta adresi açık görünmesin diye özet kullanılır.
    return hashlib.sha256(email.lower().encode()).hexdigest()[:20]


def make_verify_token(user: User) -> str:
    return signing.dumps({"u": user.pk, "e": _email_fingerprint(user.email)}, salt=VERIFY_SALT)


def read_verify_token(token: str) -> User | None:
    try:
        data = signing.loads(token, salt=VERIFY_SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired da bunun alt sınıfı
        return None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    # E-posta değiştiyse eski bağlantı geçersiz olur.
    if user is None or _email_fingerprint(user.email) != data.get("e"):
        return None
    return user


def send_verification_email(request, user: User) -> None:
    link = request.build_absolute_uri(reverse("accounts:verify", args=[make_verify_token(user)]))
    body = render_to_string("accounts/email/verify.txt", {"user": user, "link": link})
    send_mail(f"{settings.KANAT['SITE_NAME']} — e-postanı doğrula", body, None, [user.email])


def send_existing_account_notice(request, email: str) -> None:
    """Hesap numaralandırmayı engellemek için: kayıtlı e-postaya bilgi verilir, ekranda fark yoktur."""
    link = request.build_absolute_uri(reverse("accounts:password_reset"))
    body = render_to_string("accounts/email/existing.txt", {"link": link})
    send_mail(f"{settings.KANAT['SITE_NAME']} — kayıt denemesi", body, None, [email])


# --------------------------------------------------------------------------- #
# E-posta değiştirme: bağlantı YENİ adrese gider, eski adrese bilgi verilir
# --------------------------------------------------------------------------- #
def _change_key(token: str) -> str:
    return "eposta-degisim:" + hashlib.sha256(token.encode()).hexdigest()


def send_email_change_link(request, user: User, new_email: str) -> None:
    # Bağlantı rastgele bir belirteç taşır; adresler URL'de değil, sunucu tarafında saklanır.
    token = secrets.token_urlsafe(32)
    cache.set(_change_key(token), {"u": user.pk, "old": user.email, "new": new_email},
              timeout=EMAIL_CHANGE_MAX_AGE)
    link = request.build_absolute_uri(reverse("accounts:email_change_confirm", args=[token]))
    body = render_to_string("accounts/email/email_change.txt", {"user": user, "link": link})
    send_mail(f"{settings.KANAT['SITE_NAME']} — yeni e-posta adresini doğrula", body, None, [new_email])


def apply_email_change(token: str) -> tuple[User | None, str]:
    """(kullanıcı, hata mesajı) döner."""
    data = cache.get(_change_key(token))
    if not data:
        return None, "Bağlantı geçersiz ya da süresi dolmuş."
    cache.delete(_change_key(token))  # tek kullanımlık
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or user.email != data.get("old"):
        return None, "Bu bağlantı artık geçerli değil."
    new = data.get("new", "")
    if User.objects.filter(email=new).exists():
        return None, "Bu e-posta adresi başka bir hesapta kullanılıyor."
    old = user.email
    user.email, user.email_verified = new, True
    user.save(update_fields=["email", "email_verified"])
    body = render_to_string("accounts/email/email_changed_notice.txt", {"user": user, "new": new})
    send_mail(f"{settings.KANAT['SITE_NAME']} — e-posta adresin değişti", body, None, [old],
              fail_silently=True)
    from apps.core.verification import auto_verify_for_user

    auto_verify_for_user(user)
    return user, ""


# --------------------------------------------------------------------------- #
# İki adımlı doğrulama
# --------------------------------------------------------------------------- #
def start_totp_setup(user: User) -> str:
    """Kurulum için yeni gizli anahtar üretir (henüz etkin değil)."""
    user.totp_secret = totp.new_secret()
    user.totp_enabled_at = None
    user.totp_last_counter = 0
    user.save(update_fields=["totp_secret", "totp_enabled_at", "totp_last_counter"])
    return user.totp_secret


@transaction.atomic
def enable_totp(user: User, code: str) -> list[str] | None:
    counter = totp.verify(user.totp_secret, code, user.totp_last_counter)
    if counter is None:
        return None
    user.totp_enabled_at = timezone.now()
    user.totp_last_counter = counter
    user.save(update_fields=["totp_enabled_at", "totp_last_counter"])
    return regenerate_recovery_codes(user)


def regenerate_recovery_codes(user: User) -> list[str]:
    codes = totp.new_recovery_codes()
    user.recovery_codes.all().delete()
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=user, code_hash=totp.hash_recovery_code(c)) for c in codes]
    )
    return codes


@transaction.atomic
def disable_totp(user: User) -> None:
    user.totp_secret = ""
    user.totp_enabled_at = None
    user.totp_last_counter = 0
    user.save(update_fields=["totp_secret", "totp_enabled_at", "totp_last_counter"])
    user.recovery_codes.all().delete()


def verify_second_factor(user: User, code: str) -> str | None:
    """Kod geçerliyse 'totp' ya da 'recovery', değilse None döner."""
    if not user.totp_enabled:
        return None
    # Aynı anda iki istek aynı kodu kullanamasın diye satır kilitlenir.
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        counter = totp.verify(locked.totp_secret, code, locked.totp_last_counter)
        if counter is not None:
            locked.totp_last_counter = counter
            locked.save(update_fields=["totp_last_counter"])
            user.totp_last_counter = counter
            return "totp"
        hashed = totp.hash_recovery_code(code)
        rc = RecoveryCode.objects.select_for_update().filter(
            user=locked, code_hash=hashed, used_at__isnull=True
        ).first()
        if rc is not None:
            rc.used_at = timezone.now()
            rc.save(update_fields=["used_at"])
            return "recovery"
    return None


# --------------------------------------------------------------------------- #
# Veri taşınabilirliği (KVKK md. 11)
# --------------------------------------------------------------------------- #
def _iso(value):
    return value.isoformat() if value else None


def export_user_data(user: User) -> dict:
    from apps.matching.models import Message, SupportRequest

    data: dict = {
        "olusturma_zamani": timezone.now().isoformat(),
        "hesap": {
            "e_posta": user.email,
            "ad_soyad": user.full_name,
            "rol": user.get_role_display(),
            "e_posta_dogrulandi": user.email_verified,
            "uyelik_tarihi": _iso(user.date_joined),
            "son_giris": _iso(user.last_login),
            "e_posta_bildirimleri": user.email_notifications,
            "iki_adimli_dogrulama": user.totp_enabled,
        },
        "onay_kayitlari": [
            {"tur": c.get_kind_display(), "surum": c.version, "verildi": c.granted,
             "zaman": _iso(c.created_at)}
            for c in user.consents.all()
        ],
    }
    membership = getattr(user, "team_membership", None)
    if membership is not None:
        data["takim_uyeligi"] = {"takim": membership.team.name, "katilma": _iso(membership.joined_at)}
    team = user.owned_team
    if team:
        data["takim"] = {
            "ad": team.name, "kurum": team.institution, "sehir": team.city,
            "uye_sayisi": team.member_count, "danisman": team.advisor_name,
            "hakkinda": team.about, "web": team.website,
            "projeler": [
                {
                    "baslik": p.title, "ozet": p.summary, "aciklama": p.description,
                    "alan": p.get_category_display(), "yarisma": p.get_competition_display(),
                    "ihtiyaclar": [
                        {"tur": n.get_kind_display(), "baslik": n.title, "detay": n.detail,
                         "tutar": str(n.estimated_cost) if n.estimated_cost else None,
                         "karsilandi": n.fulfilled}
                        for n in p.needs.all()
                    ],
                    "gunluk": [{"baslik": u.title, "metin": u.body, "zaman": _iso(u.created_at)}
                               for u in p.updates.all()],
                }
                for p in team.projects.all()
            ],
        }
    sponsor = user.sponsor_or_none
    if sponsor:
        data["destekci"] = {
            "ad": sponsor.name, "sektor": sponsor.sector, "sehir": sponsor.city,
            "web": sponsor.website, "hakkinda": sponsor.about,
            "destek_turleri": sponsor.support_type_labels, "ilgi_alanlari": sponsor.interest_labels,
            "anahtar_kelimeler": sponsor.offering_keywords,
            "puan_kayitlari": [
                {"tur": p.get_kind_display(), "puan": p.points, "zaman": _iso(p.created_at)}
                for p in sponsor.points.all()
            ],
        }
    data["destek_talepleri"] = [
        {"proje": r.project.title, "destekci": r.sponsor.name, "durum": r.get_status_display(),
         "tur": r.get_kind_display(), "not": r.note, "zaman": _iso(r.created_at)}
        for r in SupportRequest.for_user(user).select_related("project", "sponsor")
    ]
    data["gonderdigim_mesajlar"] = [
        {"talep": m.request_id, "metin": m.body, "zaman": _iso(m.created_at)}
        for m in Message.objects.filter(sender=user)
    ]
    data["bildirimler"] = [
        {"baslik": n.title, "metin": n.body, "zaman": _iso(n.created_at), "okundu": _iso(n.read_at)}
        for n in user.notifications.all()[:500]
    ]
    return data


def can_delete_account(user: User) -> tuple[bool, str]:
    team = user.owned_team
    if team is not None and team.memberships.exists():
        return False, ("Takımında başka üyeler var. Hesabını kapatmadan önce kaptanlığı bir üyeye devret "
                       "ya da üyeleri takımdan çıkar.")
    return True, ""


# --------------------------------------------------------------------------- #
# Hesap silme — kişisel veriler silinir/anonimleştirilir
# --------------------------------------------------------------------------- #
@transaction.atomic
def delete_account(user: User) -> None:
    from apps.matching.models import Message

    # Karşı tarafın gördüğü mesaj metinleri silinir; yazışmanın varlığı anonim kalır.
    Message.objects.filter(sender=user).update(body="[Bu mesaj, hesabını kapatan kullanıcı tarafından silindi.]")

    from apps.projects.models import TeamMembership

    TeamMembership.objects.filter(user=user).delete()
    user.notifications.all().delete()
    user.recovery_codes.all().delete()

    for related in ("team", "sponsor"):
        obj = getattr(user, related, None)
        if obj is not None:
            if obj.logo:
                obj.logo.delete(save=False)
            obj.delete()  # projeler, ihtiyaçlar, açık talepler zincirleme silinir;
            # sözleşmelerin anlık kopyaları yasal saklama süresi boyunca korunur.

    # Onay kayıtları, ispat amacıyla anonim hesaba bağlı olarak saklanır.
    user.email = f"silinmis-{uuid.uuid4().hex[:12]}@silinmis.invalid"
    user.full_name = "Silinmiş kullanıcı"
    user.is_active = False
    user.email_verified = False
    user.email_notifications = False
    user.totp_secret, user.totp_enabled_at = "", None
    user.set_unusable_password()
    user.save()
