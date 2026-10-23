"""
Eşleştirme motoru.

Her proje–destekçi çifti için 0–100 arası bir uyum puanı ve bunun NEDENLERİNİ üretir.
Kural tabanlıdır ve açıklanabilir: kullanıcı neden eşleştiğini görür (KVKK md. 11/1-g:
otomatik analiz sonucuna itiraz hakkı için de şeffaflık gerekir).

Ağırlıklar
    Destek türü uyumu   35   Takımın açık ihtiyaç türleri ile destekçinin sundukları
    Alan uyumu          20   Proje alanı destekçinin ilgi alanlarında mı
    Bütçe uyumu         15   Maddi ihtiyaç destekçinin bütçe aralığına giriyor mu
    Ürün/hizmet uyumu   10   Destekçinin anahtar kelimeleri ihtiyaç listesinde KELİME BAŞINDA geçiyor mu
                             (Türkçe ekleri tanır: "motor" -> "motorlar"; "elektromotor"u eşlemez)
    Konum               10   Aynı şehir veya tüm Türkiye
    Yarışma uyumu       10   Destekçi bu yarışma/programı destekliyor mu
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.constants import CATEGORY_LABELS, COMPETITION_LABELS, SUPPORT_LABELS
from apps.core.utils import tr_normalize


@dataclass
class MatchResult:
    score: int
    reasons: list[str] = field(default_factory=list)
    shared_kinds: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if self.score >= 75:
            return "guclu"
        if self.score >= 50:
            return "iyi"
        return "zayif"

    @property
    def level_label(self) -> str:
        return {"guclu": "Güçlü uyum", "iyi": "İyi uyum", "zayif": "Kısmi uyum"}[self.level]


def _fmt_tl(value) -> str:
    return f"{int(value):,} ₺".replace(",", ".")


def keyword_in(keyword_norm: str, haystack_norm: str) -> bool:
    """Anahtar kelime metinde bir kelimenin BAŞINDA geçiyor mu? 2 harfli kelimeler tam eşleşmeli."""
    keyword_norm = " ".join(keyword_norm.split())
    if len(keyword_norm) < 2:
        return False
    tail = r"(?![a-z0-9])" if len(keyword_norm) < 3 else ""
    return re.search(r"(?<![a-z0-9])" + re.escape(keyword_norm) + tail, haystack_norm) is not None


def score_match(project, sponsor) -> MatchResult:
    reasons: list[str] = []
    score = 0.0

    # 1) Destek türü
    need_kinds = project.need_kinds
    offered = set(sponsor.support_types or [])
    shared = sorted(need_kinds & offered)
    if need_kinds:
        score += 35 * len(shared) / len(need_kinds)
    if shared:
        labels = ", ".join(SUPPORT_LABELS[k].lower() for k in shared)
        reasons.append(f"İhtiyaç duyduğun {labels} desteğini sunuyor.")
    if not shared:
        # Hiçbir ihtiyaç türü örtüşmüyorsa diğer sinyaller ne olursa olsun düşük kalsın.
        return MatchResult(score=min(15, round(score)), reasons=["Destek türleri örtüşmüyor."])

    # 2) Alan
    interests = set(sponsor.interest_categories or [])
    if project.category in interests:
        score += 20
        reasons.append(f"{CATEGORY_LABELS[project.category]} alanıyla ilgileniyor.")
    elif not interests:
        score += 10

    # 3) Bütçe (ortak kanat: bir ihtiyacın bir kısmını üstlenmek de değerlidir)
    need = project.monetary_need
    largest = project.largest_monetary_need
    if need > 0 and offered & {"maddi", "malzeme", "hizmet", "ulasim"}:
        low = Decimal(sponsor.budget_min or 0)
        high = Decimal(sponsor.budget_max) if sponsor.budget_max else None
        if high is None or low <= need <= high:
            score += 15
            reasons.append(f"Kalan {_fmt_tl(need)} tutarındaki ihtiyacın bütçe aralığında.")
        elif high and high >= largest and largest > 0:
            score += 12
            reasons.append(f"En büyük ihtiyacını ({_fmt_tl(largest)}) tek başına karşılayabilir.")
        elif high and high >= need * Decimal("0.3"):
            score += 8
            reasons.append(f"Ortak kanat olarak ihtiyacının bir kısmını ({_fmt_tl(high)}) üstlenebilir.")
    elif "mentorluk" in shared:
        score += 15 if (sponsor.mentor_hours_per_month or 0) > 0 else 8

    # 4) Ürün / hizmet anahtar kelimeleri
    haystack = tr_normalize(
        " ".join(f"{n.title} {n.detail}" for n in project.open_needs) + " " + project.description
    )
    matched = [shown for shown, norm in sponsor.offering_tokens if norm and keyword_in(norm, haystack)]
    if matched:
        score += min(10, 5 * len(matched))
        reasons.append("Aradığın ürün/hizmetler: " + ", ".join(matched[:3]) + ".")

    # 5) Konum
    if sponsor.city == project.team.city:
        score += 10
        reasons.append(f"Aynı şehirdesiniz ({project.team.city}).")
    elif sponsor.serves_all_turkey:
        score += 6

    # 6) Yarışma
    comps = set(sponsor.competitions or [])
    if project.competition in comps:
        score += 10
        reasons.append(f"{COMPETITION_LABELS[project.competition]} takımlarını destekliyor.")
    elif not comps:
        score += 5

    return MatchResult(
        score=max(0, min(100, round(score))),
        reasons=reasons,
        shared_kinds=shared,
        matched_keywords=matched,
    )


def recommend_sponsors(project, limit: int = 6, min_score: int = 30):
    from django.db.models import prefetch_related_objects

    from apps.sponsors.models import Sponsor

    prefetch_related_objects([project], "needs__contributions")
    engaged = project.requests.exclude(status__in=["red", "geri_cekildi"]).values("sponsor_id")
    candidates = (
        Sponsor.objects.available()
        .exclude(owner=project.team.owner)
        .exclude(pk__in=engaged)
        .exclude(blocks__team=project.team)
        .select_related("owner")
    )
    scored = [(s, score_match(project, s)) for s in candidates]
    scored = [pair for pair in scored if pair[1].score >= min_score]
    scored.sort(key=lambda pair: (-pair[1].score, not pair[0].verified, pair[0].name))
    return scored[:limit]


def recommend_projects(sponsor, limit: int = 8, min_score: int = 30):
    from apps.projects.models import Project

    candidates = (
        Project.objects.public()
        .select_related("team")
        .prefetch_related("needs__contributions")
        .exclude(team__owner=sponsor.owner)
        .exclude(pk__in=sponsor.requests.exclude(status__in=["red", "geri_cekildi"]).values("project_id"))
        .exclude(team__blocks__sponsor=sponsor)
    )
    scored = [(p, score_match(p, sponsor)) for p in candidates]
    scored = [pair for pair in scored if pair[1].score >= min_score]
    scored.sort(key=lambda pair: (-pair[1].score, pair[0].deadline or pair[0].created_at.date()))
    return scored[:limit]
