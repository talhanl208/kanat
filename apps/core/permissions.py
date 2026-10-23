"""Rol ve doğrulama kontrolleri. Nesne düzeyindeki yetki kontrolleri görünümlerde yapılır."""
import functools

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def role_required(role: str):
    def decorator(view):
        @login_required
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role != role:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def profile_required(view):
    """Takım/destekçi profili olmayan kullanıcıyı önce profil oluşturmaya yönlendirir."""

    @login_required
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_team and user.team_or_none is None:
            messages.info(request, "Önce takım profilini oluştur ya da sana gelen davet bağlantısını aç.")
            return redirect("projects:team_edit")
        if user.is_sponsor and not hasattr(user, "sponsor"):
            messages.info(request, "Önce destekçi profilini oluştur.")
            return redirect("sponsors:edit")
        return view(request, *args, **kwargs)

    return wrapped


def verified_required(view):
    """Mesajlaşma ve talep gönderme gibi işlemler için e-posta doğrulaması şarttır (spam'e karşı)."""

    @login_required
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.email_verified:
            messages.warning(request, "Bu işlem için önce e-posta adresini doğrulaman gerekiyor.")
            return redirect("accounts:settings")
        return view(request, *args, **kwargs)

    return wrapped


def captain_required(view):
    """Yalnızca takım kaptanı: profil, üyeler, sözleşme onayı, teslim onayı gibi bağlayıcı işlemler."""

    @profile_required
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_team_captain:
            messages.warning(request, "Bu işlemi yalnızca takım kaptanı yapabilir.")
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
