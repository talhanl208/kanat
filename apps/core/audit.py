from .models import AuditLog
from .utils import request_ip_hash


def audit(request, action: str, user=None, detail: str = "") -> None:
    """Güvenlik olayı kaydeder. `detail` alanına kişisel veri yazmayın."""
    if user is None and getattr(request, "user", None) is not None and request.user.is_authenticated:
        user = request.user
    AuditLog.objects.create(
        user=user, action=action, ip_hash=request_ip_hash(request), detail=detail[:200]
    )
