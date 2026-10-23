"""
Hukuki metinlerin sürümleri.

Bir metni değiştirdiğinizde sürümünü artırın: kullanıcıların hangi sürümü ne zaman
onayladığı ConsentRecord tablosunda saklanır (KVKK ispat yükü veri sorumlusundadır).
"""

LEGAL_DOCUMENTS = {
    "aydinlatma": {
        "title": "KVKK aydınlatma metni",
        "version": "1.1",
        "template": "legal/aydinlatma.html",
        "updated": "23 Ekim 2026",
    },
    "kullanim": {
        "title": "Kullanım koşulları",
        "version": "1.1",
        "template": "legal/kullanim.html",
        "updated": "23 Ekim 2026",
    },
    "acik-riza": {
        "title": "Açık rıza metni (bülten ve duyurular)",
        "version": "1.0",
        "template": "legal/acik_riza.html",
        "updated": "22 Ekim 2026",
    },
    "cerez": {
        "title": "Çerez politikası",
        "version": "1.0",
        "template": "legal/cerez.html",
        "updated": "22 Ekim 2026",
    },
    "sponsorluk-sozlesmesi": {
        "title": "Sponsorluk ve destek sözleşmesi şablonu",
        "version": "1.0",
        "template": "legal/sponsorluk_sablonu.html",
        "updated": "22 Ekim 2026",
    },
}


def version_of(slug: str) -> str:
    return LEGAL_DOCUMENTS[slug]["version"]
