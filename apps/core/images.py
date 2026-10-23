"""
Yüklenen görsellerin güvenli işlenmesi.

Her görsel Pillow ile açılıp doğrulanır, boyutu küçültülür ve WebP olarak YENİDEN KODLANIR.
Böylece EXIF/konum gibi meta veriler silinir, görsel kılığındaki betik/polyglot dosyalar
etkisiz hale gelir ve dosya adı tahmin edilemeyen rastgele bir ad olur.
"""
from __future__ import annotations

import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
MAX_SIDE = 512


def sanitize_image(uploaded, folder: str) -> ContentFile:
    if uploaded.size > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise ValidationError("Görsel en fazla 2 MB olabilir.")

    Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS  # sıkıştırma bombasına karşı
    try:
        uploaded.seek(0)
        probe = Image.open(uploaded)
        probe.verify()  # bozuk/hileli dosyaları yakalar
        uploaded.seek(0)
        image = Image.open(uploaded)
        fmt = image.format
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValidationError("Bu dosya geçerli bir görsel değil.") from exc

    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Yalnızca PNG, JPEG, WebP veya GIF yükleyebilirsiniz.")

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGBA") if image.mode in ("P", "LA", "RGBA") else image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))

    out = io.BytesIO()
    image.save(out, format="WEBP", quality=85, method=4)  # meta veri taşınmaz
    return ContentFile(out.getvalue(), name=f"{folder}/{uuid.uuid4().hex}.webp")
