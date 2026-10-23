from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("yeni/", views.project_create, name="create"),
    path("takimim/", views.team_edit, name="team_edit"),
    path("takimim/uyeler/", views.members, name="members"),
    path("takimim/uyeler/<int:pk>/cikar/", views.member_remove, name="member_remove"),
    path("takimim/davet/<int:pk>/iptal/", views.invite_cancel, name="invite_cancel"),
    path("takimim/ayril/", views.leave_team, name="leave"),
    path("davet/<str:token>/", views.invite_accept, name="invite_accept"),
    path("takim/<slug:slug>/", views.team_detail, name="team_detail"),
    path("<slug:slug>/", views.project_detail, name="detail"),
    path("<slug:slug>/duzenle/", views.project_edit, name="edit"),
    path("<slug:slug>/durum/", views.project_status, name="status"),
    path("<slug:slug>/gunluk/", views.update_create, name="update_create"),
    path("<slug:slug>/dosya/", views.dossier_download, name="dossier"),
    path("<slug:slug>/dosya/yukle/", views.dossier_upload, name="dossier_upload"),
    path("<slug:slug>/dosya/sil/", views.dossier_delete, name="dossier_delete"),
]
