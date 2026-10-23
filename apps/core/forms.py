from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from .images import sanitize_image


def validate_https(url: str) -> str:
    """Yalnızca https bağlantılarına izin verilir (javascript:, data:, http: reddedilir)."""
    if url and not url.lower().startswith("https://"):
        raise ValidationError("Bağlantı https:// ile başlamalı.")
    return url


class LogoCleanMixin:
    """`logo` alanındaki yeni yüklemeyi doğrular ve güvenli WebP'ye dönüştürür."""

    logo_folder = "logolar"

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if isinstance(logo, UploadedFile):
            return sanitize_image(logo, self.logo_folder)
        return logo

    def clean_website(self):
        return validate_https(self.cleaned_data.get("website", ""))


class StyledFormMixin:
    """Form alanlarına tema sınıflarını ekler."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{css} input".strip()
