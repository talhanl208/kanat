from django.urls import path

from . import views

app_name = "rankings"

urlpatterns = [
    path("", views.leaderboard, name="leaderboard"),
    path("oduller/", views.awards, name="awards"),
    path("belge/<str:code>/", views.certificate, name="certificate"),
    path("tesekkurler/", views.thanks_wall, name="thanks"),
    path("rozet/<slug:slug>.svg", views.badge_svg, name="badge"),
]
