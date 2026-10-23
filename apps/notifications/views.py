from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Notification
from .services import read_unsubscribe_token


@login_required
def notification_list(request):
    qs = request.user.notifications.all()
    page = Paginator(qs, 30).get_page(request.GET.get("sayfa"))
    return render(request, "notifications/list.html", {"page": page, "querystring": ""})


@login_required
def open_notification(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    if n.url and url_has_allowed_host_and_scheme(n.url, allowed_hosts={request.get_host()}):
        return redirect(n.url)
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    messages.success(request, "Tüm bildirimler okundu olarak işaretlendi.")
    return redirect("notifications:list")


# RFC 8058 "tek tıkla abonelikten çık": e-posta istemcisi CSRF belirteci olmadan POST eder.
# Yetkilendirme, imzalı ve kullanıcıya özel bağlantı ile yapılır; işlem yalnızca e-posta
# bildirimlerini KAPATIR (zararsız, geri alınabilir).
@csrf_exempt
def unsubscribe(request, token):
    user = read_unsubscribe_token(token)
    if user is None:
        return render(request, "notifications/unsubscribe.html", {"invalid": True}, status=400)
    if request.method == "POST":
        if user.email_notifications:
            user.email_notifications = False
            user.save(update_fields=["email_notifications"])
        return render(request, "notifications/unsubscribe.html", {"done": True})
    return render(request, "notifications/unsubscribe.html", {"token": token})
