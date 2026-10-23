from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("okundu/", views.mark_all_read, name="mark_all_read"),
    path("<int:pk>/", views.open_notification, name="open"),
    path("abonelik/<str:token>/", views.unsubscribe, name="unsubscribe"),
]
