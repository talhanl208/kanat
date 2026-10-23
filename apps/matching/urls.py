from django.urls import path

from . import views

app_name = "matching"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("proje/<slug:slug>/destek-ol/", views.offer_to_project, name="offer"),
    path("destekci/<slug:slug>/destek-iste/", views.ask_sponsor, name="ask"),
    path("cagri/<int:pk>/basvur/", views.call_apply, name="call_apply"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/mesaj/", views.post_message, name="message"),
    path("<int:pk>/yanit/", views.respond, name="respond"),
    path("<int:pk>/geri-cek/", views.withdraw, name="withdraw"),
    path("<int:pk>/sozlesme/", views.agreement_view, name="agreement"),
    path("<int:pk>/sozlesme/duzenle/", views.agreement_edit, name="agreement_edit"),
    path("<int:pk>/sozlesme/onayla/", views.agreement_approve, name="agreement_approve"),
    path("<int:pk>/teslim/", views.complete, name="complete"),
    path("<int:pk>/mentorluk/", views.session_add, name="session_add"),
    path("<int:pk>/mentorluk/<int:session_id>/onayla/", views.session_confirm, name="session_confirm"),
    path("<int:pk>/sikayet/", views.report, name="report"),
    path("<int:pk>/engelle/", views.block, name="block"),
    path("<int:pk>/engeli-kaldir/", views.unblock, name="unblock"),
]
