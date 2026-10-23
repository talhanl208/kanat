"""
Profil gücü: profili tamamlamaya yönelik somut, tıklanabilir bir kontrol listesi.
Destekçiler daha dolu profilleri ciddiye alır; eşleştirme de daha isabetli olur.
"""
from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone


def _result(items):
    done = sum(weight for _, _, weight, ok in items if ok)
    total = sum(weight for _, _, weight, _ in items) or 1
    return {
        "percent": round(100 * done / total),
        "items": [{"label": label, "url": url, "done": ok} for label, url, _, ok in items],
        "missing": [{"label": label, "url": url} for label, url, _, ok in items if not ok],
    }


def team_strength(team) -> dict:
    projects = list(team.projects.filter(status="aktif").prefetch_related("needs", "updates"))
    focus = projects[0] if projects else None
    edit_team = reverse("projects:team_edit")
    edit_project = reverse("projects:edit", args=[focus.slug]) if focus else reverse("projects:create")
    project_url = focus.get_absolute_url() if focus else reverse("projects:create")
    recent = timezone.now() - timedelta(days=30)
    items = [
        ("Takımı en az birkaç cümleyle anlat", edit_team, 10, len(team.about or "") >= 120),
        ("Logo ekle", edit_team, 10, bool(team.logo)),
        ("Web sitesi ya da sosyal medya bağlantısı ekle", edit_team, 5, bool(team.website)),
        ("Takımını doğrulat", reverse("core:verification"), 15, team.verified),
        ("Destek arayan bir proje yayınla", reverse("projects:create"), 15, bool(focus)),
        ("İhtiyaçlara tutar ya da saat yaz", edit_project, 10,
         bool(focus) and all((n.estimated_cost or n.mentor_hours) for n in focus.needs.all())),
        ("Destekçiye neler sunduğunu yaz", edit_project, 10, bool(focus and focus.sponsor_benefits)),
        ("Sponsorluk dosyanı (PDF) yükle", project_url + "#dosya", 15, bool(focus and focus.dossier)),
        ("Son 30 günde proje günlüğüne bir şey yaz", project_url + "#gunluk", 5,
         bool(focus) and any(u.created_at >= recent for u in focus.updates.all())),
        ("Takım arkadaşlarını davet et", reverse("projects:members"), 5,
         team.kind == "bireysel" or team.memberships.exists()),
    ]
    return _result(items)


def sponsor_strength(sponsor) -> dict:
    edit = reverse("sponsors:edit")
    items = [
        ("Kendini en az birkaç cümleyle tanıt", edit, 10, len(sponsor.about or "") >= 120),
        ("Logo ekle", edit, 10, bool(sponsor.logo)),
        ("Web siteni ekle", edit, 10, bool(sponsor.website)),
        ("Profilini doğrulat (sıralamaya girmek için gerekli)", reverse("core:verification"), 25,
         sponsor.verified),
        ("En az 3 ürün/hizmet anahtar kelimesi yaz", edit, 15, len(sponsor.offering_keywords) >= 3),
        ("İlgilendiğin alanları seç", edit, 10, bool(sponsor.interest_categories)),
        ("Bütçe aralığını ya da mentörlük kapasiteni yaz", edit, 10,
         bool(sponsor.budget_max or sponsor.mentor_hours_per_month)),
        ("Bir destek çağrısı yayınla", reverse("sponsors:call_create"), 10, sponsor.calls.exists()),
    ]
    return _result(items)
