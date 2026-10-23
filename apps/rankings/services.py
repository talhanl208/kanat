"""
Kanat puanı, unvanlar, rozetler ve ödüller.

Tasarım ilkeleri
- Puan yalnızca takımın onayladığı olaylardan doğar; destekçi kendine puan yazamaz.
- Parasal değer KAREKÖK ile ölçeklenir: 100.000 ₺ veren, 10.000 ₺ verenin 10 katı değil
  ~3 katı puan alır. Böylece KOBİ'ler ve mentörler de sıralamada görünür olur.
- Daha önce hiç destek almamış (doğrulanmış) takımı desteklemek ekstra puan kazandırır.
- Sıralama ligi: mikro, KOBİ ve büyük kurumlar ayrı listelerde de yarışır.

Hileye karşı
- Sıralamaya ve ödüllere yalnızca DOĞRULANMIŞ destekçiler girer.
- Aynı takım–destekçi çifti için yılda 1. destek tam, 2. destek yarım puan alır; sonrakiler puansızdır.
- Mentörlük puanı, aynı süreç için ayda en fazla 20 saatlik oturumdan hesaplanır.
- Şüpheli işaretler (aynı ağdan giriş, aynı e-posta alan adı, çok hızlı tamamlanma,
  doğrulanmamış takıma yüksek tutar) varsa puanlar silinmez ama "incelemede" tutulur;
  yönetici onaylayana kadar sıralamaya yansımaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.matching.models import MentorSession

from .models import Award, PointEntry

COMPLETION_BASE = 40
VALUE_FACTOR = 12          # 12 * sqrt(değer / 1000)
VALUE_CAP = 150
FIRST_TEAM_BONUS = 25
FAST_RESPONSE_BONUS = 5
FAST_RESPONSE_HOURS = 72
RATING_POINTS = {5: 15, 4: 8}
MENTOR_POINTS_PER_HOUR = 10
MENTOR_SESSION_CAP = 40
MENTOR_MONTHLY_HOURS_CAP = 20
CO_FUND_BONUS = 10
PAIR_MULTIPLIERS = {0: 1.0, 1: 0.5}   # aynı yıl içinde aynı çiftin önceki tamamlanan destek sayısı
HIGH_VALUE_REVIEW = Decimal(50000)
IP_LOOKBACK_DAYS = 60

VALID = Q(is_void=False, held=False)

TITLES = [  # (alt sınır, unvan, açıklama)
    (1500, "Anka", "Küllerinden yeniden doğan efsane kuş; platformun en yüksek unvanı."),
    (700, "Kartal", "Göklerin hâkimi; düzenli ve büyük katkılar."),
    (300, "Şahin", "Keskin göz; isabetli ve süreklileşen destekler."),
    (100, "Doğan", "Yükselişte; ilk destekleri tamamlanmış."),
    (0, "Kanat adayı", "Yolculuğun başı; ilk desteği bekleniyor."),
]


def value_points(value: Decimal | float | int | None) -> int:
    if not value or value <= 0:
        return 0
    return min(VALUE_CAP, round(VALUE_FACTOR * math.sqrt(float(value) / 1000)))


# --------------------------------------------------------------------------- #
# Şüphe işaretleri
# --------------------------------------------------------------------------- #
def suspicion_reasons(support_request, for_completion: bool = True) -> list[str]:
    from apps.core.models import AuditLog
    from apps.core.verification import FREE_EMAIL_DOMAINS, email_domain

    reasons: list[str] = []
    team = support_request.project.team
    sponsor = support_request.sponsor
    team_users = team.all_users
    since = timezone.now() - timedelta(days=IP_LOOKBACK_DAYS)
    logins = AuditLog.objects.filter(
        action__in=[AuditLog.Action.LOGIN, AuditLog.Action.REGISTER], created_at__gte=since
    ).exclude(ip_hash="")
    team_ips = set(logins.filter(user__in=team_users).values_list("ip_hash", flat=True))
    sponsor_ips = set(logins.filter(user_id=sponsor.owner_id).values_list("ip_hash", flat=True))
    if team_ips & sponsor_ips:
        reasons.append("Takım ve destekçi hesapları aynı ağ adresinden giriş yapmış.")

    sponsor_domain = email_domain(sponsor.owner.email)
    if sponsor_domain not in FREE_EMAIL_DOMAINS and any(
        email_domain(u.email) == sponsor_domain for u in team_users
    ):
        reasons.append("Takım ve destekçi aynı e-posta alan adını kullanıyor.")

    if for_completion:
        value = support_request.delivered_value or support_request.amount or Decimal(0)
        if value >= HIGH_VALUE_REVIEW and not team.verified:
            reasons.append("Doğrulanmamış takıma yüksek tutarlı destek.")
        if (support_request.completed_at and support_request.created_at
                and support_request.completed_at - support_request.created_at < timedelta(hours=24)):
            reasons.append("Talep 24 saatten kısa sürede tamamlanmış.")
    return reasons


def _hold(entries: list[PointEntry], reasons: list[str]) -> None:
    if not reasons:
        return
    text = " ".join(reasons)[:200]
    for e in entries:
        e.held, e.hold_reason = True, text


def _notify_hold(support_request) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import notify, sponsor_users, staff_users

    notify(staff_users(), Notification.Kind.SYSTEM, "Puan incelemesi bekliyor",
           f"Talep #{support_request.pk}: {support_request.project.title} ↔ {support_request.sponsor.name}",
           url=reverse("admin:rankings_pointentry_changelist") + "?held__exact=1", email=False)
    notify(sponsor_users(support_request.sponsor), Notification.Kind.POINTS,
           "Puanların kısa bir incelemeden geçiyor",
           "Bu destekten gelen puanlar, yönetim onayından sonra sıralamana yansıyacak.",
           url=support_request.get_absolute_url(), email=False)


# --------------------------------------------------------------------------- #
# Puan verme
# --------------------------------------------------------------------------- #
@transaction.atomic
def award_completion(support_request) -> list[PointEntry]:
    """Takım 'teslim aldık' dediğinde çağrılır. Aynı talep için iki kez puan verilmez."""
    if PointEntry.objects.filter(request=support_request, kind=PointEntry.Kind.COMPLETION).exists():
        return []

    Request = type(support_request)
    sponsor = support_request.sponsor
    team = support_request.project.team
    year = (support_request.completed_at or timezone.now()).year

    previous_pair = Request.objects.filter(
        project__team=team, sponsor=sponsor, status="tamamlandi", completed_at__year=year
    ).exclude(pk=support_request.pk).count()
    multiplier = PAIR_MULTIPLIERS.get(previous_pair, 0.0)
    pair_note = ""
    if multiplier < 1:
        pair_note = ("Aynı takıma bu yılki 2. destek: yarım puan." if multiplier
                     else "Aynı takıma bu yılki 3. ve sonraki destek: puan yok.")

    entries = [PointEntry(
        sponsor=sponsor, request=support_request, kind=PointEntry.Kind.COMPLETION,
        points=round(COMPLETION_BASE * multiplier),
        note=(pair_note or support_request.project.title)[:150],
    )]
    vp = round(value_points(support_request.delivered_value) * multiplier)
    if vp:
        entries.append(PointEntry(sponsor=sponsor, request=support_request,
                                  kind=PointEntry.Kind.VALUE, points=vp))

    earlier_team = Request.objects.filter(project__team=team, status="tamamlandi").exclude(pk=support_request.pk)
    if team.verified and not earlier_team.exists():
        entries.append(PointEntry(sponsor=sponsor, request=support_request,
                                  kind=PointEntry.Kind.FIRST_TEAM, points=FIRST_TEAM_BONUS,
                                  note="İlk kez destek alan takım"))

    if (
        support_request.initiated_by == "takim"
        and support_request.responded_at
        and support_request.responded_at - support_request.created_at <= timedelta(hours=FAST_RESPONSE_HOURS)
    ):
        entries.append(PointEntry(sponsor=sponsor, request=support_request,
                                  kind=PointEntry.Kind.FAST, points=FAST_RESPONSE_BONUS))

    rp = RATING_POINTS.get(support_request.rating or 0, 0)
    if rp and multiplier:
        entries.append(PointEntry(sponsor=sponsor, request=support_request,
                                  kind=PointEntry.Kind.RATING, points=rp))

    # Ortak kanat: aynı ihtiyaca başka bir destekçi de katkı verdiyse ikisi de bonus alır.
    if support_request.need_id:
        partners = Request.objects.filter(need_id=support_request.need_id, status="tamamlandi") \
            .exclude(pk=support_request.pk).exclude(sponsor=sponsor).select_related("sponsor")
        if partners.exists():
            entries.append(PointEntry(sponsor=sponsor, request=support_request,
                                      kind=PointEntry.Kind.CO_FUND, points=CO_FUND_BONUS,
                                      note="Bir ihtiyacı başka destekçilerle birlikte karşıladı"))
            for partner in partners:
                if not PointEntry.objects.filter(request=partner, kind=PointEntry.Kind.CO_FUND).exists():
                    entries.append(PointEntry(sponsor=partner.sponsor, request=partner,
                                              kind=PointEntry.Kind.CO_FUND, points=CO_FUND_BONUS,
                                              note="Bir ihtiyacı başka destekçilerle birlikte karşıladı"))

    reasons = suspicion_reasons(support_request)
    own = [e for e in entries if e.request_id == support_request.pk]
    _hold(own, reasons)
    created = PointEntry.objects.bulk_create(entries)
    if reasons:
        transaction.on_commit(lambda: _notify_hold(support_request))
    return created


def award_mentor_session(session) -> PointEntry | None:
    month_start = session.date.replace(day=1)
    used = MentorSession.objects.filter(
        request=session.request, confirmed_at__isnull=False,
        date__gte=month_start, date__lt=(month_start + timedelta(days=32)).replace(day=1),
    ).exclude(pk=session.pk).aggregate(h=Sum("hours"))["h"] or Decimal(0)
    counted = min(Decimal(session.hours), max(Decimal(0), Decimal(MENTOR_MONTHLY_HOURS_CAP) - used))
    pts = min(MENTOR_SESSION_CAP, round(float(counted) * MENTOR_POINTS_PER_HOUR))
    if pts <= 0:
        return None
    entry = PointEntry(
        sponsor=session.request.sponsor, request=session.request,
        kind=PointEntry.Kind.MENTOR, points=pts, note=session.topic[:150],
    )
    reasons = suspicion_reasons(session.request, for_completion=False)
    _hold([entry], reasons)
    entry.save()
    if reasons:
        transaction.on_commit(lambda: _notify_hold(session.request))
    return entry


# --------------------------------------------------------------------------- #
# Dönemler ve sıralama
# --------------------------------------------------------------------------- #
@dataclass
class Period:
    key: str          # "ay", "yil", "tum"
    label: str
    start: date | None
    end: date | None  # hariç


MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end


def resolve_period(key: str, today: date | None = None) -> Period:
    today = today or timezone.localdate()
    if key == "yil":
        return Period("yil", f"{today.year} yılı", date(today.year, 1, 1), date(today.year + 1, 1, 1))
    if key == "tum":
        return Period("tum", "Tüm zamanlar", None, None)
    start, end = month_bounds(today.year, today.month)
    return Period("ay", f"{MONTHS_TR[today.month - 1]} {today.year}", start, end)


def _valid_points_filter(period: Period) -> Q:
    flt = Q(points__is_void=False, points__held=False)
    if period.start:
        flt &= Q(points__created_at__date__gte=period.start, points__created_at__date__lt=period.end)
    return flt


def leaderboard(period: Period, league: str | None = None, limit: int = 50):
    from apps.sponsors.models import Sponsor

    flt = _valid_points_filter(period)
    qs = Sponsor.objects.filter(owner__is_active=True, verified=True)
    if league:
        qs = qs.filter(league=league)
    qs = (
        qs.annotate(
            total=Sum("points__points", filter=flt),
            supported=Count("points__request", filter=flt & Q(points__kind="tamamlanan_destek"),
                            distinct=True),
        )
        .filter(total__gt=0)
        .order_by("-total", "name")[:limit]
    )
    rows = list(qs)
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return rows


def total_points(sponsor) -> int:
    return sponsor.points.filter(VALID).aggregate(t=Sum("points"))["t"] or 0


def held_points(sponsor) -> int:
    return sponsor.points.filter(is_void=False, held=True).aggregate(t=Sum("points"))["t"] or 0


def title_for(points: int) -> dict:
    for floor, name, desc in TITLES:
        if points >= floor:
            nxt = next((t for t in reversed(TITLES) if t[0] > points), None)
            return {
                "name": name, "description": desc, "floor": floor,
                "next_name": nxt[1] if nxt else None,
                "next_floor": nxt[0] if nxt else None,
                "to_next": (nxt[0] - points) if nxt else 0,
                "progress": 100 if not nxt else round(100 * (points - floor) / (nxt[0] - floor)),
            }
    return {}


# --------------------------------------------------------------------------- #
# Rozetler (hesaplanır, saklanmaz)
# --------------------------------------------------------------------------- #
BADGES = [
    ("ilk-kanat", "İlk kanat", "İlk desteğini tamamladı."),
    ("kilavuz", "Kılavuz", "En az 10 saat onaylı mentörlük verdi."),
    ("firsat-elcisi", "Fırsat elçisi", "Hiç destek almamış 3 takıma ilk desteği verdi."),
    ("yedi-bolge", "Yedi bölge", "En az 5 farklı şehirden takımı destekledi."),
    ("hizli-kanat", "Hızlı kanat", "3 talebe 72 saat içinde yanıt verip desteği tamamladı."),
    ("gonul-kopru", "Gönül köprüsü", "Takımlardan 5 tam puanlık teşekkür aldı."),
    ("ortak-kanat", "Ortak kanat", "Bir ihtiyacı başka destekçilerle birlikte karşıladı."),
]


def badges_for(sponsor) -> list[dict]:
    pts = sponsor.points.filter(VALID)
    completed = sponsor.requests.filter(status="tamamlandi")
    mentor_hours = float(
        MentorSession.objects.filter(request__sponsor=sponsor, confirmed_at__isnull=False)
        .aggregate(h=Sum("hours"))["h"] or 0
    )
    earned = {
        "ilk-kanat": completed.exists(),
        "kilavuz": mentor_hours >= 10,
        "firsat-elcisi": pts.filter(kind="firsat_esitligi").count() >= 3,
        "yedi-bolge": completed.values("project__team__city").distinct().count() >= 5,
        "hizli-kanat": pts.filter(kind="hizli_yanit").count() >= 3,
        "gonul-kopru": completed.filter(rating=5).count() >= 5,
        "ortak-kanat": pts.filter(kind="ortak_kanat").exists(),
    }
    return [
        {"slug": slug, "name": name, "description": desc, "earned": earned[slug]}
        for slug, name, desc in BADGES
    ]


# --------------------------------------------------------------------------- #
# Ödül dağıtımı (günlük bakım komutundan çağrılır, tekrar çalıştırmak güvenlidir)
# --------------------------------------------------------------------------- #
@transaction.atomic
def issue_awards(period: Period, kind: str, top: int = 3) -> list[Award]:
    period_code = (
        f"{period.start.year}-{period.start.month:02d}" if period.key == "ay" else str(period.start.year)
    )
    issued = []
    leagues = [None, "mikro", "kobi", "buyuk"]
    for league in leagues:
        for row in leaderboard(period, league=league, limit=top):
            award, created = Award.objects.get_or_create(
                sponsor=row, kind=kind, period=period_code, league=league or "",
                defaults={"rank": row.rank, "points": row.total},
            )
            if created:
                issued.append(award)

    if period.key == "yil":
        issued += _special_award(period, period_code, Award.Kind.MENTOR, "mentorluk")
        issued += _special_award(period, period_code, Award.Kind.EQUITY, "firsat_esitligi")

    if issued:
        transaction.on_commit(lambda: _notify_awards(issued))
    return issued


def _notify_awards(awards) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import notify, sponsor_users

    for award in awards:
        league = f", {award.league_label} ligi" if award.league else ""
        notify(sponsor_users(award.sponsor), Notification.Kind.POINTS,
               f"Tebrikler! {award.get_kind_display()} ödülünü kazandın",
               f"{award.period_label}{league}, {award.rank}. sıra. Belgen hazır.",
               url=award.get_absolute_url())


def _special_award(period: Period, period_code: str, kind: str, point_kind: str) -> list[Award]:
    from apps.sponsors.models import Sponsor

    flt = Q(points__is_void=False, points__held=False, points__kind=point_kind,
            points__created_at__date__gte=period.start, points__created_at__date__lt=period.end)
    best = (
        Sponsor.objects.filter(verified=True, owner__is_active=True)
        .annotate(total=Sum("points__points", filter=flt))
        .filter(total__gt=0).order_by("-total").first()
    )
    if not best:
        return []
    award, created = Award.objects.get_or_create(
        sponsor=best, kind=kind, period=period_code, league="",
        defaults={"rank": 1, "points": best.total},
    )
    return [award] if created else []
