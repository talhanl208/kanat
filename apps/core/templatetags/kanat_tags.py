from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

from apps.core.constants import SUPPORT_LABELS
from apps.core.utils import tr_normalize

register = template.Library()


@register.filter
def tl(value):
    """18000 -> '18.000 ₺'"""
    if value in (None, ""):
        return ""
    try:
        number = int(Decimal(value))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    return f"{number:,} ₺".replace(",", ".")


@register.filter
def destek_adi(code):
    return SUPPORT_LABELS.get(code, code)


@register.filter
def css_ad(value):
    """'Kanat adayı' -> 'kanat-adayi' (CSS sınıfı için güvenli)."""
    return "-".join(tr_normalize(str(value)).split())


@register.simple_tag(takes_context=True)
def aktif(context, prefix, haric=""):
    request = context.get("request")
    if request and request.path.startswith(prefix) and not (haric and request.path.startswith(haric)):
        return mark_safe('aria-current="page"')  # sabit metin
    return ""


@register.filter
def ilk_harf(value):
    parts = [p for p in str(value).split() if p]
    return "".join(p[0] for p in parts[:2]).upper()
