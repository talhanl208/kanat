from django.urls import path

from . import views

app_name = "sponsors"

urlpatterns = [
    path("", views.sponsor_list, name="list"),
    path("profilim/", views.sponsor_edit, name="edit"),
    path("etki-raporu/", views.impact_report, name="impact"),
    path("cagrilar/", views.call_list, name="calls"),
    path("cagrilar/yeni/", views.call_create, name="call_create"),
    path("cagrilar/<int:pk>/", views.call_detail, name="call_detail"),
    path("cagrilar/<int:pk>/duzenle/", views.call_edit, name="call_edit"),
    path("cagrilar/<int:pk>/kapat/", views.call_close, name="call_close"),
    path("<slug:slug>/", views.sponsor_detail, name="detail"),
]
