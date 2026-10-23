from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("kayit/", views.register, name="register"),
    path("giris/", views.login_view, name="login"),
    path("giris/dogrula/", views.login_2fa, name="login_2fa"),
    path("iki-adim/", views.two_factor, name="two_factor"),
    path("iki-adim/dogrula/", views.two_factor_verify, name="two_factor_verify"),
    path("eposta/degistir/", views.email_change, name="email_change"),
    path("eposta/onayla/<str:token>/", views.email_change_confirm, name="email_change_confirm"),
    path("cikis/", views.logout_view, name="logout"),
    path("dogrula/<str:token>/", views.verify_email, name="verify"),
    path("dogrulama-gonder/", views.resend_verification, name="resend_verification"),
    path("ayarlar/", views.account_settings, name="settings"),
    path("onay-guncelle/", views.reconsent, name="reconsent"),
    path("verilerim/", views.export_data, name="export"),
    path("hesabi-kapat/", views.delete_account, name="delete"),
    path("parola/degistir/", views.PasswordChangeView.as_view(), name="password_change"),
    path("parola/sifirla/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "parola/sifirla/gonderildi/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "parola/sifirla/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "parola/sifirla/tamam/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
