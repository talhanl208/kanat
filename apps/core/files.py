"""
Sponsorluk dosyası (PDF) güvenlik denetimi.

PDF'ler betik çalıştırabilir, dosya gömebilir, dış bağlantı açabilir. Bu yüzden:
- Boyut sınırı, '%PDF-' imzası ve dosya sonu işareti kontrol edilir.
- Şifreli PDF'ler reddedilir (içleri taranamaz).
- Ham içerik ve sıkıştırılmış (FlateDecode) akışlar açılarak tehlikeli anahtarlar aranır:
  JavaScript, Launch, EmbeddedFile, RichMedia, XFA, SubmitForm, ImportData, GoToR, GoToE.
  PDF ad kaçışları (#4A gibi) çözüldükten sonra arama yapılır.
- Açma sırasında sıkıştırma bombasına karşı toplam boyut sınırlanır.
Kabul edilen dosya rastgele adla, web'den erişilemeyen klasöre kaydedilir ve yalnızca
"indirme" (attachment) olarak, ayrı bir CSP sandbox'ı ile sunulur.
"""
from __future__ import annotations

import re
import uuid
import zlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

FORBIDDEN = (
    b"/javascript", b"/js", b"/launch", b"/embeddedfile", b"/embeddedfiles", b"/richmedia",
    b"/xfa", b"/submitform", b"/importdata", b"/gotor", b"/gotoe",
)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_NAME_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_FORBIDDEN_RE = re.compile(rb"(" + rb"|".join(re.escape(f) for f in FORBIDDEN) + rb")(?![a-z0-9])")
MAX_INFLATED_TOTAL = 60 * 1024 * 1024


def _decode_names(data: bytes) -> bytes:
    return _NAME_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), data)


def _inflated_streams(data: bytes):
    budget = MAX_INFLATED_TOTAL
    for match in _STREAM.finditer(data):
        raw = match.group(1)
        try:
            d = zlib.decompressobj()
            out = d.decompress(raw, budget)
        except zlib.error:
            continue
        budget -= len(out)
        yield out
        if budget <= 0:
            raise ValidationError("PDF içeriği açılırken boyut sınırı aşıldı.")


def scan_pdf_bytes(data: bytes) -> None:
    head = data[:1024]
    if b"%PDF-" not in head:
        raise ValidationError("Bu dosya geçerli bir PDF değil.")
    if b"%%EOF" not in data[-2048:]:
        raise ValidationError("PDF dosyası eksik ya da bozuk görünüyor.")
    candidates = [data, *_inflated_streams(data)]
    for chunk in candidates:
        lowered = _decode_names(chunk).lower()
        if b"/encrypt" in lowered:
            raise ValidationError("Şifreli PDF'ler kabul edilmiyor. Şifresiz kaydedip yeniden yükle.")
        hit = _FORBIDDEN_RE.search(lowered)
        if hit:
            raise ValidationError(
                "PDF'te izin verilmeyen etkin içerik var (betik, gömülü dosya ya da form). "
                "Dosyayı 'PDF olarak yazdır' ile yeniden oluşturup yükle."
            )


def sanitize_pdf(uploaded, folder: str = "dosyalar") -> ContentFile:
    if uploaded.size > settings.MAX_PDF_UPLOAD_BYTES:
        raise ValidationError("Sponsorluk dosyası en fazla 5 MB olabilir.")
    name = (getattr(uploaded, "name", "") or "").lower()
    if not name.endswith(".pdf"):
        raise ValidationError("Yalnızca .pdf uzantılı dosya yükleyebilirsin.")
    uploaded.seek(0)
    data = uploaded.read(settings.MAX_PDF_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_PDF_UPLOAD_BYTES:
        raise ValidationError("Sponsorluk dosyası en fazla 5 MB olabilir.")
    scan_pdf_bytes(data)
    return ContentFile(data, name=f"{folder}/{uuid.uuid4().hex}.pdf")
