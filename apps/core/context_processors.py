from django.conf import settings

from .quotes import random_quote


def site(request):
    unread = 0
    needs_reconsent = False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(read_at__isnull=True).count()
        from apps.accounts.services import outdated_consents

        needs_reconsent = bool(outdated_consents(user))
    return {
        "SITE": settings.KANAT,
        "csp_nonce": getattr(request, "csp_nonce", ""),
        "footer_quote": random_quote(),
        "unread_notifications": unread,
        "needs_reconsent": needs_reconsent,
    }
