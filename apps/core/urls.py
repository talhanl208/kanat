from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("hakkinda/", views.about, name="about"),
    path("panel/", views.dashboard, name="dashboard"),
    path("baslangic/", views.onboarding, name="onboarding"),
    path("yasal/<slug:slug>/", views.legal, name="legal"),
    path("kvkk-basvuru/", views.data_request, name="data_request"),
    path("dogrulama/", views.verification, name="verification"),
    path("saglik/", views.health, name="health"),
    path("robots.txt", views.robots_txt, name="robots"),
    path(".well-known/security.txt", views.security_txt, name="security_txt"),
]
