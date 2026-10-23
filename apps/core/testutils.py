"""Testlerde ortak kullanılan veri üreticileri."""
import zlib
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import Need, Project, Team, TeamMembership
from apps.sponsors.models import Sponsor

PASSWORD = "Test-Parola-2026!"


def make_user(email, role, verified=True):
    return User.objects.create_user(
        email=email, password=PASSWORD, full_name="Test Kişi", role=role, email_verified=verified
    )


def make_team(email="takim@ornek.test", city="Konya", verified=True, team_verified=True, category="ika"):
    user = make_user(email, User.Role.TEAM, verified)
    team = Team.objects.create(owner=user, name=f"Takım {email}", institution="Okul", city=city,
                               about="Hakkında", member_count=5, verified=team_verified,
                               verification_method="yonetici" if team_verified else "")
    project = Project.objects.create(
        team=team, title=f"Proje {email}", summary="Özet", description="Uzun açıklama motorlar ve sürücü",
        category=category, competition="teknofest", stage="prototip",
    )
    Need.objects.create(project=project, kind="malzeme", title="Fırçasız motor", estimated_cost=Decimal(10000))
    Need.objects.create(project=project, kind="mentorluk", title="ROS mentörlüğü", mentor_hours=5)
    return user, team, project


def add_member(team, email):
    user = make_user(email, User.Role.TEAM)
    TeamMembership.objects.create(team=team, user=user)
    return user


def make_sponsor(email="destekci@ornek.test", city="Konya", verified=True, sponsor_verified=True, **extra):
    user = make_user(email, User.Role.SPONSOR, verified)
    data = dict(
        owner=user, name=f"Firma {email}", sector="Elektronik", city=city, about="Hakkında",
        support_types=["malzeme", "mentorluk"], interest_categories=["ika"], competitions=["teknofest"],
        budget_min=1000, budget_max=50000, mentor_hours_per_month=10, offerings="motor, PCB",
        verified=sponsor_verified, verification_method="yonetici" if sponsor_verified else "",
    )
    data.update(extra)
    return user, Sponsor.objects.create(**data)


def age_request(req, days=3):
    """Hızlı tamamlanma işaretine takılmamak için talebi geçmişe taşır."""
    type(req).objects.filter(pk=req.pk).update(created_at=timezone.now() - timedelta(days=days))
    req.refresh_from_db()
    return req


def clear_cache():
    cache.clear()


MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj\n"
    b"trailer << /Root 1 0 R >>\n%%EOF\n"
)


def pdf_with(extra: bytes = b"", compressed: bytes | None = None) -> bytes:
    body = MINIMAL_PDF.replace(b"trailer", extra + b"\ntrailer")
    if compressed is not None:
        data = zlib.compress(compressed)
        stream = (b"4 0 obj << /Length " + str(len(data)).encode() + b" /Filter /FlateDecode >> stream\n"
                  + data + b"\nendstream endobj\n")
        body = body.replace(b"trailer", stream + b"trailer")
    return body
