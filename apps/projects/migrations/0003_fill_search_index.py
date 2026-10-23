"""Mevcut projeler ve destekçiler için Türkçe uyumlu arama dizinini doldurur."""
from django.db import migrations

from apps.core.constants import CATEGORY_KEYWORDS, CATEGORY_LABELS, COMPETITION_LABELS, SUPPORT_LABELS
from apps.core.utils import search_text


def fill(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    Need = apps.get_model("projects", "Need")
    Sponsor = apps.get_model("sponsors", "Sponsor")
    for p in Project.objects.select_related("team"):
        needs = " ".join(f"{n.title} {n.detail}" for n in Need.objects.filter(project=p))
        p.search_index = search_text(
            p.title, p.summary, p.description, p.competition_detail,
            CATEGORY_LABELS.get(p.category, ""), CATEGORY_KEYWORDS.get(p.category, ""),
            COMPETITION_LABELS.get(p.competition, ""),
            p.team.name, p.team.institution, p.team.city, needs,
        )
        p.save(update_fields=["search_index"])
    for s in Sponsor.objects.all():
        s.search_index = search_text(
            s.name, s.sector, s.offerings, s.city, s.about,
            " ".join(SUPPORT_LABELS.get(k, k) for k in s.support_types or []),
            " ".join(CATEGORY_LABELS.get(c, c) for c in s.interest_categories or []),
        )
        s.save(update_fields=["search_index"])


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_project_dossier_project_dossier_uploaded_at_and_more"),
        ("sponsors", "0002_sponsor_max_active_projects_sponsor_search_index_and_more"),
    ]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
